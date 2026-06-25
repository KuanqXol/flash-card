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
    
    # Ensure column knowledge_score and new analytics columns exist
    cursor.execute("PRAGMA table_info(words)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'knowledge_score' not in columns:
        cursor.execute("ALTER TABLE words ADD COLUMN knowledge_score INTEGER DEFAULT 30")
        
    # Define V2 analytics and example columns
    new_cols = {
        'example': 'TEXT DEFAULT NULL',
        'flashcard_seen': 'INTEGER DEFAULT 0',
        'flashcard_correct': 'INTEGER DEFAULT 0',
        'flashcard_wrong': 'INTEGER DEFAULT 0',
        'mcq_seen': 'INTEGER DEFAULT 0',
        'mcq_correct': 'INTEGER DEFAULT 0',
        'mcq_wrong': 'INTEGER DEFAULT 0',
        'matching_seen': 'INTEGER DEFAULT 0',
        'matching_correct': 'INTEGER DEFAULT 0',
        'matching_wrong': 'INTEGER DEFAULT 0',
        'fill_seen': 'INTEGER DEFAULT 0',
        'fill_correct': 'INTEGER DEFAULT 0',
        'fill_wrong': 'INTEGER DEFAULT 0',
        'total_seen': 'INTEGER DEFAULT 0',
        'total_correct': 'INTEGER DEFAULT 0',
        'total_wrong': 'INTEGER DEFAULT 0'
    }
    
    added_any = False
    for col_name, col_def in new_cols.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE words ADD COLUMN {col_name} {col_def}")
            added_any = True
            
    # Backfill migration if new columns were added
    if added_any:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='word_stats'")
        if cursor.fetchone():
            import math
            def get_status_from_score(score):
                if 0 <= score <= 29:
                    return 'danger'
                elif 30 <= score <= 49:
                    return 'new'
                elif 50 <= score <= 69:
                    return 'learning'
                elif 70 <= score <= 89:
                    return 'familiar'
                elif 90 <= score <= 100:
                    return 'mastered'
                return 'new'

            cursor.execute("SELECT word_id, exercise, seen, correct FROM word_stats")
            stats_rows = cursor.fetchall()
            word_stats_data = {}
            for r in stats_rows:
                wid = r['word_id']
                exercise = r['exercise']
                seen = r['seen'] or 0
                correct = r['correct'] or 0
                if wid not in word_stats_data:
                    word_stats_data[wid] = {}
                word_stats_data[wid][exercise] = (seen, correct)
                
            cursor.execute("SELECT id FROM words")
            words_list = [r['id'] for r in cursor.fetchall()]
            
            for wid in words_list:
                stats = word_stats_data.get(wid, {})
                # flashcard
                fc_seen, fc_corr = stats.get('flashcard', (0, 0))
                fc_wrong = max(0, fc_seen - fc_corr)
                # mcq
                mcq_seen, mcq_corr = stats.get('mcq', (0, 0))
                mcq_wrong = max(0, mcq_seen - mcq_corr)
                # matching
                mat_seen, mat_corr = stats.get('matching', (0, 0))
                mat_wrong = max(0, mat_seen - mat_corr)
                # fill (typing)
                fill_seen, fill_corr = stats.get('typing', (0, 0))
                fill_wrong = max(0, fill_seen - fill_corr)
                
                tot_seen = fc_seen + mcq_seen + mat_seen + fill_seen
                tot_corr = fc_corr + mcq_corr + mat_corr + fill_corr
                tot_wrong = fc_wrong + mcq_wrong + mat_wrong + fill_wrong
                
                seen_count = tot_seen
                if seen_count == 0:
                    new_k_score = 30
                else:
                    review_quality = (fc_corr / fc_seen) * 100.0 if fc_seen > 0 else 0.0
                    en_vi_seen = mcq_seen + mat_seen
                    en_vi_corr = mcq_corr + mat_corr
                    quiz_score = (en_vi_corr / en_vi_seen) * 100.0 if en_vi_seen > 0 else 0.0
                    quiz_score_vi_en = (fill_corr / fill_seen) * 100.0 if fill_seen > 0 else 0.0
                    seen_score = min(100.0, (math.log(1 + seen_count) / math.log(31)) * 100.0)
                    final_score = 0.40 * review_quality + 0.20 * quiz_score + 0.30 * quiz_score_vi_en + 0.10 * seen_score
                    new_k_score = max(0, min(100, int(round(final_score))))
                    
                new_status = get_status_from_score(new_k_score)
                
                cursor.execute("""
                    UPDATE words SET
                        flashcard_seen = ?, flashcard_correct = ?, flashcard_wrong = ?,
                        mcq_seen = ?, mcq_correct = ?, mcq_wrong = ?,
                        matching_seen = ?, matching_correct = ?, matching_wrong = ?,
                        fill_seen = ?, fill_correct = ?, fill_wrong = ?,
                        total_seen = ?, total_correct = ?, total_wrong = ?,
                        knowledge_score = ?, status = ?
                    WHERE id = ?
                """, (
                    fc_seen, fc_corr, fc_wrong,
                    mcq_seen, mcq_corr, mcq_wrong,
                    mat_seen, mat_corr, mat_wrong,
                    fill_seen, fill_corr, fill_wrong,
                    tot_seen, tot_corr, tot_wrong,
                    new_k_score, new_status, wid
                ))
            
    # Define V3 2-way scoring and stats columns
    new_cols_v3 = {
        'flashcard_en_vi_seen': 'INTEGER DEFAULT 0',
        'flashcard_en_vi_correct': 'INTEGER DEFAULT 0',
        'flashcard_en_vi_wrong': 'INTEGER DEFAULT 0',
        'flashcard_vi_en_seen': 'INTEGER DEFAULT 0',
        'flashcard_vi_en_correct': 'INTEGER DEFAULT 0',
        'flashcard_vi_en_wrong': 'INTEGER DEFAULT 0',
        'mcq_en_vi_seen': 'INTEGER DEFAULT 0',
        'mcq_en_vi_correct': 'INTEGER DEFAULT 0',
        'mcq_en_vi_wrong': 'INTEGER DEFAULT 0',
        'mcq_vi_en_seen': 'INTEGER DEFAULT 0',
        'mcq_vi_en_correct': 'INTEGER DEFAULT 0',
        'mcq_vi_en_wrong': 'INTEGER DEFAULT 0',
        'en_vi_score': 'INTEGER DEFAULT 0',
        'vi_en_score': 'INTEGER DEFAULT 0'
    }
    
    added_v3 = False
    for col_name, col_def in new_cols_v3.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE words ADD COLUMN {col_name} {col_def}")
            added_v3 = True
            
    # Backfill migration if V3 columns were added
    if added_v3:
        # Fetch current values of flashcard_seen, flashcard_correct, flashcard_wrong, mcq_seen, mcq_correct, mcq_wrong
        # and copy them to the en_vi versions since the old history was all En-Vi.
        cursor.execute("""
            UPDATE words SET
                flashcard_en_vi_seen = flashcard_seen,
                flashcard_en_vi_correct = flashcard_correct,
                flashcard_en_vi_wrong = flashcard_wrong,
                mcq_en_vi_seen = mcq_seen,
                mcq_en_vi_correct = mcq_correct,
                mcq_en_vi_wrong = mcq_wrong
        """)
        
        # Now recalculate scores using the split scoring formula for all words!
        cursor.execute("SELECT id FROM words")
        words_list = [r['id'] for r in cursor.fetchall()]
        
        for wid in words_list:
            cursor.execute("""
                SELECT flashcard_en_vi_seen, flashcard_en_vi_correct,
                       flashcard_vi_en_seen, flashcard_vi_en_correct,
                       mcq_en_vi_seen, mcq_en_vi_correct,
                       mcq_vi_en_seen, mcq_vi_en_correct,
                       matching_seen, matching_correct,
                       fill_seen, fill_correct
                FROM words WHERE id = ?
            """, (wid,))
            w = cursor.fetchone()
            if w:
                fc_ev_seen = w['flashcard_en_vi_seen'] or 0
                fc_ev_corr = w['flashcard_en_vi_correct'] or 0
                fc_ve_seen = w['flashcard_vi_en_seen'] or 0
                fc_ve_corr = w['flashcard_vi_en_correct'] or 0
                
                mcq_ev_seen = w['mcq_en_vi_seen'] or 0
                mcq_ev_corr = w['mcq_en_vi_correct'] or 0
                mcq_ve_seen = w['mcq_vi_en_seen'] or 0
                mcq_ve_corr = w['mcq_vi_en_correct'] or 0
                
                mat_seen = w['matching_seen'] or 0
                mat_corr = w['matching_correct'] or 0
                fill_seen = w['fill_seen'] or 0
                fill_corr = w['fill_correct'] or 0
                
                # Formula
                seen_count = fc_ev_seen + fc_ve_seen + mcq_ev_seen + mcq_ve_seen + mat_seen + fill_seen
                
                if seen_count == 0:
                    ev_score = 0
                    ve_score = 0
                    final_score = 30
                else:
                    fc_ev_acc = (fc_ev_corr / fc_ev_seen) * 100.0 if fc_ev_seen > 0 else 0.0
                    mcq_ev_acc = (mcq_ev_corr / mcq_ev_seen) * 100.0 if mcq_ev_seen > 0 else 0.0
                    mat_acc = (mat_corr / mat_seen) * 100.0 if mat_seen > 0 else 0.0
                    ev_score = int(round(0.40 * fc_ev_acc + 0.30 * mcq_ev_acc + 0.30 * mat_acc))
                    
                    fc_ve_acc = (fc_ve_corr / fc_ve_seen) * 100.0 if fc_ve_seen > 0 else 0.0
                    mcq_ve_acc = (mcq_ve_corr / mcq_ve_seen) * 100.0 if mcq_ve_seen > 0 else 0.0
                    fill_acc = (fill_corr / fill_seen) * 100.0 if fill_seen > 0 else 0.0
                    ve_score = int(round(0.40 * fc_ve_acc + 0.30 * mcq_ve_acc + 0.30 * fill_acc))
                    
                    import math
                    seen_score = min(100.0, (math.log(1 + seen_count) / math.log(31)) * 100.0)
                    
                    final_score = int(round(0.45 * ev_score + 0.45 * ve_score + 0.10 * seen_score))
                    final_score = max(0, min(100, final_score))
                
                def get_status_from_score(score):
                    if 0 <= score <= 29: return 'danger'
                    elif 30 <= score <= 49: return 'new'
                    elif 50 <= score <= 69: return 'learning'
                    elif 70 <= score <= 89: return 'familiar'
                    elif 90 <= score <= 100: return 'mastered'
                    return 'new'
                    
                new_status = get_status_from_score(final_score)
                cursor.execute("""
                    UPDATE words SET
                        en_vi_score = ?,
                        vi_en_score = ?,
                        knowledge_score = ?,
                        status = ?
                    WHERE id = ?
                """, (ev_score, ve_score, final_score, new_status, wid))
        
    # Ensure first_learned_at column exists
    cursor.execute("PRAGMA table_info(words)")
    columns_latest = [row['name'] for row in cursor.fetchall()]
    if 'first_learned_at' not in columns_latest:
        cursor.execute("ALTER TABLE words ADD COLUMN first_learned_at TEXT DEFAULT NULL")
        # Backfill: existing reviewed words get first_learned_at = date_added
        cursor.execute("""
            UPDATE words SET first_learned_at = date_added
            WHERE review_count > 0 AND first_learned_at IS NULL
        """)

    # Create word_events table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS word_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        event TEXT NOT NULL,
        timestamp TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (word_id) REFERENCES words(id)
    );
    ''')

    # Create word_stats table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS word_stats (
        word_id INTEGER,
        exercise TEXT,
        seen INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        PRIMARY KEY (word_id, exercise),
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
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
        ('session_size', '20'),
        ('matching_pairs', '6'),
        ('new_word_ratio', '0.2'),
        ('theme', 'light'),
        ('user_name', ''),
        ('tts_speed_normal', '1.0'),
        ('tts_speed_slow', '0.5'),
        ('perf_pool_size', '20'),
    ]
    for key, value in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Migration: update default session_size from 10 to 20 for existing databases
    cursor.execute("SELECT value FROM settings WHERE key = 'session_size'")
    row = cursor.fetchone()
    if row and row['value'] == '10':
        cursor.execute("UPDATE settings SET value = '20' WHERE key = 'session_size'")
        
    # Create toeic_questions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS toeic_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        question TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_option TEXT NOT NULL,
        explanation TEXT,
        translation TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    ''')

    # Ensure column import_batch exists in toeic_questions
    cursor.execute("PRAGMA table_info(toeic_questions)")
    toeic_columns = [row['name'] for row in cursor.fetchall()]
    if 'import_batch' not in toeic_columns:
        cursor.execute("ALTER TABLE toeic_questions ADD COLUMN import_batch TEXT DEFAULT NULL")

    # Create toeic_sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS toeic_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now','localtime')),
        topic TEXT DEFAULT 'Tất cả',
        total_questions INTEGER NOT NULL,
        correct_count INTEGER NOT NULL,
        accuracy REAL NOT NULL,
        duration_seconds INTEGER NOT NULL,
        details TEXT
    );
    ''')
        
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
    elif status == 'learned':
        cursor.execute("SELECT * FROM words WHERE status = 'mastered' ORDER BY id DESC")
    elif status == 'learning':
        cursor.execute("SELECT * FROM words WHERE status IN ('learning', 'danger', 'familiar') ORDER BY id DESC")
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
        
    status_query = ""
    params = []
    
    if status:
        if status == 'learned':
            status_query = "status = 'mastered'"
        elif status == 'learning':
            status_query = "status IN ('learning', 'danger', 'familiar')"
        else:
            status_query = "status = ?"
            params.append(status)
            
    exclude_query = ""
    if exclude_id is not None:
        exclude_query = "id != ?"
        params.append(exclude_id)
        
    where_parts = []
    if status_query:
        where_parts.append(status_query)
    if exclude_query:
        where_parts.append(exclude_query)
        
    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    params.append(n)
    
    query = f"SELECT * FROM words {where_clause} ORDER BY RANDOM() LIMIT ?"
    cursor.execute(query, tuple(params))
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
        
        # Set first_learned_at on first-ever review
        db.execute("""
            UPDATE words SET first_learned_at = ?
            WHERE id = ? AND first_learned_at IS NULL
        """, (now, word_id_val))
        
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
    
    counts = {'danger': 0, 'new': 0, 'learning': 0, 'familiar': 0, 'mastered': 0}
    for r in rows:
        status_val = r['status']
        cnt = r['cnt']
        if status_val in counts:
            counts[status_val] = cnt
            
    # Total words count
    cursor.execute("SELECT COUNT(*) FROM words")
    row_count = cursor.fetchone()
    total = row_count[0] if row_count else 0
    
    # Reviewed today count
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM words WHERE substr(last_reviewed, 1, 10) = ?", (today_str,))
    row_today = cursor.fetchone()
    reviewed_today = row_today[0] if row_today else 0
    
    # New words reviewed today (first_learned_at is today)
    cursor.execute("SELECT COUNT(*) FROM words WHERE substr(first_learned_at, 1, 10) = ?", (today_str,))
    row_new_today = cursor.fetchone()
    new_words_reviewed_today = row_new_today[0] if row_new_today else 0
    
    # Total score sum
    cursor.execute("SELECT SUM(total_score) FROM words")
    row_score = cursor.fetchone()
    total_score_sum = row_score[0] if (row_score and row_score[0] is not None) else 0
    
    # Knowledge score sum
    cursor.execute("SELECT SUM(knowledge_score) FROM words")
    row_k_score = cursor.fetchone()
    knowledge_score_sum = row_k_score[0] if (row_k_score and row_k_score[0] is not None) else 0
    
    # Needs review count
    cursor.execute("SELECT COUNT(*) FROM words WHERE needs_review = 1")
    row_review = cursor.fetchone()
    needs_review_cnt = row_review[0] if row_review else 0
    
    # Count of words mastered this week (last 7 days)
    cursor.execute("""
        SELECT COUNT(DISTINCT word_id) 
        FROM word_events 
        WHERE event IN ('auto_mastered', 'manual_mastered') 
          AND timestamp >= datetime('now', '-7 days', 'localtime')
    """)
    mastered_this_week = cursor.fetchone()[0] or 0

    # Practice stats by mode
    cursor.execute("""
        SELECT 
            mode,
            COUNT(*) as total_reviews,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as total_correct,
            SUM(CASE WHEN substr(reviewed_at, 1, 10) = ? THEN 1 ELSE 0 END) as today_reviews,
            SUM(CASE WHEN substr(reviewed_at, 1, 10) = ? AND is_correct = 1 THEN 1 ELSE 0 END) as today_correct
        FROM review_history
        GROUP BY mode
    """, (today_str, today_str))
    mode_rows = cursor.fetchall()
    
    practice_stats = {
        'flashcard': {'total_reviews': 0, 'total_correct': 0, 'today_reviews': 0, 'today_correct': 0, 'accuracy': 0.0},
        'mcq': {'total_reviews': 0, 'total_correct': 0, 'today_reviews': 0, 'today_correct': 0, 'accuracy': 0.0},
        'matching': {'total_reviews': 0, 'total_correct': 0, 'today_reviews': 0, 'today_correct': 0, 'accuracy': 0.0},
        'typing': {'total_reviews': 0, 'total_correct': 0, 'today_reviews': 0, 'today_correct': 0, 'accuracy': 0.0},
        'toeic': {'total_reviews': 0, 'total_correct': 0, 'today_reviews': 0, 'today_correct': 0, 'accuracy': 0.0}
    }
    
    for r in mode_rows:
        m = r['mode']
        if m == 'fill':
            m = 'typing'
        if m in practice_stats:
            tot_rev = r['total_reviews'] or 0
            tot_corr = r['total_correct'] or 0
            tod_rev = r['today_reviews'] or 0
            tod_corr = r['today_correct'] or 0
            acc = round(tot_corr / tot_rev * 100, 1) if tot_rev > 0 else 0.0
            practice_stats[m] = {
                'total_reviews': tot_rev,
                'total_correct': tot_corr,
                'today_reviews': tod_rev,
                'today_correct': tod_corr,
                'accuracy': acc
            }
            
    # Fetch TOEIC stats
    cursor.execute("""
        SELECT
            COUNT(*) as sessions_count,
            SUM(total_questions) as total_q,
            SUM(correct_count) as correct_q,
            SUM(CASE WHEN substr(timestamp, 1, 10) = ? THEN total_questions ELSE 0 END) as today_total_q,
            SUM(CASE WHEN substr(timestamp, 1, 10) = ? THEN correct_count ELSE 0 END) as today_correct_q
        FROM toeic_sessions
    """, (today_str, today_str))
    toeic_row = cursor.fetchone()
    
    if toeic_row and toeic_row['total_q'] and toeic_row['total_q'] > 0:
        tot_q = toeic_row['total_q']
        tot_c = toeic_row['correct_q'] or 0
        tod_q = toeic_row['today_total_q'] or 0
        tod_c = toeic_row['today_correct_q'] or 0
        
        practice_stats['toeic'] = {
            'total_reviews': tot_q,
            'total_correct': tot_c,
            'today_reviews': tod_q,
            'today_correct': tod_c,
            'accuracy': round(tot_c * 100.0 / tot_q, 1)
        }
            
    conn.close()
    
    # Map legacy categories
    legacy_new = counts['new']
    legacy_learning = counts['learning'] + counts['danger'] + counts['familiar']
    legacy_learned = counts['mastered']
    
    return {
        'danger': counts['danger'],
        'new': legacy_new,
        'learning': legacy_learning,
        'familiar': counts['familiar'],
        'learned': legacy_learned,
        'mastered': legacy_learned,
        'total': total,
        'reviewed_today': reviewed_today,
        'new_words_reviewed_today': new_words_reviewed_today,
        'total_score_sum': total_score_sum,
        'knowledge_score_sum': knowledge_score_sum,
        'needs_review': needs_review_cnt,
        'mastered_this_week': mastered_this_week,
        'practice_stats': practice_stats
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
  'new_reviewed_today': {
    'label': 'Từ mới đã ôn hôm nay',
    'group': 'time',
    'sql': "date(first_learned_at) = date('now','localtime')",
    'pool_mode': False,
  },
  'reviewed_within_2days': {
    'label': 'Đã ôn trong 2 ngày',
    'group': 'time',
    'sql': "last_reviewed IS NOT NULL AND date(last_reviewed) >= date('now','-1 day','localtime')",
    'pool_mode': False,
  },
  'reviewed_within_3days': {
    'label': 'Đã ôn trong 3 ngày',
    'group': 'time',
    'sql': "last_reviewed IS NOT NULL AND date(last_reviewed) >= date('now','-2 days','localtime')",
    'pool_mode': False,
  },
  'new_reviewed_within_2days': {
    'label': 'Từ mới trong 2 ngày',
    'group': 'time',
    'sql': "first_learned_at IS NOT NULL AND date(first_learned_at) >= date('now','-1 day','localtime')",
    'pool_mode': False,
  },
  'new_reviewed_within_3days': {
    'label': 'Từ mới trong 3 ngày',
    'group': 'time',
    'sql': "first_learned_at IS NOT NULL AND date(first_learned_at) >= date('now','-2 days','localtime')",
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
    'sql': "status != 'mastered' AND status != 'learned'",
    'order': 'knowledge_score ASC',
    'pool_mode': True,   # ← lấy top N rồi shuffle
  },
  'lowest_accuracy': {
    'label': 'Accuracy thấp nhất',
    'group': 'performance',
    'sql': "review_count >= 3",  # cần đủ data mới so sánh accuracy
    'order': "(correct_count * 1.0 / NULLIF(review_count, 0)) ASC",
    'pool_mode': True,
  },
  'most_wrong': {
    'label': 'Sai nhiều nhất',
    'group': 'performance',
    'sql': "wrong_count > 0",
    'order': 'wrong_count DESC',
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
    Hỗ trợ chọn nhiều bộ lọc trạng thái và bộ lọc thời gian/hiệu suất (phân tách bằng dấu phẩy).
    """
    import random
    from scoring import get_review_queue
    
    exclude_ids = exclude_ids or []
    
    filter_keys = [fk.strip() for fk in filter_key.split(',') if fk.strip()] if filter_key else []
    
    # Smart queue không dùng SQL filter
    if 'smart_priority' in filter_keys:
        return get_review_queue(db, n=limit or 20, status_filter=status, exclude_ids=exclude_ids)
    
    # Build WHERE clause
    conditions = []
    
    # Status filter (OR logic within status group)
    if status and status != 'all':
        statuses = [s.strip() for s in status.split(',') if s.strip()]
        status_clauses = []
        for s in statuses:
            if s == 'learned' or s == 'mastered':
                status_clauses.append("status = 'mastered'")
            elif s == 'learning':
                status_clauses.append("status IN ('learning', 'danger', 'familiar')")
            elif s == 'new':
                status_clauses.append("status = 'new'")
        if status_clauses:
            conditions.append("(" + " OR ".join(status_clauses) + ")")
            
    # Custom filters
    time_clauses = []
    perf_clauses = []
    pool_mode = False
    
    # Load perf_pool_size setting
    try:
        cursor = db.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'perf_pool_size'")
        row = cursor.fetchone()
        perf_pool_size = int(row['value']) if row else 20
    except Exception:
        perf_pool_size = 20
        
    pool_size = perf_pool_size
    order_by_clauses = []
    
    for fk in filter_keys:
        if fk == 'all':
            continue
        if fk in FILTERS:
            f = FILTERS[fk]
            grp = f.get('group')
            sql_cond = f.get('sql')
            if sql_cond:
                if grp == 'time' or grp == 'combo':
                    time_clauses.append(sql_cond)
                elif grp == 'performance':
                    perf_clauses.append(sql_cond)
            if f.get('pool_mode'):
                pool_mode = True
                pool_size = max(pool_size, f.get('pool_size', perf_pool_size))
                if f.get('order'):
                    order_by_clauses.append(f['order'])
                    
    if time_clauses:
        conditions.append("(" + " OR ".join(time_clauses) + ")")
    if perf_clauses:
        conditions.append("(" + " OR ".join(perf_clauses) + ")")
    
    # Exclude IDs
    if exclude_ids:
        placeholders = ','.join(str(int(x)) for x in exclude_ids)
        conditions.append(f"id NOT IN ({placeholders})")
        
    where_clause = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    
    # Pool mode: lấy N từ theo ORDER, rồi shuffle
    if pool_mode:
        order = ", ".join(order_by_clauses) if order_by_clauses else 'knowledge_score ASC'
        query = f"SELECT * FROM words {where_clause} ORDER BY {order} LIMIT {pool_size}"
        rows = db.execute(query).fetchall()
        result = [dict(r) for r in rows]
        random.shuffle(result)
        return result[:limit] if limit else result
        
    # Normal mode
    order = 'RANDOM()'
    query = f"SELECT * FROM words {where_clause} ORDER BY {order}" + (f" LIMIT {limit}" if limit else "")
    rows = db.execute(query).fetchall()
    return [dict(r) for r in rows]


def get_toeic_questions(db, topic=None, limit=None, unanswered_only=False):
    """Retrieves list of TOEIC questions, optionally filtered by topic and shuffled."""
    query_parts = []
    params = []
    
    if topic and topic != 'all':
        tenses = [
            "Hiện tại đơn", "Hiện tại tiếp diễn", "Hiện tại hoàn thành", "Hiện tại hoàn thành tiếp diễn",
            "Quá khứ đơn", "Quá khứ tiếp diễn", "Quá khứ hoàn thành", "Quá khứ hoàn thành tiếp diễn",
            "Tương lai đơn", "Tương lai tiếp diễn", "Tương lai hoàn thành", "Tương lai hoàn thành tiếp diễn"
        ]
        if topic == 'tenses':
            placeholders = ",".join("?" for _ in tenses)
            query_parts.append(f"topic IN ({placeholders})")
            params.extend(tenses)
        elif topic == 'others':
            placeholders = ",".join("?" for _ in tenses)
            query_parts.append(f"(topic NOT IN ({placeholders}) OR topic IS NULL OR topic = '')")
            params.extend(tenses)
        elif topic == 'wrong_questions':
            # Retrieve all toeic sessions to analyze wrong questions
            # Order by timestamp ASC so that later correct attempts overwrite earlier wrong attempts.
            rows = db.execute("SELECT details FROM toeic_sessions ORDER BY timestamp ASC").fetchall()
            wrong_set = set()
            for r in rows:
                details_str = r['details']
                if not details_str:
                    continue
                try:
                    import json
                    details = json.loads(details_str)
                    for item in details:
                        q_id = item.get('question_id')
                        is_correct = item.get('is_correct')
                        correct = (is_correct is True or is_correct == 1 or str(is_correct).lower() == 'true')
                        if q_id is not None:
                            if not correct:
                                wrong_set.add(int(q_id))
                            else:
                                wrong_set.discard(int(q_id))
                except Exception:
                    pass
            
            if not wrong_set:
                return []
            
            placeholders = ",".join("?" for _ in wrong_set)
            query_parts.append(f"id IN ({placeholders})")
            params.extend(wrong_set)
        else:
            query_parts.append("topic = ?")
            params.append(topic)
            
    if unanswered_only and topic != 'wrong_questions':
        # Retrieve all toeic sessions to analyze answered questions
        rows = db.execute("SELECT details FROM toeic_sessions").fetchall()
        answered_set = set()
        for r in rows:
            details_str = r['details']
            if not details_str:
                continue
            try:
                import json
                details = json.loads(details_str)
                for item in details:
                    q_id = item.get('question_id')
                    if q_id is not None:
                        answered_set.add(int(q_id))
            except Exception:
                pass
        
        if answered_set:
            placeholders = ",".join("?" for _ in answered_set)
            query_parts.append(f"id NOT IN ({placeholders})")
            params.extend(answered_set)
        
    where_clause = "WHERE " + " AND ".join(query_parts) if query_parts else ""
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"SELECT * FROM toeic_questions {where_clause} ORDER BY RANDOM() {limit_clause}"
    rows = db.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_toeic_topics(db):
    """Retrieves all unique topics/categories in toeic_questions."""
    rows = db.execute("SELECT DISTINCT topic FROM toeic_questions WHERE topic IS NOT NULL AND topic != '' ORDER BY topic").fetchall()
    return [r['topic'] for r in rows]

def get_toeic_import_batches(db):
    """Retrieves list of all unique import batches from toeic_questions."""
    rows = db.execute("SELECT DISTINCT import_batch FROM toeic_questions WHERE import_batch IS NOT NULL AND import_batch != '' ORDER BY import_batch DESC").fetchall()
    return [r['import_batch'] for r in rows]

def insert_toeic_session(db, topic, total_questions, correct_count, accuracy, duration_seconds, details):
    """Inserts a completed TOEIC practice session into database."""
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO toeic_sessions (topic, total_questions, correct_count, accuracy, duration_seconds, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (topic, total_questions, correct_count, accuracy, duration_seconds, details))
    db.commit()
    return cursor.lastrowid

def get_toeic_sessions(db, limit=None):
    """Retrieves all TOEIC sessions sorted by recent timestamp first."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"SELECT * FROM toeic_sessions ORDER BY timestamp DESC {limit_clause}"
    rows = db.execute(query).fetchall()
    return [dict(row) for row in rows]


