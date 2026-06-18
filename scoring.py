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
    Delegates database updates to database.update_word_after_review.
    Returns: (new_score, status_changed, new_status)
    """
    from database import update_word_after_review
    updated_word, status_changed = update_word_after_review(
        db, word_id, delta, mode, rating=rating, is_correct=is_correct
    )
    return updated_word['total_score'], status_changed, updated_word['status']
