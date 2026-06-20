import sqlite3
from datetime import datetime
import math

SCORE_CONFIG = {
    'flashcard': {'correct': 1, 'wrong': 0},
    'matching':  {'correct': 2, 'wrong': -3},
    'mcq':       {'correct': 3, 'wrong': -2},
    'typing':    {'correct': 5, 'wrong': -1}
}

def _get_status_from_score(score: int) -> str:
    if 0 <= score <= 50:
        return 'new'
    elif 51 <= score <= 89:
        return 'learning'
    elif 90 <= score <= 100:
        return 'mastered'
    return 'new'

def update_score(word_id: int, exercise: str, is_correct: bool, db=None) -> int:
    """
    Updates the knowledge_score of a word based on exercise type and correctness.
    Applies diminishing returns factor based on seen_count.
    Handles mastered rules: no negative changes allowed.
    Updates status automatically.
    Returns: new_score
    """
    # Normalize fill to typing
    if exercise == 'fill':
        exercise = 'typing'
        
    if exercise not in SCORE_CONFIG:
        raise ValueError(f"Unknown exercise type: {exercise}")
        
    should_close = False
    if db is None:
        from database import get_db
        db = get_db()
        db.row_factory = sqlite3.Row
        should_close = True
        
    try:
        cursor = db.cursor()
        
        # 1. Fetch current word details
        cursor.execute("SELECT status, knowledge_score, total_score, correct_count, wrong_count, correct_streak, consecutive_wrong, needs_review, last_failed_at, self_correct_count, self_wrong_count FROM words WHERE id = ?", (word_id,))
        word = cursor.fetchone()
        if not word:
            raise ValueError(f"Word with id {word_id} not found")
            
        old_score = word['knowledge_score']
        if old_score is None:
            old_score = 30
        status = word['status']
        
        # 2. Get seen_count from word_stats (before updating stats)
        cursor.execute("SELECT seen FROM word_stats WHERE word_id = ? AND exercise = ?", (word_id, exercise))
        stat_row = cursor.fetchone()
        seen_count = stat_row['seen'] if stat_row else 0
        
        # 3. Calculate factor and delta
        factor = 1.0 / math.sqrt(seen_count + 1)
        base_delta = SCORE_CONFIG[exercise]['correct'] if is_correct else SCORE_CONFIG[exercise]['wrong']
        effective_delta = base_delta * factor
        
        # 4. Handle mastered word rules (no negative changes)
        if status == 'mastered' and effective_delta < 0:
            effective_delta = 0
            
        # 5. Compute new score
        new_score = max(0, min(100, int(round(old_score + effective_delta))))
        new_status = _get_status_from_score(new_score)
        
        # 6. Update word_stats
        # Flashcard seen count is updated on flip, other exercises are updated here
        seen_increment = 0 if exercise == 'flashcard' else 1
        correct_increment = 1 if is_correct else 0
        cursor.execute("""
            INSERT INTO word_stats (word_id, exercise, seen, correct)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(word_id, exercise) DO UPDATE SET
                seen = seen + ?,
                correct = correct + ?
        """, (word_id, exercise, seen_increment, correct_increment, seen_increment, correct_increment))
        
        # 7. Update other metrics to keep compatibility with dashboard/history
        now_str = datetime.now().isoformat()
        
        # correct/wrong count
        c_count_inc = 1 if is_correct else 0
        w_count_inc = 0 if not is_correct else 1
        
        # streak
        new_streak = (word['correct_streak'] or 0) + 1 if is_correct else 0
        new_consec_wrong = 0 if is_correct else (word['consecutive_wrong'] or 0) + 1
        
        last_failed_at = now_str if not is_correct else word['last_failed_at']
        
        # needs_review flag logic
        needs_review = word['needs_review'] or 0
        if new_consec_wrong >= 3:
            needs_review = 1
        if new_streak >= 2:
            needs_review = 0
            
        # Self evaluation counts
        self_c_inc = 1 if (exercise == 'typing' and is_correct) else 0
        self_w_inc = 1 if (exercise == 'typing' and not is_correct) else 0
        
        # total_score (gamification) update
        new_total_score = max(0, (word['total_score'] or 0) + base_delta)
        
        cursor.execute("""
            UPDATE words SET
                knowledge_score = ?,
                status = ?,
                total_score = ?,
                review_count = review_count + 1,
                correct_count = correct_count + ?,
                wrong_count = wrong_count + ?,
                correct_streak = ?,
                consecutive_wrong = ?,
                last_failed_at = ?,
                needs_review = ?,
                self_correct_count = self_correct_count + ?,
                self_wrong_count = self_wrong_count + ?,
                last_reviewed = ?
            WHERE id = ?
        """, (new_score, new_status, new_total_score, c_count_inc, w_count_inc,
              new_streak, new_consec_wrong, last_failed_at, needs_review,
              self_c_inc, self_w_inc, now_str, word_id))
        
        # 8. Record review history
        cursor.execute("""
            INSERT INTO review_history (word_id, mode, score_delta, is_correct, rating, reviewed_at)
            VALUES (?, ?, ?, ?, NULL, ?)
        """, (word_id, exercise, int(round(effective_delta)), 1 if is_correct else 0, now_str))
        
        if should_close:
            db.commit()
            
        return new_score
    except Exception as e:
        if should_close:
            db.rollback()
        raise e
    finally:
        if should_close:
            db.close()

def _apply_score_change(db: sqlite3.Connection, word_id: int, delta: int, mode: str, rating: int = None, is_correct: bool = None) -> tuple:
    """
    Apply generic score changes.
    """
    exercise = mode
    if exercise == 'fill':
        exercise = 'typing'
    is_correct_val = is_correct if is_correct is not None else (rating >= 4 if rating is not None else delta > 0)
    
    cursor = db.cursor()
    cursor.execute("SELECT status FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    old_status = row['status'] if row else 'new'
    
    if exercise in SCORE_CONFIG:
        new_score = update_score(word_id, exercise, is_correct_val, db=db)
    else:
        cursor.execute("SELECT knowledge_score FROM words WHERE id = ?", (word_id,))
        w_row = cursor.fetchone()
        old_k_score = w_row['knowledge_score'] if (w_row and w_row['knowledge_score'] is not None) else 30
        new_score = max(0, min(100, old_k_score + delta))
        new_status = _get_status_from_score(new_score)
        
        from database import update_word_after_review
        update_word_after_review(db, word_id, delta, mode, rating=rating, is_correct=is_correct)
        
        cursor.execute("UPDATE words SET knowledge_score = ?, status = ? WHERE id = ?", (new_score, new_status, word_id))
        
    cursor.execute("SELECT status FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    new_status = row['status'] if row else 'new'
    
    return new_score, new_status != old_status, new_status

def apply_flashcard_rating(db: sqlite3.Connection, word_id: int, rating: int) -> dict:
    """
    Apply flashcard rating for backward compatibility.
    """
    is_correct = rating >= 4
    
    cursor = db.cursor()
    cursor.execute("SELECT seen FROM word_stats WHERE word_id = ? AND exercise = 'flashcard'", (word_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO word_stats (word_id, exercise, seen, correct) VALUES (?, 'flashcard', 1, 0)", (word_id,))
    
    old_score_row = db.execute("SELECT knowledge_score, status FROM words WHERE id = ?", (word_id,)).fetchone()
    old_score = old_score_row['knowledge_score'] if (old_score_row and old_score_row['knowledge_score'] is not None) else 30
    old_status = old_score_row['status'] if old_score_row else 'new'
    
    new_score = update_score(word_id, 'flashcard', is_correct, db=db)
    
    word_row = db.execute("SELECT status FROM words WHERE id = ?", (word_id,)).fetchone()
    new_status = word_row['status']
    
    return {
        'new_score': new_score,
        'old_score': old_score,
        'status_changed': new_status != old_status,
        'new_status': new_status,
        'delta': 1 if is_correct else 0
    }

def apply_matching_result(db: sqlite3.Connection, word_id: int, is_correct: bool) -> dict:
    """
    Apply matching game result.
    """
    new_score = update_score(word_id, 'matching', is_correct, db=db)
    delta = SCORE_CONFIG['matching']['correct'] if is_correct else SCORE_CONFIG['matching']['wrong']
    return {
        'new_score': new_score,
        'delta': delta
    }

def apply_fill_result(db: sqlite3.Connection, word_id: int, is_correct: bool) -> dict:
    """
    Apply fill result.
    """
    new_score = update_score(word_id, 'typing', is_correct, db=db)
    delta = SCORE_CONFIG['typing']['correct'] if is_correct else SCORE_CONFIG['typing']['wrong']
    return {
        'new_score': new_score,
        'delta': delta
    }

def mark_as_learned(db: sqlite3.Connection, word_id: int) -> dict:
    """Manually mark a word as mastered (formerly learned)."""
    cursor = db.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("UPDATE words SET knowledge_score = 95, status = 'mastered' WHERE id = ?", (word_id,))
    cursor.execute("INSERT INTO word_events (word_id, event, timestamp) VALUES (?, ?, ?)", (word_id, 'manual_mastered', now_str))
    db.commit()
    return {'success': True}

def mark_as_learning(db: sqlite3.Connection, word_id: int) -> dict:
    """Reset a word status manually."""
    cursor = db.cursor()
    cursor.execute("SELECT status FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    if not row:
        return {'success': False, 'message': 'Word not found'}
    
    old_status = row['status']
    now_str = datetime.now().isoformat()
    
    if old_status == 'new':
        cursor.execute("UPDATE words SET knowledge_score = 55, status = 'learning' WHERE id = ?", (word_id,))
        cursor.execute("INSERT INTO word_events (word_id, event, timestamp) VALUES (?, ?, ?)", (word_id, 'start_learning', now_str))
    elif old_status == 'mastered':
        cursor.execute("UPDATE words SET knowledge_score = 70, status = 'learning' WHERE id = ?", (word_id,))
        cursor.execute("INSERT INTO word_events (word_id, event, timestamp) VALUES (?, ?, ?)", (word_id, 'unmastered', now_str))
    else:
        cursor.execute("UPDATE words SET status = 'learning' WHERE id = ?", (word_id,))
        
    db.commit()
    return {'success': True}

def apply_forgetting_decay(word_id: int, db=None) -> int or None:
    """
    Applies forgetting decay based on last_reviewed date.
    Returns: new_score or None if no decay was applied.
    """
    should_close = False
    if db is None:
        from database import get_db
        db = get_db()
        db.row_factory = sqlite3.Row
        should_close = True
        
    try:
        cursor = db.cursor()
        cursor.execute("SELECT status, knowledge_score, last_reviewed FROM words WHERE id = ?", (word_id,))
        word = cursor.fetchone()
        if not word:
            return None
            
        status = word['status']
        if status == 'mastered':
            return None
            
        last_reviewed = word['last_reviewed']
        if not last_reviewed:
            return None
            
        try:
            last_reviewed_dt = datetime.fromisoformat(last_reviewed)
            days = (datetime.now() - last_reviewed_dt).days
        except Exception:
            return None
            
        decay = 0
        if 30 <= days <= 59:
            decay = -5
        elif 60 <= days <= 89:
            decay = -10
        elif days >= 90:
            decay = -15
            
        if decay < 0:
            old_score = word['knowledge_score'] if word['knowledge_score'] is not None else 30
            new_score = max(0, old_score + decay)
            new_status = _get_status_from_score(new_score)
            now_str = datetime.now().isoformat()
            
            cursor.execute("""
                UPDATE words SET
                    knowledge_score = ?,
                    status = ?,
                    last_reviewed = ?
                WHERE id = ?
            """, (new_score, new_status, now_str, word_id))
            
            if should_close:
                db.commit()
            return new_score
            
        return None
    except Exception as e:
        if should_close:
            db.rollback()
        raise e
    finally:
        if should_close:
            db.close()

def get_practice_queue(exercise: str, limit: int = 10, db=None) -> list:
    """
    Retrieves a list of word IDs for practice.
    Excludes words with 'mastered' status.
    Prioritizes words with the lowest knowledge_score.
    Applies forgetting decay on fetch.
    Returns: list[word_id]
    """
    should_close = False
    if db is None:
        from database import get_db
        db = get_db()
        db.row_factory = sqlite3.Row
        should_close = True
        
    try:
        cursor = db.cursor()
        
        # 1. Fetch non-mastered words to apply forgetting decay
        cursor.execute("SELECT id, status, last_reviewed FROM words WHERE status != 'mastered'")
        words = [dict(r) for r in cursor.fetchall()]
        
        for w in words:
            apply_forgetting_decay(w['id'], db=db)
            
        # 2. Re-fetch and order by knowledge_score ascending, prioritizing lowest scores
        cursor.execute("""
            SELECT id FROM words 
            WHERE status != 'mastered' 
            ORDER BY knowledge_score ASC, id ASC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        return [r['id'] for r in rows]
    except Exception as e:
        raise e
    finally:
        if should_close:
            db.commit()
            db.close()

def calculate_priority(word) -> float:
    """
    Tính priority score: score cao hơn = cần ôn hơn.
    """
    if not isinstance(word, dict):
        word = dict(word)
        
    total_reviews = (word.get('correct_count') or 0) + (word.get('wrong_count') or 0)
    
    if total_reviews > 0:
        wrong_ratio = (word.get('wrong_count') or 0) / total_reviews
    else:
        wrong_ratio = 0.5
    accuracy_pressure = wrong_ratio * 50
    
    if word.get('last_reviewed'):
        try:
            delta = datetime.now() - datetime.fromisoformat(word['last_reviewed'])
            days = min(delta.total_seconds() / 86400, 30)
        except:
            days = 30
    else:
        days = 30
    staleness = days * 2
    
    # Map both 'learned' and 'mastered' to same reduction
    status_bonus = {'new': 8, 'learning': 20, 'mastered': -15, 'learned': -15}.get(word.get('status', 'new'), 0)
    
    recent_fail_boost = 0
    if word.get('last_failed_at'):
        try:
            hours = (datetime.now() - datetime.fromisoformat(word['last_failed_at'])).total_seconds() / 3600
            if hours < 24:
                recent_fail_boost = 35 * max(0, 1 - hours / 24)
        except:
            pass
    
    streak = word.get('correct_streak', 0)
    mastery_reduction = min(streak * 3, 30)
    
    return accuracy_pressure + staleness + status_bonus + recent_fail_boost - mastery_reduction

def get_review_queue(db, n: int = 10, status_filter: str = 'all', 
                      exclude_ids: list = None, include_new_ratio: float = 0.2) -> list:
    """
    Lấy n từ theo priority để học trong phiên này.
    """
    exclude_ids = exclude_ids or []
    
    if status_filter == 'all':
        query = "SELECT * FROM words"
        words = [dict(r) for r in db.execute(query).fetchall()]
    else:
        sf = 'mastered' if status_filter == 'learned' else status_filter
        query = "SELECT * FROM words WHERE status = ?"
        words = [dict(r) for r in db.execute(query, (sf,)).fetchall()]
    
    words = [w for w in words if w['id'] not in exclude_ids]
    
    if not words:
        return []
    
    for w in words:
        w['_priority'] = calculate_priority(w)
    
    new_words     = [w for w in words if w['status'] == 'new']
    review_words  = [w for w in words if w['status'] != 'new']
    
    new_words.sort(key=lambda x: x['_priority'], reverse=True)
    review_words.sort(key=lambda x: x['_priority'], reverse=True)
    
    if status_filter == 'all':
        n_new    = min(int(n * include_new_ratio), len(new_words))
        n_review = min(n - n_new, len(review_words))
        if n_review < n - n_new:
            n_new = min(n - n_review, len(new_words))
        queue = new_words[:n_new] + review_words[:n_review]
        queue.sort(key=lambda x: x['_priority'], reverse=True)
    else:
        words.sort(key=lambda x: x['_priority'], reverse=True)
        queue = words[:n]
    
    import random
    if len(queue) > 3:
        top = queue[:max(1, len(queue)//2)]
        rest = queue[max(1, len(queue)//2):]
        random.shuffle(top)
        queue = top + rest
    
    for w in queue:
        w.pop('_priority', None)
    
    return queue

def calculate_mastery_score(word) -> float:
    """
    Tính mastery score: phản ánh mức độ thực sự nhớ từ.
    """
    if not isinstance(word, dict):
        word = dict(word)
        
    total_reviews = (word.get('correct_count') or 0) + (word.get('wrong_count') or 0)
    if total_reviews == 0:
        return 0.0
    
    accuracy = (word.get('correct_count') or 0) / total_reviews
    
    fill_bonus = min((word.get('self_correct_count') or 0) * 3, 20)
    fill_penalty = min((word.get('self_wrong_count') or 0) * 2, 15)
    
    confidence = min(math.log(1 + total_reviews) / math.log(11), 1.0)
    
    raw = (accuracy * 60 + fill_bonus - fill_penalty)
    return max(0.0, round(raw * confidence, 1))
