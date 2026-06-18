import sys
import os

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def test_all():
    import sqlite3
    # Add local path to sys.path if not there
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database import init_db
    from scoring import apply_flashcard_rating, apply_matching_result, apply_fill_result, mark_as_learned
    
    # Setup in-memory DB
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    init_db(db)
    
    # Insert 1 test word
    db.execute("INSERT INTO words (word, translation, short_translation) VALUES ('test', 'thử nghiệm', 'thử nghiệm')")
    db.commit()
    word_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Test 1: Rate 1-4 không thay đổi status
    result = apply_flashcard_rating(db, word_id, 3)
    assert result['new_status'] == 'new', "Rate 3 không được thay đổi status"
    assert result['status_changed'] == False
    assert result['new_score'] == 3
    
    # Test 2: Rate 5 lần đầu → new → learning
    result = apply_flashcard_rating(db, word_id, 5)
    assert result['new_status'] == 'learning', "Rate 5 phải chuyển sang learning"
    assert result['status_changed'] == True
    assert result['new_score'] == 8  # 3 + 5
    
    # Test 3: Rate 5 lần 2 (đã learning) → status không đổi, chỉ cộng điểm
    result = apply_flashcard_rating(db, word_id, 5)
    assert result['new_status'] == 'learning', "Đã learning không đổi status"
    assert result['status_changed'] == False
    assert result['new_score'] == 13
    
    # Test 4: Điểm không âm
    for _ in range(10):
        result = apply_matching_result(db, word_id, False)  # -2 each time
    word = db.execute("SELECT total_score FROM words WHERE id=?", (word_id,)).fetchone()
    assert word['total_score'] == 0, "Điểm không bao giờ âm (phải được giới hạn ở 0)"
    
    # Test 5: mark_as_learned
    mark_as_learned(db, word_id)
    word = db.execute("SELECT status FROM words WHERE id=?", (word_id,)).fetchone()
    assert word['status'] == 'learned'
    
    # Test 6: Priority Queue test
    test_priority_queue()

    print("✅ Tất cả tests pass!")

def test_priority_queue():
    import sqlite3
    from database import init_db
    from scoring import calculate_priority, get_review_queue
    from datetime import datetime, timedelta
    
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    init_db(db)
    
    # Insert some words with different properties
    # Word 1: New word
    db.execute("""
        INSERT INTO words (id, word, translation, status, correct_count, wrong_count, last_reviewed, last_failed_at, correct_streak) 
        VALUES (1, 'new_word', 'từ mới', 'new', 0, 0, NULL, NULL, 0)
    """)
    # Word 2: Learning word, high wrong count, failed recently (hours < 24)
    yesterday = (datetime.now() - timedelta(hours=2)).isoformat()
    db.execute("""
        INSERT INTO words (id, word, translation, status, correct_count, wrong_count, last_reviewed, last_failed_at, correct_streak) 
        VALUES (2, 'failed_word', 'từ sai', 'learning', 1, 5, ?, ?, 0)
    """, (yesterday, yesterday))
    # Word 3: Learned word, high correct streak
    db.execute("""
        INSERT INTO words (id, word, translation, status, correct_count, wrong_count, last_reviewed, last_failed_at, correct_streak) 
        VALUES (3, 'mastered_word', 'từ thuộc', 'learned', 10, 0, ?, NULL, 5)
    """, (yesterday,))
    db.commit()
    
    # Verify calculate_priority
    p_new = calculate_priority(dict(db.execute("SELECT * FROM words WHERE id=1").fetchone()))
    p_fail = calculate_priority(dict(db.execute("SELECT * FROM words WHERE id=2").fetchone()))
    p_master = calculate_priority(dict(db.execute("SELECT * FROM words WHERE id=3").fetchone()))
    
    print(f"Priority - New: {p_new}, Failed: {p_fail}, Mastered: {p_master}")
    
    # Failed word should have much higher priority than mastered word
    assert p_fail > p_master, "Failed learning word should have higher priority than mastered word"
    
    # Test get_review_queue
    queue = get_review_queue(db, n=3, status_filter='all')
    assert len(queue) == 3, f"Expected 3 words, got {len(queue)}"
    
    # Test exclude_ids
    queue_ex = get_review_queue(db, n=3, status_filter='all', exclude_ids=[2])
    assert 2 not in [w['id'] for w in queue_ex], "Excluded ID should not be in queue"
    
    print("✓ Priority queue tests passed!")

if __name__ == '__main__':
    test_all()

