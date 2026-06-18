import sqlite3
import os
from datetime import datetime

DB_NAME = 'flashcards.db'

def get_db():
    """Returns a sqlite3 connection object with sqlite3.Row row_factory."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn=None):
    """Initializes the SQLite database schemas for words, review_history, word_pos, and settings tables."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    cursor = conn.cursor()
    
    # Create words table (v2 schema)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL,
        phonetic TEXT,
        translation TEXT NOT NULL,        -- Nghĩa đầy đủ từ CSV
        short_translation TEXT,           -- Nghĩa rút gọn để hiển thị game
        date_added TEXT,
        status TEXT DEFAULT 'new',        -- 'new' | 'learning' | 'learned'
        total_score INTEGER DEFAULT 0,
        review_count INTEGER DEFAULT 0,
        has_been_rated_five INTEGER DEFAULT 0,  -- 1 nếu từng rate 5 sao
        last_reviewed TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        correct_count INTEGER DEFAULT 0,
        wrong_count INTEGER DEFAULT 0,
        self_correct_count INTEGER DEFAULT 0,
        self_wrong_count INTEGER DEFAULT 0,
        last_failed_at TEXT,
        correct_streak INTEGER DEFAULT 0,
        consecutive_wrong INTEGER DEFAULT 0,
        needs_review INTEGER DEFAULT 0
    );
    ''')
    
    # Create review_history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS review_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        mode TEXT NOT NULL,               -- 'flashcard' | 'matching' | 'fill'
        score_delta INTEGER NOT NULL,
        is_correct INTEGER,               -- 1=đúng, 0=sai, NULL=flashcard
        rating INTEGER,                   -- 1-5, chỉ cho flashcard
        reviewed_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (word_id) REFERENCES words(id)
    );
    ''')
    
    # Create word_pos table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS word_pos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        pos TEXT,            -- 'n', 'v', 'adj', 'adv', 'prep', 'conj', 'pron', NULL (cho phrase)
        meaning TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    );
    ''')
    
    # Create settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );
    ''')
    
    # Insert default settings
    defaults = [
        ('daily_goal', '20'),
        ('session_size', '10'),
        ('matching_pairs', '6'),
        ('new_word_ratio', '0.2'),
        ('theme', 'light'),
    ]
    for key, value in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        
    conn.commit()
    if should_close:
        conn.close()

def get_word_by_id(word_id):
    """Retrieves a single word by its ID. Returns dict or None."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM words WHERE id = ?', (word_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_words_by_status(status):
    """Retrieves words matching status ('new', 'learning', 'learned', or 'all'). Returns list[dict]."""
    conn = get_db()
    cursor = conn.cursor()
    if status == 'all':
        cursor.execute('SELECT * FROM words ORDER BY id DESC')
    else:
        cursor.execute('SELECT * FROM words WHERE status = ? ORDER BY id DESC', (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_random_words(n, status=None, exclude_id=None):
    """Retrieves n random words, optionally filtered by status and excluding a specific word ID. Returns list[dict]."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Normalize 'all' status to None
    if status == 'all':
        status = None
        
    if status:
        if exclude_id is not None:
            cursor.execute('SELECT * FROM words WHERE status = ? AND id != ? ORDER BY RANDOM() LIMIT ?', (status, exclude_id, n))
        else:
            cursor.execute('SELECT * FROM words WHERE status = ? ORDER BY RANDOM() LIMIT ?', (status, n))
    else:
        if exclude_id is not None:
            cursor.execute('SELECT * FROM words WHERE id != ? ORDER BY RANDOM() LIMIT ?', (exclude_id, n))
        else:
            cursor.execute('SELECT * FROM words ORDER BY RANDOM() LIMIT ?', (n,))
            
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_word_after_review(db_or_id, word_id=None, delta=None, mode=None, rating=None, is_correct=None):
    """
    Cập nhật word sau 1 lần review.
    Supports two signatures:
      - update_word_after_review(word_id, delta, mode, rating=None, is_correct=None)
      - update_word_after_review(db, word_id, delta, mode, rating=None, is_correct=None)
    """
    if isinstance(db_or_id, (int, str)):
        # Signature: update_word_after_review(word_id, delta, mode, rating, is_correct)
        word_id_val = int(db_or_id)
        delta_val = word_id
        mode_val = delta
        db = get_db()
        db.row_factory = sqlite3.Row
        should_close = True
    else:
        # Signature: update_word_after_review(db, word_id, delta, mode, rating, is_correct)
        db = db_or_id
        word_id_val = word_id
        delta_val = delta
        mode_val = mode
        should_close = False
        
    try:
        now = datetime.now().isoformat()
        
        # Lấy word hiện tại
        word = db.execute("SELECT * FROM words WHERE id=?", (word_id_val,)).fetchone()
        if not word:
            return False if should_close else (None, False)
            
        # Tính new_score (không âm)
        new_score = max(0, word['total_score'] + delta_val)
        
        # Xác định đúng/sai (flashcard: đúng nếu rating >= 4)
        effective_correct = is_correct
        if mode_val == 'flashcard' and rating is not None:
            effective_correct = rating >= 4
        
        # Cập nhật correct/wrong counts
        if effective_correct is True:
            correct_delta = 1
            wrong_delta = 0
            new_streak = (word['correct_streak'] or 0) + 1
            new_consec_wrong = 0
            fail_at = word['last_failed_at']  # giữ nguyên
        elif effective_correct is False:
            correct_delta = 0
            wrong_delta = 1
            new_streak = 0
            new_consec_wrong = (word['consecutive_wrong'] or 0) + 1
            fail_at = now
        else:
            correct_delta = 0
            wrong_delta = 0
            new_streak = word['correct_streak'] or 0
            new_consec_wrong = word['consecutive_wrong'] or 0
            fail_at = word['last_failed_at']
        
        # Self-evaluation (fill mode)
        self_correct_delta = 1 if (mode_val == 'fill' and is_correct is True) else 0
        self_wrong_delta   = 1 if (mode_val == 'fill' and is_correct is False) else 0
        
        # Soft-flag needs_review nếu consecutive_wrong >= 3
        needs_review = 1 if new_consec_wrong >= 3 else (word['needs_review'] or 0)
        # Reset needs_review nếu correct_streak >= 2
        if new_streak >= 2:
            needs_review = 0
        
        # Flashcard rate 5 → set has_been_rated_five
        rated_five = word['has_been_rated_five'] or 0
        if mode_val == 'flashcard' and rating == 5:
            rated_five = 1
        
        db.execute("""
            UPDATE words SET
                total_score        = ?,
                review_count       = review_count + 1,
                correct_count      = correct_count + ?,
                wrong_count        = wrong_count + ?,
                self_correct_count = self_correct_count + ?,
                self_wrong_count   = self_wrong_count + ?,
                correct_streak     = ?,
                consecutive_wrong  = ?,
                last_failed_at     = ?,
                needs_review       = ?,
                has_been_rated_five= ?,
                last_reviewed      = ?
            WHERE id = ?
        """, (new_score, correct_delta, wrong_delta, self_correct_delta, self_wrong_delta,
              new_streak, new_consec_wrong, fail_at, needs_review, rated_five, now, word_id_val))
        
        # Ghi review_history
        db.execute("""
            INSERT INTO review_history (word_id, mode, score_delta, is_correct, rating, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (word_id_val, mode_val, delta_val, 1 if is_correct else (0 if is_correct is False else None), rating, now))
        
        db.commit()
        
        # Auto-upgrade new → learning nếu đủ điều kiện
        status_changed = False
        if not should_close:
            status_changed = check_and_auto_upgrade(db, word_id_val)
        
        updated_word = db.execute("SELECT * FROM words WHERE id=?", (word_id_val,)).fetchone()
        
        if should_close:
            return True
        return dict(updated_word), status_changed
    except Exception as e:
        db.rollback()
        raise e
    finally:
        if should_close:
            db.close()

def update_word_status(word_id, new_status):
    """Updates the status of a word."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE words SET status = ? WHERE id = ?', (new_status, word_id))
    conn.commit()
    conn.close()

def check_and_auto_upgrade(db_or_id, word_id=None):
    """
    Upgrades word status to 'learning' if it has been rated five and status is 'new'.
    Supports both signatures: (word_id) and (db, word_id).
    """
    if word_id is None:
        word_id = db_or_id
        db = get_db()
        should_close = True
    else:
        db = db_or_id
        should_close = False
        
    try:
        cursor = db.cursor()
        cursor.execute('SELECT status, has_been_rated_five FROM words WHERE id = ?', (word_id,))
        row = cursor.fetchone()
        if not row:
            return False

        if row['has_been_rated_five'] == 1 and row['status'] == 'new':
            cursor.execute("UPDATE words SET status = 'learning' WHERE id = ?", (word_id,))
            db.commit()
            return True
        return False
    finally:
        if should_close:
            db.close()

def get_stats():
    """Returns a dict of database aggregate statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get status counts
    cursor.execute("SELECT status, COUNT(*) as cnt FROM words GROUP BY status")
    rows = cursor.fetchall()
    
    counts = {'new': 0, 'learning': 0, 'learned': 0}
    for r in rows:
        if r['status'] in counts:
            counts[r['status']] = r['cnt']
            
    # Total words count
    cursor.execute("SELECT COUNT(*) FROM words")
    row_count = cursor.fetchone()
    total = row_count[0] if row_count else 0
    
    # Reviewed today count
    cursor.execute("SELECT COUNT(*) FROM words WHERE DATE(last_reviewed) = DATE('now', 'localtime')")
    row_today = cursor.fetchone()
    reviewed_today = row_today[0] if row_today else 0
    
    # Total score sum
    cursor.execute("SELECT SUM(total_score) FROM words")
    row_score = cursor.fetchone()
    total_score_sum = row_score[0] if (row_score and row_score[0] is not None) else 0
    
    # Needs review count
    cursor.execute("SELECT COUNT(*) FROM words WHERE needs_review = 1")
    row_review = cursor.fetchone()
    needs_review_cnt = row_review[0] if row_review else 0
    
    conn.close()
    
    return {
        'new': counts['new'],
        'learning': counts['learning'],
        'learned': counts['learned'],
        'total': total,
        'reviewed_today': reviewed_today,
        'total_score_sum': total_score_sum,
        'needs_review': needs_review_cnt
    }

def get_setting(db, key: str, default: str = '') -> str:
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row['value'] if row else default

def set_setting(db, key: str, value: str):
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value)
    )
    db.commit()

