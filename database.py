import sqlite3
import os

DB_NAME = 'flashcards.db'

def get_db():
    """Returns a sqlite3 connection object with sqlite3.Row row_factory."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database schemas for words and review_history tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create words table
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
        created_at TEXT DEFAULT (datetime('now','localtime'))
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
    
    conn.commit()
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

def update_word_after_review(word_id, delta, mode, rating=None, is_correct=None):
    """Updates total_score, review_count, last_reviewed, has_been_rated_five and logs to review_history."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # 1. Fetch current word to modify its score and rate
        cursor.execute('SELECT total_score, has_been_rated_five FROM words WHERE id = ?', (word_id,))
        row = cursor.fetchone()
        if not row:
            return False

        current_score = row['total_score']
        current_has_five = row['has_been_rated_five']

        new_score = max(0, current_score + delta)
        new_has_five = current_has_five
        if rating == 5:
            new_has_five = 1

        # 2. Update words table
        cursor.execute('''
            UPDATE words 
            SET total_score = ?, 
                review_count = review_count + 1, 
                has_been_rated_five = ?, 
                last_reviewed = datetime('now', 'localtime') 
            WHERE id = ?
        ''', (new_score, new_has_five, word_id))

        # Handle is_correct input normalization
        is_correct_val = None
        if is_correct is not None:
            is_correct_val = 1 if is_correct else 0

        # 3. Insert review history record
        cursor.execute('''
            INSERT INTO review_history (word_id, mode, score_delta, is_correct, rating)
            VALUES (?, ?, ?, ?, ?)
        ''', (word_id, mode, delta, is_correct_val, rating))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_word_status(word_id, new_status):
    """Updates the status of a word."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE words SET status = ? WHERE id = ?', (new_status, word_id))
    conn.commit()
    conn.close()

def check_and_auto_upgrade(word_id):
    """Upgrades word status to 'learning' if it has been rated five and status is 'new'."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT status, has_been_rated_five FROM words WHERE id = ?', (word_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    if row['has_been_rated_five'] == 1 and row['status'] == 'new':
        cursor.execute("UPDATE words SET status = 'learning' WHERE id = ?", (word_id,))
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False

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
    
    conn.close()
    
    return {
        'new': counts['new'],
        'learning': counts['learning'],
        'learned': counts['learned'],
        'total': total,
        'reviewed_today': reviewed_today,
        'total_score_sum': total_score_sum
    }
