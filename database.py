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


# ═══ FILTERS CONFIGURATION ═══
FILTERS = {
  # ═══ NHÓM THỜI GIAN ═══
  'added_today': {
    'label': 'Thêm hôm nay',
    'group': 'time',
    'sql': "date(date_added) = date('now','localtime')",
    'pool_mode': False,
  },
  'added_this_week': {
    'label': 'Thêm tuần này',
    'group': 'time',
    'sql': "date(date_added) >= date('now','-7 days','localtime')",
    'pool_mode': False,
  },
  'not_reviewed_today': {
    'label': 'Chưa ôn hôm nay',
    'group': 'time',
    'sql': "(last_reviewed IS NULL OR date(last_reviewed) < date('now','localtime'))",
    'pool_mode': False,
  },
  'reviewed_today': {
    'label': 'Đã ôn hôm nay',
    'group': 'time',
    'sql': "date(last_reviewed) = date('now','localtime')",
    'pool_mode': False,
  },
  'not_reviewed_3days': {
    'label': 'Chưa ôn 3 ngày',
    'group': 'time',
    'sql': "(last_reviewed IS NULL OR last_reviewed < datetime('now','-3 days','localtime'))",
    'pool_mode': False,
  },
  'not_reviewed_7days': {
    'label': 'Chưa ôn 7 ngày',
    'group': 'time',
    'sql': "(last_reviewed IS NULL OR last_reviewed < datetime('now','-7 days','localtime'))",
    'pool_mode': False,
  },
  'failed_today': {
    'label': 'Vừa mới sai (hôm nay)',
    'group': 'time',
    'sql': "date(last_failed_at) = date('now','localtime')",
    'pool_mode': False,
  },
  'failed_24h': {
    'label': 'Vừa mới sai (24h)',
    'group': 'time',
    'sql': "last_failed_at >= datetime('now','-24 hours','localtime')",
    'pool_mode': False,
  },

  # ═══ NHÓM KẾT HỢP STATUS + THỜI GIAN ═══
  'new_today': {
    'label': 'Từ mới — thêm hôm nay',
    'group': 'combo',
    'sql': "status = 'new' AND date(date_added) = date('now','localtime')",
    'pool_mode': False,
  },
  'learning_today': {
    'label': 'Đang học — ôn hôm nay',
    'group': 'combo',
    'sql': "status = 'learning' AND date(last_reviewed) = date('now','localtime')",
    'pool_mode': False,
  },
  'learning_not_today': {
    'label': 'Đang học — chưa ôn hôm nay',
    'group': 'combo',
    'sql': "status = 'learning' AND (last_reviewed IS NULL OR date(last_reviewed) < date('now','localtime'))",
    'pool_mode': False,
  },
  'needs_review': {
    'label': 'Cần ôn lại (⚠️ flag)',
    'group': 'combo',
    'sql': "needs_review = 1",
    'pool_mode': False,
  },

  # ═══ NHÓM HIỆU SUẤT — Pool mode: lấy N từ → shuffle ═══
  'lowest_score': {
    'label': 'Điểm thấp nhất',
    'group': 'performance',
    'sql': "status != 'learned'",
    'order': 'total_score ASC',
    'pool_size': 20,
    'pool_mode': True,   # ← lấy top N rồi shuffle
  },
  'lowest_accuracy': {
    'label': 'Accuracy thấp nhất',
    'group': 'performance',
    'sql': "review_count >= 3",  # cần đủ data mới so sánh accuracy
    'order': "(correct_count * 1.0 / NULLIF(review_count, 0)) ASC",
    'pool_size': 20,
    'pool_mode': True,
  },
  'most_wrong': {
    'label': 'Sai nhiều nhất',
    'group': 'performance',
    'sql': "wrong_count > 0",
    'order': 'wrong_count DESC',
    'pool_size': 20,
    'pool_mode': True,
  },
  'never_reviewed': {
    'label': 'Chưa ôn lần nào',
    'group': 'performance',
    'sql': "review_count = 0",
    'pool_mode': False,
  },
  'danger_words': {
    'label': 'Từ nguy hiểm',
    'description': 'Ôn nhiều nhưng vẫn hay sai',
    'group': 'performance',
    'sql': "review_count > 5 AND (correct_count * 1.0 / NULLIF(review_count, 0)) < 0.5",
    'pool_mode': False,
  },

  # ═══ SMART ═══
  'smart_priority': {
    'label': 'Ưu tiên thông minh',
    'description': 'Dùng priority algorithm từ scoring.py',
    'group': 'smart',
    'sql': None,  # dùng get_review_queue() thay vì SQL filter
    'pool_mode': False,
    'use_smart_queue': True,
  },
}


def get_filtered_words(db, filter_key: str = 'all', status: str = 'all',
                       limit: int = None, exclude_ids: list = None) -> list[dict]:
    """
    Lấy danh sách từ theo filter. 
    Pool mode filters: lấy N từ rồi shuffle trước khi trả về.
    """
    import random
    from scoring import get_review_queue
    
    exclude_ids = exclude_ids or []
    
    # Smart queue không dùng SQL filter
    if filter_key != 'all' and FILTERS.get(filter_key, {}).get('use_smart_queue'):
        return get_review_queue(db, n=limit or 20, status_filter=status, exclude_ids=exclude_ids)
    
    # Build WHERE clause
    conditions = []
    
    # Status filter
    if status != 'all':
        conditions.append(f"status = '{status}'")
    
    # Named filter
    if filter_key != 'all' and filter_key in FILTERS:
        f = FILTERS[filter_key]
        if f.get('sql'):
            conditions.append(f['sql'])
            
    # Exclude IDs
    if exclude_ids:
        placeholders = ','.join(str(int(x)) for x in exclude_ids)
        conditions.append(f"id NOT IN ({placeholders})")
    
    where_clause = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    
    # Pool mode: lấy N từ theo ORDER, rồi shuffle
    if filter_key in FILTERS and FILTERS[filter_key].get('pool_mode'):
        f = FILTERS[filter_key]
        pool_size = f.get('pool_size', 20)
        order = f.get('order', 'total_score ASC')
        rows = db.execute(
            f"SELECT * FROM words {where_clause} ORDER BY {order} LIMIT {pool_size}"
        ).fetchall()
        result = [dict(r) for r in rows]
        random.shuffle(result)
        return result[:limit] if limit else result
    
    # Normal mode
    order = 'RANDOM()'  # mặc định random
    rows = db.execute(f"SELECT * FROM words {where_clause} ORDER BY {order}" +
                      (f" LIMIT {limit}" if limit else "")).fetchall()
    return [dict(r) for r in rows]


