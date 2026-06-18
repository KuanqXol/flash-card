import sqlite3
from datetime import datetime
import math

SCORE_RULES = {
    'flashcard': lambda rating: rating,  # 1-5
    'matching_correct': 3,
    'matching_wrong': -2,
    'fill_correct': 5,
    'fill_wrong': -3,
}

def apply_flashcard_rating(db: sqlite3.Connection, word_id: int, rating: int) -> dict:
    """
    Apply flashcard rating (1-5).
    Returns: { new_score, old_score, status_changed, new_status, delta }
    """
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5")
        
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    cursor.execute("SELECT total_score FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Word with id {word_id} not found")
    old_score = row['total_score']
    
    delta = SCORE_RULES['flashcard'](rating)
    new_score, status_changed, new_status = _apply_score_change(
        db=db,
        word_id=word_id,
        delta=delta,
        mode='flashcard',
        rating=rating
    )
    
    return {
        'new_score': new_score,
        'old_score': old_score,
        'status_changed': status_changed,
        'new_status': new_status,
        'delta': delta
    }

def apply_matching_result(db: sqlite3.Connection, word_id: int, is_correct: bool) -> dict:
    """
    Apply matching game result.
    Returns: { new_score, delta }
    """
    delta = SCORE_RULES['matching_correct'] if is_correct else SCORE_RULES['matching_wrong']
    new_score, _, _ = _apply_score_change(
        db=db,
        word_id=word_id,
        delta=delta,
        mode='matching',
        is_correct=is_correct
    )
    return {
        'new_score': new_score,
        'delta': delta
    }

def apply_fill_result(db: sqlite3.Connection, word_id: int, is_correct: bool) -> dict:
    """
    Apply fill-in-the-blank self-evaluation.
    Returns: { new_score, delta }
    """
    delta = SCORE_RULES['fill_correct'] if is_correct else SCORE_RULES['fill_wrong']
    new_score, _, _ = _apply_score_change(
        db=db,
        word_id=word_id,
        delta=delta,
        mode='fill',
        is_correct=is_correct
    )
    return {
        'new_score': new_score,
        'delta': delta
    }

def mark_as_learned(db: sqlite3.Connection, word_id: int) -> dict:
    """Manually mark a word as learned."""
    cursor = db.cursor()
    cursor.execute("UPDATE words SET status = 'learned' WHERE id = ?", (word_id,))
    db.commit()
    return {'success': True}

def mark_as_learning(db: sqlite3.Connection, word_id: int) -> dict:
    """Reset a word back to learning status."""
    cursor = db.cursor()
    cursor.execute("UPDATE words SET status = 'learning' WHERE id = ?", (word_id,))
    db.commit()
    return {'success': True}

def _apply_score_change(db: sqlite3.Connection, word_id: int, delta: int, mode: str, rating: int = None, is_correct: bool = None) -> tuple:
    """
    Internal helper: apply score delta, update counts, log history.
    Delegates database updates to database.update_word_after_review.
    Returns: (new_score, status_changed, new_status)
    """
    from database import update_word_after_review
    updated_word, status_changed = update_word_after_review(
        db, word_id, delta, mode, rating=rating, is_correct=is_correct
    )
    return updated_word['total_score'], status_changed, updated_word['status']


def calculate_priority(word: dict) -> float:
    """
    Tính priority score: score cao hơn = cần ôn hơn.
    
    Công thức:
    priority = accuracy_pressure + staleness + status_bonus + recent_fail_boost - mastery_reduction
    """
    total_reviews = (word.get('correct_count') or 0) + (word.get('wrong_count') or 0)
    
    # 1. Accuracy pressure (0-50): sai nhiều = urgent hơn
    if total_reviews > 0:
        wrong_ratio = (word.get('wrong_count') or 0) / total_reviews
    else:
        wrong_ratio = 0.5  # Từ mới chưa review: giả định 50%
    accuracy_pressure = wrong_ratio * 50
    
    # 2. Staleness (0-60): lâu không ôn = urgent hơn, cap ở 30 ngày
    if word.get('last_reviewed'):
        try:
            delta = datetime.now() - datetime.fromisoformat(word['last_reviewed'])
            days = min(delta.total_seconds() / 86400, 30)
        except:
            days = 30
    else:
        days = 30  # Chưa bao giờ ôn = max staleness
    staleness = days * 2  # max = 60
    
    # 3. Status bonus: learning được ưu tiên cao nhất
    status_bonus = {'new': 8, 'learning': 20, 'learned': -15}.get(word.get('status', 'new'), 0)
    
    # 4. Recently failed boost: vừa sai gần đây được ưu tiên cao (decay 24h)
    recent_fail_boost = 0
    if word.get('last_failed_at'):
        try:
            hours = (datetime.now() - datetime.fromisoformat(word['last_failed_at'])).total_seconds() / 3600
            if hours < 24:
                recent_fail_boost = 35 * max(0, 1 - hours / 24)  # 35 → 0 theo thời gian
        except:
            pass
    
    # 5. Mastery reduction: đúng liên tiếp nhiều lần thì giảm priority
    streak = word.get('correct_streak', 0)
    mastery_reduction = min(streak * 3, 30)  # cap ở -30
    
    return accuracy_pressure + staleness + status_bonus + recent_fail_boost - mastery_reduction


def get_review_queue(db, n: int = 10, status_filter: str = 'all', 
                     exclude_ids: list = None, include_new_ratio: float = 0.2) -> list:
    """
    Lấy n từ theo priority để học trong phiên này.
    
    Args:
        n: số từ cần lấy
        status_filter: 'all' | 'new' | 'learning' | 'learned'
        exclude_ids: list word_id đã xem trong session (tránh lặp)
        include_new_ratio: tỉ lệ từ mới trong queue (0.0-1.0, default 20%)
    
    Returns:
        list[dict] đã sort theo priority DESC
    """
    exclude_ids = exclude_ids or []
    
    # Lấy tất cả từ phù hợp
    if status_filter == 'all':
        query = "SELECT * FROM words"
        words = [dict(r) for r in db.execute(query).fetchall()]
    else:
        query = "SELECT * FROM words WHERE status = ?"
        words = [dict(r) for r in db.execute(query, (status_filter,)).fetchall()]
    
    # Loại exclude_ids
    words = [w for w in words if w['id'] not in exclude_ids]
    
    if not words:
        return []
    
    # Tính priority cho mỗi từ
    for w in words:
        w['_priority'] = calculate_priority(w)
    
    # Tách new và non-new
    new_words     = [w for w in words if w['status'] == 'new']
    review_words  = [w for w in words if w['status'] != 'new']
    
    # Sort theo priority DESC
    new_words.sort(key=lambda x: x['_priority'], reverse=True)
    review_words.sort(key=lambda x: x['_priority'], reverse=True)
    
    # Mix theo ratio
    if status_filter == 'all':
        n_new    = min(int(n * include_new_ratio), len(new_words))
        n_review = min(n - n_new, len(review_words))
        # Nếu không đủ review words, bù bằng new words
        if n_review < n - n_new:
            n_new = min(n - n_review, len(new_words))
        queue = new_words[:n_new] + review_words[:n_review]
        # Sort queue according to priority to keep highest priority first
        queue.sort(key=lambda x: x['_priority'], reverse=True)
    else:
        words.sort(key=lambda x: x['_priority'], reverse=True)
        queue = words[:n]
    
    # Shuffle nhẹ trong nhóm priority cao (tránh predictable)
    import random
    if len(queue) > 3:
        top = queue[:max(1, len(queue)//2)]
        rest = queue[max(1, len(queue)//2):]
        random.shuffle(top)
        queue = top + rest
    
    # Xóa _priority khỏi kết quả
    for w in queue:
        w.pop('_priority', None)
    
    return queue


def calculate_mastery_score(word: dict) -> float:
    """
    Tính mastery score: phản ánh mức độ thực sự nhớ từ.
    Khác total_score (gamification), mastery_score dùng để đánh giá
    chất lượng học (fill đúng có giá trị hơn flashcard 5 sao x10).
    
    Trả về số 0-100.
    """
    total_reviews = (word.get('correct_count') or 0) + (word.get('wrong_count') or 0)
    if total_reviews == 0:
        return 0.0
    
    # Accuracy cơ bản
    accuracy = (word.get('correct_count') or 0) / total_reviews  # 0-1
    
    # Fill mode weight: fill đúng = strong recall, weight cao hơn
    # (self_correct_count từ fill mode)
    fill_bonus = min((word.get('self_correct_count') or 0) * 3, 20)
    fill_penalty = min((word.get('self_wrong_count') or 0) * 2, 15)
    
    # Review count factor: cần đủ data để tin tưởng
    confidence = min(math.log(1 + total_reviews) / math.log(11), 1.0)  # 0→1 khi review 0→10
    
    raw = (accuracy * 60 + fill_bonus - fill_penalty)
    return max(0.0, round(raw * confidence, 1))  # scale theo confidence


