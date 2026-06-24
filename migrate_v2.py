import sqlite3
from datetime import datetime

def migrate():
    conn = sqlite3.connect('flashcards.db')
    c = conn.cursor()
    
    print("🔄 Bắt đầu migrate v1 → v2...")
    
    # 1. Thêm columns mới vào bảng words (dùng ALTER TABLE, bỏ qua nếu đã có)
    new_columns = [
        ("correct_count",      "INTEGER DEFAULT 0"),
        ("wrong_count",        "INTEGER DEFAULT 0"),
        ("self_correct_count", "INTEGER DEFAULT 0"),  # chỉ fill mode
        ("self_wrong_count",   "INTEGER DEFAULT 0"),  # chỉ fill mode
        ("last_failed_at",     "TEXT"),               # ISO datetime lần sai gần nhất
        ("correct_streak",     "INTEGER DEFAULT 0"),  # số lần đúng liên tiếp
        ("consecutive_wrong",  "INTEGER DEFAULT 0"),  # số lần sai liên tiếp (reset khi đúng)
        ("needs_review",       "INTEGER DEFAULT 0"),  # 1 = cần ôn lại (soft flag)
    ]
    
    for col_name, col_def in new_columns:
        try:
            c.execute(f"ALTER TABLE words ADD COLUMN {col_name} {col_def}")
            print(f"  ✅ Thêm column: {col_name}")
        except sqlite3.OperationalError:
            print(f"  ⏩ Đã có: {col_name}")
    
    # 2. Tạo bảng word_pos (POS entries riêng biệt)
    c.execute("""
        CREATE TABLE IF NOT EXISTS word_pos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER NOT NULL,
            pos TEXT,            -- 'n', 'v', 'adj', 'adv', 'prep', 'conj', 'pron', NULL (cho phrase)
            meaning TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
        )
    """)
    print("  ✅ Tạo bảng word_pos")
    
    # 3. Tạo bảng settings (key-value store)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    print("  ✅ Tạo bảng settings")
    
    # 4. Default settings
    defaults = [
        ('daily_goal', '20'),           # số từ ôn mỗi ngày
        ('session_size', '20'),         # số từ mỗi phiên
        ('matching_pairs', '6'),        # số cặp mỗi round matching
        ('new_word_ratio', '0.2'),      # 20% từ mới trong session
        ('theme', 'light'),
        ('perf_pool_size', '20'),
    ]
    for key, value in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    print("  ✅ Thêm default settings")
    
    # 5. Backfill correct_count và wrong_count từ review_history
    c.execute("""
        UPDATE words SET
            correct_count = (
                SELECT COUNT(*) FROM review_history 
                WHERE word_id = words.id AND is_correct = 1
            ),
            wrong_count = (
                SELECT COUNT(*) FROM review_history 
                WHERE word_id = words.id AND is_correct = 0
            )
    """)
    print("  ✅ Backfill correct_count/wrong_count từ review_history")
    
    conn.commit()
    conn.close()
    print(f"\n✅ Migration hoàn thành lúc {datetime.now().strftime('%H:%M:%S')}")

if __name__ == '__main__':
    migrate()
