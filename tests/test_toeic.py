import sqlite3
import pytest
import sys
import os
import pandas as pd

# Add parent dir to sys.path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    init_db,
    get_toeic_questions,
    get_toeic_topics,
    insert_toeic_session,
    get_toeic_sessions
)
from import_toeic import import_toeic_from_xlsx

@pytest.fixture
def db():
    # Setup in-memory DB
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn

def test_toeic_db_helpers(db):
    # Insert questions manually to test helpers
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO toeic_questions (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Hiện tại đơn", "He ___ a book every day.", "read", "reads", "reading", "will read", "B", "Giải thích HTĐ", "Dịch nghĩa HTĐ"))
    cursor.execute("""
        INSERT INTO toeic_questions (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Quá khứ đơn", "He ___ a book yesterday.", "read", "reads", "reading", "will read", "A", "Giải thích QKĐ", "Dịch nghĩa QKĐ"))
    cursor.execute("""
        INSERT INTO toeic_questions (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Giới từ", "She is good ___ English.", "at", "in", "on", "for", "A", "Giải thích giới từ", "Dịch nghĩa giới từ"))
    cursor.execute("""
        INSERT INTO toeic_questions (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Từ vựng", "This is a ___ vocabulary test.", "simple", "simply", "simplest", "simplicity", "A", "Giải thích từ vựng", "Dịch nghĩa từ vựng"))
    db.commit()

    # Test topics query
    topics = get_toeic_topics(db)
    assert "Hiện tại đơn" in topics
    assert "Quá khứ đơn" in topics
    assert "Giới từ" in topics
    assert "Từ vựng" in topics
    assert len(topics) == 4

    # Test questions query
    all_qs = get_toeic_questions(db)
    assert len(all_qs) == 4
    
    # Test tenses filtering
    tenses_qs = get_toeic_questions(db, topic="tenses")
    assert len(tenses_qs) == 2
    tenses_topics = {q['topic'] for q in tenses_qs}
    assert "Hiện tại đơn" in tenses_topics
    assert "Quá khứ đơn" in tenses_topics

    # Test others filtering
    others_qs = get_toeic_questions(db, topic="others")
    assert len(others_qs) == 2
    others_topics = {q['topic'] for q in others_qs}
    assert "Giới từ" in others_topics
    assert "Từ vựng" in others_topics

    # Test specific topic filtering
    topic_qs = get_toeic_questions(db, topic="Giới từ")
    assert len(topic_qs) == 1
    assert topic_qs[0]['question'] == "She is good ___ English."

    # Test sessions
    sess_id = insert_toeic_session(db, "Tất cả", 10, 8, 80.0, 120, '[]')
    assert sess_id > 0

    sessions = get_toeic_sessions(db)
    assert len(sessions) == 1
    assert sessions[0]['accuracy'] == 80.0
    assert sessions[0]['correct_count'] == 8
    assert sessions[0]['total_questions'] == 10
    assert sessions[0]['duration_seconds'] == 120

def test_excel_import(db, tmp_path):
    # Create a temporary excel file
    df = pd.DataFrame([{
        "Chu De": "Chia động từ",
        "Cau Hoi": "I ___ a student.",
        "Dap An A": "am",
        "Dap An B": "is",
        "Dap An C": "are",
        "Dap An D": "be",
        "Dap An Dung": "A",
        "Giai Thich": "I đi với am",
        "Dich Nghia": "Tôi là học sinh"
    }])
    
    xlsx_file = tmp_path / "test_import.xlsx"
    df.to_excel(xlsx_file, index=False)
    
    db_file = tmp_path / "test_flashcards.db"
    
    import database
    original_db_name = database.DB_NAME
    database.DB_NAME = str(db_file)
    
    try:
        res = import_toeic_from_xlsx(str(xlsx_file))
        assert res['imported'] == 1
        assert res['total'] == 1
        
        # Verify db contents
        conn = database.get_db()
        qs = get_toeic_questions(conn)
        assert len(qs) == 1
        assert qs[0]['question'] == "I ___ a student."
        assert qs[0]['correct_option'] == "A"
        conn.close()
    finally:
        database.DB_NAME = original_db_name

def test_toeic_stats_integration(tmp_path):
    import database
    from database import get_stats, init_db, insert_toeic_session
    
    db_file = tmp_path / "test_stats_flashcards.db"
    original_db_name = database.DB_NAME
    database.DB_NAME = str(db_file)
    
    try:
        conn = database.get_db()
        init_db(conn)
        
        # Initially toeic reviews should be 0
        stats = get_stats()
        assert stats['practice_stats']['toeic']['total_reviews'] == 0
        
        # Insert a session
        insert_toeic_session(conn, "Hiện tại đơn", 10, 8, 80.0, 100, '[]')
        
        # Query stats again
        stats = get_stats()
        assert stats['practice_stats']['toeic']['total_reviews'] == 10
        assert stats['practice_stats']['toeic']['total_correct'] == 8
        assert stats['practice_stats']['toeic']['accuracy'] == 80.0
        
        conn.close()
    finally:
        database.DB_NAME = original_db_name

def test_excel_import_positional(db, tmp_path):
    # Create an excel file with scrambled/different header names but exactly 9 columns
    df = pd.DataFrame([{
        "Random Col 1": "Liên từ",
        "Random Col 2": "___ he was tired, he finished his work.",
        "Random Col 3": "Although",
        "Random Col 4": "Because",
        "Random Col 5": "However",
        "Random Col 6": "Therefore",
        "Random Col 7": "A",
        "Random Col 8": "Although chỉ sự nhượng bộ",
        "Random Col 9": "Mặc dù anh ấy mệt..."
    }])
    
    xlsx_file = tmp_path / "test_scrambled_import.xlsx"
    df.to_excel(xlsx_file, index=False)
    
    db_file = tmp_path / "test_flashcards_scrambled.db"
    
    import database
    original_db_name = database.DB_NAME
    database.DB_NAME = str(db_file)
    
    try:
        res = import_toeic_from_xlsx(str(xlsx_file))
        assert res['imported'] == 1
        assert res['total'] == 1
        assert 'batch_name' in res
        
        # Verify db contents and batch name
        conn = database.get_db()
        qs = get_toeic_questions(conn)
        assert len(qs) == 1
        assert qs[0]['topic'] == "Liên từ"
        assert qs[0]['question'] == "___ he was tired, he finished his work."
        assert qs[0]['correct_option'] == "A"
        assert qs[0]['import_batch'] == res['batch_name']
        conn.close()
    finally:
        database.DB_NAME = original_db_name

def test_excel_import_column_mismatch(db, tmp_path):
    # Create an excel file with only 8 columns (which is invalid)
    df = pd.DataFrame([{
        "Col 1": "Liên từ",
        "Col 2": "___ he was tired, he finished his work.",
        "Col 3": "Although",
        "Col 4": "Because",
        "Col 5": "However",
        "Col 6": "Therefore",
        "Col 7": "A",
        "Col 8": "Although chỉ sự nhượng bộ"
    }])
    
    xlsx_file = tmp_path / "test_invalid_import.xlsx"
    df.to_excel(xlsx_file, index=False)
    
    with pytest.raises(ValueError) as excinfo:
        import_toeic_from_xlsx(str(xlsx_file))
    assert "Số lượng cột không đúng" in str(excinfo.value)

def test_wrong_questions_filtering(db):
    from database import get_toeic_questions, insert_toeic_session
    import json
    
    cursor = db.cursor()
    # Insert 3 questions
    cursor.execute("""
        INSERT INTO toeic_questions (id, topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (1, "Liên từ", "Q1", "A", "B", "C", "D", "A", "E1", "T1"))
    cursor.execute("""
        INSERT INTO toeic_questions (id, topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (2, "Giới từ", "Q2", "A", "B", "C", "D", "B", "E2", "T2"))
    cursor.execute("""
        INSERT INTO toeic_questions (id, topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (3, "Các thì", "Q3", "A", "B", "C", "D", "C", "E3", "T3"))
    db.commit()
    
    # Initially, wrong questions should be empty
    assert len(get_toeic_questions(db, topic="wrong_questions")) == 0
    
    # Insert session 1: user got Q1 wrong, Q2 correct
    details1 = [
        {"question_id": 1, "is_correct": False},
        {"question_id": 2, "is_correct": True}
    ]
    insert_toeic_session(db, "Tất cả", 2, 1, 50.0, 60, json.dumps(details1))
    
    # Now, Q1 should be in wrong questions
    wrong_qs = get_toeic_questions(db, topic="wrong_questions")
    assert len(wrong_qs) == 1
    assert wrong_qs[0]['id'] == 1
    
    # Insert session 2: user got Q1 correct (solved), Q3 wrong
    details2 = [
        {"question_id": 1, "is_correct": True},
        {"question_id": 3, "is_correct": False}
    ]
    insert_toeic_session(db, "Tất cả", 2, 1, 50.0, 60, json.dumps(details2))
    
    # Now, wrong questions should contain Q3, but Q1 should be removed
    wrong_qs = get_toeic_questions(db, topic="wrong_questions")
    assert len(wrong_qs) == 1
    assert wrong_qs[0]['id'] == 3
