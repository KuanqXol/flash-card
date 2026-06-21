import sys
import os
import pandas as pd
import re
from database import get_db, init_db

POS_TAGS = ('n', 'v', 'adj', 'adv', 'prep', 'conj', 'pron', 'web')
_SPLIT_RE = re.compile(r';\s*(?=' + '|'.join(POS_TAGS) + r'\.\s)')
_MATCH_RE = re.compile(r'^(' + '|'.join(POS_TAGS) + r')\.\s*(.+)')

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_pos_entries(translation: str) -> list[dict]:
    """
    Input : "n. người đại diện; adj. đại diện tượng trưng; v. đại diện thay mặt; web. tiêu biểu..."
    Output: [
        {"pos": "n",   "meaning": "người đại diện"},
        {"pos": "adj", "meaning": "đại diện tượng trưng"},
        {"pos": "v",   "meaning": "đại diện thay mặt"},
        # "web" bị loại bỏ
    ]
    Edge cases:
    - Phrase (không có POS): pos=None, lấy toàn bộ text
    - Chỉ 1 POS không có ";": vẫn parse đúng
    - Translation rỗng hoặc None: trả về []
    - Chỉ có "web.": trả về [] (vì web bị filter)
    """
    if not translation or not translation.strip() or not isinstance(translation, str):
        return []
    
    parts = _SPLIT_RE.split(translation.strip())
    entries = []
    has_pos_prefix = False
    
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        m = _MATCH_RE.match(part)
        if m:
            has_pos_prefix = True
            pos, meaning = m.group(1), m.group(2).strip()
            if pos != 'web':  # Bỏ entries web
                entries.append({'pos': pos, 'meaning': meaning})
        elif not has_pos_prefix and i == 0:
            # Phrase không có POS prefix (vd: "the nasal spray")
            entries.append({'pos': None, 'meaning': part})
    
    return entries


def get_short_translation(pos_entries: list[dict], full_translation: str) -> str:
    """
    Lấy nghĩa ngắn gọn nhất từ pos_entries.
    - Dùng meaning của entry đầu tiên
    - Cắt tối đa 60 ký tự
    """
    if pos_entries:
        meaning = pos_entries[0]['meaning']
    elif full_translation and isinstance(full_translation, str):
        # Fallback: bỏ POS prefix và lấy phần trước ";"
        cleaned = re.sub(r'^(' + '|'.join(POS_TAGS) + r')\.\s*', '', full_translation.strip())
        meaning = cleaned.split(';')[0].strip()
    else:
        meaning = ''
    
    return meaning[:60] + ('...' if len(meaning) > 60 else '')


def parse_short_translation(full_translation: str) -> str:
    """Legacy stub to maintain test suite compatibility."""
    entries = parse_pos_entries(full_translation)
    return get_short_translation(entries, full_translation)

def import_from_csv(csv_path: str) -> dict:
    """
    Reads a CSV file containing Word, Phonetic, Translation, and Date columns,
    and performs a case-insensitive upsert in the database.
    Returns: { 'imported': int, 'updated': int, 'skipped': int, 'total': int }
    """
    if not os.path.exists(csv_path):
        print(f"Error: File '{csv_path}' does not exist.")
        sys.exit(1)
        
    # Read CSV using pandas with utf-8-sig to handle BOM correctly
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # Normalize column names to strip any stray spaces
    df.columns = [c.strip() for c in df.columns]
    
    # Ensure database tables exist before importing
    init_db()
    
    conn = get_db()
    cursor = conn.cursor()
    
    new_count = 0
    update_count = 0
    skipped_count = 0
    
    for _, row in df.iterrows():
        word = str(row.get('Word', '')).strip() if pd.notna(row.get('Word')) else ''
        if not word:
            skipped_count += 1
            continue
            
        phonetic = str(row.get('Phonetic', '')).strip() if pd.notna(row.get('Phonetic')) else None
        if phonetic == '--':
            phonetic = ''
            
        translation = str(row.get('Translation', '')).strip() if pd.notna(row.get('Translation')) else ""
        date_added = str(row.get('Date', '')).strip() if pd.notna(row.get('Date')) else None
        
        # Parse POS entries
        entries = parse_pos_entries(translation)
        short_translation = get_short_translation(entries, translation)
        
        # Perform case-insensitive search for existing word
        cursor.execute('SELECT id FROM words WHERE LOWER(word) = LOWER(?)', (word,))
        existing = cursor.fetchone()
        
        if existing:
            # Update phonetic, translation, and short_translation, preserving existing stats
            cursor.execute('''
                UPDATE words
                SET phonetic = ?, translation = ?, short_translation = ?
                WHERE id = ?
            ''', (phonetic, translation, short_translation, existing['id']))
            update_count += 1
            word_id = existing['id']
        else:
            # Insert new word record
            cursor.execute('''
                INSERT INTO words (word, phonetic, translation, short_translation, date_added, status, total_score, review_count, has_been_rated_five, last_reviewed, knowledge_score)
                VALUES (?, ?, ?, ?, ?, 'new', 0, 0, 0, NULL, 30)
            ''', (word, phonetic, translation, short_translation, date_added))
            new_count += 1
            word_id = cursor.lastrowid
            
        # Xóa POS entries cũ của từ này rồi insert lại
        cursor.execute("DELETE FROM word_pos WHERE word_id = ?", (word_id,))
        for i, entry in enumerate(entries):
            cursor.execute(
                "INSERT INTO word_pos (word_id, pos, meaning, sort_order) VALUES (?, ?, ?, ?)",
                (word_id, entry['pos'], entry['meaning'], i)
            )
            
    conn.commit()
    conn.close()
    
    total_count = new_count + update_count + skipped_count
    print(f"✅ Import: {new_count} từ mới | ♻️ Update: {update_count} từ | Skipped: {skipped_count} | Tổng: {total_count}")
    
    return {
        'imported': new_count,
        'updated': update_count,
        'skipped': skipped_count,
        'total': total_count
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_csv.py <csv_path>")
        sys.exit(1)
        
    csv_path = sys.argv[1]
    import_from_csv(csv_path)
