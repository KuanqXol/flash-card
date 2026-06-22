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

def import_toeic_from_xlsx(file_path: str) -> dict:
    """
    Reads an Excel (.xlsx) file containing TOEIC Part 5 multiple choice questions
    with columns: Chu De, Cau Hoi, Dap An A, Dap An B, Dap An C, Dap An D, Dap An Dung, Giai Thich, Dich Nghia
    and performs a case-insensitive check and upsert in the database.
    
    Returns: { 'imported': int, 'updated': int, 'skipped': int, 'total': int }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' does not exist.")
        
    # Ensure database is initialized
    init_db()
    
    # Read Excel using pandas
    df = pd.read_excel(file_path)
    
    # Strip whitespace from column names
    df.columns = [str(c).strip() for c in df.columns]
    
    conn = get_db()
    cursor = conn.cursor()
    
    new_count = 0
    update_count = 0
    skipped_count = 0
    
    for _, row in df.iterrows():
        # Extracted fields
        question = str(row.get('Cau Hoi', '')).strip() if pd.notna(row.get('Cau Hoi')) else ''
        if not question:
            skipped_count += 1
            continue
            
        topic = str(row.get('Chu De', 'Chung')).strip() if pd.notna(row.get('Chu De')) else 'Chung'
        option_a = str(row.get('Dap An A', '')).strip() if pd.notna(row.get('Dap An A')) else ''
        option_b = str(row.get('Dap An B', '')).strip() if pd.notna(row.get('Dap An B')) else ''
        option_c = str(row.get('Dap An C', '')).strip() if pd.notna(row.get('Dap An C')) else ''
        option_d = str(row.get('Dap An D', '')).strip() if pd.notna(row.get('Dap An D')) else ''
        
        correct_option = str(row.get('Dap An Dung', '')).strip().upper() if pd.notna(row.get('Dap An Dung')) else ''
        explanation = str(row.get('Giai Thich', '')).strip() if pd.notna(row.get('Giai Thich')) else ''
        translation = str(row.get('Dich Nghia', '')).strip() if pd.notna(row.get('Dich Nghia')) else ''
        
        # Validation
        if not option_a or not option_b or not option_c or not option_d or correct_option not in ['A', 'B', 'C', 'D']:
            skipped_count += 1
            continue
            
        # Case-insensitive duplicate check based on question
        cursor.execute("SELECT id FROM toeic_questions WHERE LOWER(question) = LOWER(?)", (question,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing question
            cursor.execute("""
                UPDATE toeic_questions
                SET topic = ?, option_a = ?, option_b = ?, option_c = ?, option_d = ?, correct_option = ?, explanation = ?, translation = ?
                WHERE id = ?
            """, (topic, option_a, option_b, option_c, option_d, correct_option, explanation, translation, existing['id']))
            update_count += 1
        else:
            # Insert new question
            cursor.execute("""
                INSERT INTO toeic_questions (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (topic, question, option_a, option_b, option_c, option_d, correct_option, explanation, translation))
            new_count += 1
            
    conn.commit()
    conn.close()
    
    total_count = new_count + update_count + skipped_count
    return {
        'imported': new_count,
        'updated': update_count,
        'skipped': skipped_count,
        'total': total_count
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_toeic.py <xlsx_path>")
        sys.exit(1)
        
    xlsx_path = sys.argv[1]
    res = import_toeic_from_xlsx(xlsx_path)
    print(f"Imported: {res['imported']} | Updated: {res['updated']} | Skipped: {res['skipped']} | Total: {res['total']}")
