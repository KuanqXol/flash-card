import sqlite3
import pytest
from datetime import datetime, timedelta
import math
import sys
import os

# Add parent dir to sys.path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db
from scoring import (
    update_score,
    apply_forgetting_decay,
    get_practice_queue,
    _get_status_from_score,
    SCORE_CONFIG
)

@pytest.fixture
def db():
    # Setup in-memory DB
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn

def test_new_scoring_formula(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('test', 'thử nghiệm', 30, 'new')")
    db.commit()
    word_id = cursor.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 1. Reset everything to 0
    cursor.execute("""
        UPDATE words SET 
            flashcard_en_vi_seen = 0, flashcard_en_vi_correct = 0, flashcard_en_vi_wrong = 0,
            flashcard_vi_en_seen = 0, flashcard_vi_en_correct = 0, flashcard_vi_en_wrong = 0,
            mcq_en_vi_seen = 0, mcq_en_vi_correct = 0, mcq_en_vi_wrong = 0,
            mcq_vi_en_seen = 0, mcq_vi_en_correct = 0, mcq_vi_en_wrong = 0,
            matching_seen = 0, matching_correct = 0, matching_wrong = 0,
            fill_seen = 0, fill_correct = 0, fill_wrong = 0,
            en_vi_score = 0, vi_en_score = 0,
            knowledge_score = 30, status = 'new' 
        WHERE id = ?
    """, (word_id,))
    db.commit()

    # 2. Add a flashcard correct review
    cursor.execute("UPDATE words SET flashcard_en_vi_seen = 1, flashcard_en_vi_correct = 0 WHERE id = ?", (word_id,))
    db.commit()
    s1 = update_score(word_id, 'flashcard', True, db=db, direction='en_vi')
    # seen_count = 1. fc_ev_seen = 1, fc_ev_corr = 1.
    # ev_score = 0.40 * 100 = 40. vi_en_score = 0.
    # seen_score = ln(2)/ln(31)*100 = 20.18.
    # final_score = 0.45 * 40 + 0.45 * 0 + 0.10 * 20.18 = 18.0 + 2.0 = 20.
    assert s1 == 20

    # 3. Add more exercise stats and test recalculation
    cursor.execute("""
        UPDATE words SET
            flashcard_en_vi_seen = 5, flashcard_en_vi_correct = 5,
            flashcard_vi_en_seen = 5, flashcard_vi_en_correct = 5,
            mcq_en_vi_seen = 5, mcq_en_vi_correct = 5,
            mcq_vi_en_seen = 5, mcq_vi_en_correct = 5,
            matching_seen = 5, matching_correct = 5,
            fill_seen = 5, fill_correct = 4
        WHERE id = ?
    """, (word_id,))
    db.commit()
    # Now seen_count = 30.
    # s2 adds matching_seen=6, mat_corr=6 -> seen=31.
    # fc_ev_acc = 100.0, mcq_ev_acc = 100.0, mat_acc = 100.0 => ev_score = 100.
    # fc_ve_acc = 100.0, mcq_ve_acc = 100.0, fill_acc = 80.0 => vi_en_score = 94.
    # seen_score = ln(32)/ln(31)*100 = 100.9 -> clamped to 100.
    # final_score = 0.45 * 100 + 0.45 * 94 + 0.10 * 100 = 45 + 42.3 + 10 = 97.3 -> 97.
    s2 = update_score(word_id, 'matching', True, db=db)
    assert s2 == 97

def test_score_clamps(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('test', 'thử nghiệm', 98, 'mastered')")
    db.commit()
    word_id = cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Score should clamp to 100
    s_high = update_score(word_id, 'mcq', True, db=db)
    assert s_high <= 100
    
    # Score should clamp to 0
    cursor.execute("UPDATE words SET knowledge_score = 1, status = 'new' WHERE id = ?", (word_id,))
    db.commit()
    s_low = update_score(word_id, 'mcq', False, db=db)
    assert s_low >= 0

def test_mastered_word_no_penalty(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('mastered_word', 'đã thuộc', 95, 'mastered')")
    db.commit()
    word_id = cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    s_after = update_score(word_id, 'mcq', False, db=db)
    assert s_after == 95, f"Mastered word score was reduced from 95 to {s_after}"
    
    hundred_days_ago = (datetime.now() - timedelta(days=100)).isoformat()
    cursor.execute("UPDATE words SET last_reviewed = ? WHERE id = ?", (hundred_days_ago, word_id))
    db.commit()
    
    decay_result = apply_forgetting_decay(word_id, db=db)
    assert decay_result is None
    word = cursor.execute("SELECT knowledge_score FROM words WHERE id = ?", (word_id,)).fetchone()
    assert word['knowledge_score'] == 95

def test_forgetting_decay(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('decay_word', 'decay', 80, 'learning')")
    db.commit()
    word_id = cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # 1. 30-59 days -> score -= 5
    thirty_days_ago = (datetime.now() - timedelta(days=35)).isoformat()
    cursor.execute("UPDATE words SET knowledge_score = 80, last_reviewed = ? WHERE id = ?", (thirty_days_ago, word_id))
    db.commit()
    res = apply_forgetting_decay(word_id, db=db)
    assert res == 75
    
    # 2. 60-89 days -> score -= 10
    sixty_days_ago = (datetime.now() - timedelta(days=65)).isoformat()
    cursor.execute("UPDATE words SET knowledge_score = 80, last_reviewed = ? WHERE id = ?", (sixty_days_ago, word_id))
    db.commit()
    res = apply_forgetting_decay(word_id, db=db)
    assert res == 70
    
    # 3. >= 90 days -> score -= 15
    ninety_days_ago = (datetime.now() - timedelta(days=95)).isoformat()
    cursor.execute("UPDATE words SET knowledge_score = 80, last_reviewed = ? WHERE id = ?", (ninety_days_ago, word_id))
    db.commit()
    res = apply_forgetting_decay(word_id, db=db)
    assert res == 65

def test_migration_mapping():
    def map_score(avg):
        if avg <= 2.0:
            return 20
        elif avg <= 3.0:
            return 35
        elif avg <= 4.0:
            return 58
        else:
            return 75
            
    assert map_score(1.0) == 20
    assert map_score(2.0) == 20
    assert map_score(3.0) == 35
    assert map_score(4.0) == 58
    assert map_score(5.0) == 75

def test_practice_queue_excludes_mastered(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('word1', '1', 30, 'learning')")
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('word2', '2', 95, 'mastered')")
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('word3', '3', 10, 'new')")
    db.commit()
    
    queue = get_practice_queue('mcq', limit=5, db=db)
    cursor.execute("SELECT id FROM words WHERE word = 'word2'")
    mastered_id = cursor.fetchone()[0]
    assert mastered_id not in queue
    
    cursor.execute("SELECT id FROM words WHERE word = 'word3'")
    new_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM words WHERE word = 'word1'")
    learning_id = cursor.fetchone()[0]
    
    assert new_id in queue
    assert learning_id in queue
    assert queue.index(new_id) < queue.index(learning_id)
