import sqlite3
import math

def calculate_knowledge_score(
    fc_seen: int, fc_corr: int,
    mcq_seen: int, mcq_corr: int,
    mat_seen: int, mat_corr: int,
    fill_seen: int, fill_corr: int
) -> int:
    seen_count = fc_seen + mcq_seen + mat_seen + fill_seen
    if seen_count == 0:
        return 30  # Baseline default score

    review_quality = (fc_corr / fc_seen) * 100.0 if fc_seen > 0 else 0.0
    
    en_vi_seen = mcq_seen + mat_seen
    en_vi_corr = mcq_corr + mat_corr
    quiz_score = (en_vi_corr / en_vi_seen) * 100.0 if en_vi_seen > 0 else 0.0
    
    quiz_score_vi_en = (fill_corr / fill_seen) * 100.0 if fill_seen > 0 else 0.0
    
    seen_score = min(100.0, (math.log(1 + seen_count) / math.log(31)) * 100.0)
    
    final_score = 0.40 * review_quality + 0.20 * quiz_score + 0.30 * quiz_score_vi_en + 0.10 * seen_score
    return max(0, min(100, int(round(final_score))))

def get_status_from_score(score: int) -> str:
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

def run_migration():
    conn = sqlite3.connect('flashcards.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Fetch all words
    cursor.execute("""
        SELECT id, word, status, knowledge_score,
               flashcard_seen, flashcard_correct,
               mcq_seen, mcq_correct,
               matching_seen, matching_correct,
               fill_seen, fill_correct
        FROM words
    """)
    words = cursor.fetchall()
    
    migrated_count = 0
    print(f"Starting score recalculation for {len(words)} words using new formula...")
    
    for word in words:
        word_id = word['id']
        
        fc_seen = word['flashcard_seen'] or 0
        fc_corr = word['flashcard_correct'] or 0
        mcq_seen = word['mcq_seen'] or 0
        mcq_corr = word['mcq_correct'] or 0
        mat_seen = word['matching_seen'] or 0
        mat_corr = word['matching_correct'] or 0
        fill_seen = word['fill_seen'] or 0
        fill_corr = word['fill_correct'] or 0
        
        new_score = calculate_knowledge_score(
            fc_seen, fc_corr,
            mcq_seen, mcq_corr,
            mat_seen, mat_corr,
            fill_seen, fill_corr
        )
        
        new_status = get_status_from_score(new_score)
        
        cursor.execute("""
            UPDATE words
            SET knowledge_score = ?,
                status = ?
            WHERE id = ?
        """, (new_score, new_status, word_id))
        migrated_count += 1
        
    conn.commit()
    conn.close()
    print(f"Done! Successfully updated {migrated_count} words.")

if __name__ == '__main__':
    run_migration()
