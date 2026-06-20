import sqlite3

def run_migration():
    conn = sqlite3.connect('flashcards.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Fetch all words
    cursor.execute("SELECT id, word, status, knowledge_score FROM words")
    words = cursor.fetchall()
    
    # We will log how many words are migrated
    migrated_count = 0
    
    print(f"Bắt đầu migrate {len(words)} từ...")
    
    for word in words:
        word_id = word['id']
        
        # Calculate avg_rating from review_history where rating is not null
        cursor.execute("SELECT AVG(rating) as avg_rating FROM review_history WHERE word_id = ? AND rating IS NOT NULL", (word_id,))
        row = cursor.fetchone()
        avg_rating = row['avg_rating']
        
        if avg_rating is None:
            # Từ chưa có review → knowledge_score = 30
            k_score = 30
        else:
            if avg_rating <= 2.0:
                k_score = 20
            elif avg_rating <= 3.0:
                k_score = 35
            elif avg_rating <= 4.0:
                k_score = 58
            else:
                k_score = 75
                
        # Status calculation based on new score
        if 0 <= k_score <= 50:
            status = 'new'
        elif 51 <= k_score <= 89:
            status = 'learning'
        else:
            status = 'mastered'
            
        cursor.execute("UPDATE words SET knowledge_score = ?, status = ? WHERE id = ?", (k_score, status, word_id))
        migrated_count += 1
        
    print(f"Đã hoàn thành migrate {migrated_count} từ trước khi commit.")
    conn.commit()
    conn.close()
    print("Migration committed thành công!")

if __name__ == '__main__':
    run_migration()
