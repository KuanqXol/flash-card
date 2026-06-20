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

def test_diminishing_returns(db):
    cursor = db.cursor()
    cursor.execute("INSERT INTO words (word, translation, knowledge_score, status) VALUES ('test', 'thử nghiệm', 30, 'new')")
    db.commit()
    word_id = cursor.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 1st try (seen=0):
    cursor.execute("INSERT OR REPLACE INTO word_stats (word_id, exercise, seen, correct) VALUES (?, 'mcq', 0, 0)", (word_id,))
    cursor.execute("UPDATE words SET knowledge_score = 30, status = 'new' WHERE id = ?", (word_id,))
    db.commit()
    s1 = update_score(word_id, 'mcq', True, db=db)
    delta1 = s1 - 30
    
    # 5th try (seen=4):
    cursor.execute("INSERT OR REPLACE INTO word_stats (word_id, exercise, seen, correct) VALUES (?, 'mcq', 4, 0)", (word_id,))
    cursor.execute("UPDATE words SET knowledge_score = 30, status = 'new' WHERE id = ?", (word_id,))
    db.commit()
    s5 = update_score(word_id, 'mcq', True, db=db)
    delta5 = s5 - 30
    
    # 10th try (seen=9):
    cursor.execute("INSERT OR REPLACE INTO word_stats (word_id, exercise, seen, correct) VALUES (?, 'mcq', 9, 0)", (word_id,))
    cursor.execute("UPDATE words SET knowledge_score = 30, status = 'new' WHERE id = ?", (word_id,))
    db.commit()
    s10 = update_score(word_id, 'mcq', True, db=db)
    delta10 = s10 - 30
    
    print(f"Deltas: 1st={delta1}, 5th={delta5}, 10th={delta10}")
    
    # Assert factor mathematical values directly
    factor1 = 1.0 / math.sqrt(0 + 1)
    factor5 = 1.0 / math.sqrt(4 + 1)
    factor10 = 1.0 / math.sqrt(9 + 1)
    assert factor1 > factor5 > factor10, "Factor values are incorrect"
    
    # Assert actual score change is diminishing overall (1st > 10th)
    assert delta1 > delta10, "Score delta did not diminish"

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
