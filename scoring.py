import sqlite3
from datetime import datetime

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
    Returns: (new_score, status_changed, new_status)
    """
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    
    # 1. Lấy word hiện tại
    cursor.execute("SELECT total_score, status, has_been_rated_five FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Word with id {word_id} not found")
        
    old_score = row['total_score']
    old_status = row['status']
    old_has_five = row['has_been_rated_five']
    
    # 2. Tính new_score = MAX(0, old_score + delta)
    new_score = max(0, old_score + delta)
    
    # 3. Xác định has_been_rated_five (nếu rating == 5)
    new_has_five = 1 if (rating == 5 or old_has_five == 1) else 0
    
    # 4. UPDATE words SET total_score=?, review_count=review_count+1, last_reviewed=?, has_been_rated_five=?
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE words 
        SET total_score = ?, 
            review_count = review_count + 1, 
            last_reviewed = ?, 
            has_been_rated_five = ?
        WHERE id = ?
    """, (new_score, now_str, new_has_five, word_id))
    
    # 5. Gọi check_and_auto_upgrade(word_id) - logic implemented directly here
    status_changed = False
    new_status = old_status
    if new_has_five == 1 and old_status == 'new':
        cursor.execute("UPDATE words SET status = 'learning' WHERE id = ?", (word_id,))
        new_status = 'learning'
        status_changed = True
        
    # 6. INSERT vào review_history
    is_correct_val = None
    if is_correct is not None:
        is_correct_val = 1 if is_correct else 0
        
    cursor.execute("""
        INSERT INTO review_history (word_id, mode, score_delta, is_correct, rating, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (word_id, mode, delta, is_correct_val, rating, now_str))
    
    db.commit()
    
    # 7. Return kết quả
    return new_score, status_changed, new_status
