import sys
import os
import pandas as pd
from database import get_db, init_db

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_short_translation(full_translation: str) -> str:
    """
    Parses full translation by taking the first segment before a semicolon,
    stripping specific word-type prefixes, and cleaning up extra whitespace.
    
    Example:
    "n. người đại diện đại diện tượng trưng; adj. đại diện" -> "người đại diện đại diện tượng trưng"
    """
    if not isinstance(full_translation, str) or not full_translation:
        return ""
    
    # Split by semicolon and get the first part
    first_part = full_translation.split(';')[0].strip()
    
    # Prefix list to strip from the beginning of the string (case-insensitive)
    prefixes = ["n. ", "v. ", "adj. ", "adv. ", "web. "]
    
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if first_part.lower().startswith(prefix.lower()):
                first_part = first_part[len(prefix):].strip()
                changed = True
                break
                
    return first_part

def import_from_csv(csv_path: str):
    """
    Reads a CSV file containing Word, Phonetic, Translation, and Date columns,
    and performs a case-insensitive upsert in the database.
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
    
    for _, row in df.iterrows():
        word = str(row.get('Word', '')).strip()
        if not word:
            continue
            
        phonetic = str(row.get('Phonetic', '')).strip() if pd.notna(row.get('Phonetic')) else None
        translation = str(row.get('Translation', '')).strip() if pd.notna(row.get('Translation')) else ""
        date_added = str(row.get('Date', '')).strip() if pd.notna(row.get('Date')) else None
        
        short_translation = parse_short_translation(translation)
        
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
        else:
            # Insert new word record
            cursor.execute('''
                INSERT INTO words (word, phonetic, translation, short_translation, date_added, status, total_score, review_count, has_been_rated_five, last_reviewed)
                VALUES (?, ?, ?, ?, ?, 'new', 0, 0, 0, NULL)
            ''', (word, phonetic, translation, short_translation, date_added))
            new_count += 1
            
    conn.commit()
    conn.close()
    
    total_count = new_count + update_count
    print(f"✅ Import: {new_count} từ mới | ♻️ Update: {update_count} từ | Tổng: {total_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_csv.py <csv_path>")
        sys.exit(1)
        
    csv_path = sys.argv[1]
    import_from_csv(csv_path)
