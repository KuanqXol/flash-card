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
    
    print("✅ Tất cả tests pass!")

if __name__ == '__main__':
    test_all()
