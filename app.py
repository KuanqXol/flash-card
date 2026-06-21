import os
import tempfile
import csv
import threading
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, make_response, send_file
from database import (
    init_db, 
    get_stats, 
    get_words_by_status, 
    get_random_words, 
    get_word_by_id,
    get_db,
    get_setting,
    set_setting,
    update_word_after_review,
    FILTERS,
    get_filtered_words
)
from scoring import (
    apply_flashcard_rating,
    apply_matching_result,
    apply_fill_result,
    mark_as_learned,
    mark_as_learning,
    _apply_score_change,
    get_review_queue,
    calculate_mastery_score,
    update_score,
    get_practice_queue,
    apply_forgetting_decay
)

app = Flask(__name__)

# Ensure audio cache directory exists
os.makedirs(os.path.join('static', 'audio'), exist_ok=True)

# TTS Thread-safe structures for generation tracking
generating_lock = threading.Lock()
generating_files = set()
generation_errors = {}
generation_errors_lock = threading.Lock()

def sanitize_word(word):
    if not word:
        return ""
    return "".join(c for c in word if c.isalpha() or c.isspace() or c == '-')

def slugify(word):
    w = word.lower()
    res = []
    for c in w:
        if c.isalnum() or c == '-':
            res.append(c)
        elif c == '_':
            res.append(c)
        elif c == ' ':
            res.append('_')
    return "".join(res)

def cleanup_audio_cache():
    cache_dir = os.path.join('static', 'audio')
    if not os.path.exists(cache_dir):
        return
    
    max_size = 100 * 1024 * 1024
    files = []
    total_size = 0
    try:
        for filename in os.listdir(cache_dir):
            if filename.endswith('.mp3'):
                filepath = os.path.join(cache_dir, filename)
                try:
                    size = os.path.getsize(filepath)
                    files.append((filepath, size))
                    total_size += size
                except Exception as e:
                    app.logger.warning(f"Error accessing cache file {filepath}: {e}")
    except Exception as e:
        app.logger.warning(f"Error listing cache directory: {e}")
        return

    if total_size > max_size:
        try:
            files.sort(key=lambda x: os.path.getmtime(x[0]))
        except Exception as e:
            app.logger.warning(f"Error sorting cache files by mtime: {e}")
            
        for filepath, size in files:
            try:
                os.remove(filepath)
                total_size -= size
                app.logger.info(f"LRU Eviction deleted cache file: {filepath}")
                if total_size <= max_size:
                    break
            except Exception as e:
                app.logger.warning(f"Failed to evict {filepath}: {e}")


# Route GET / -> render template dashboard.html
@app.route('/')
def dashboard():
    stats = get_stats()
    # Fetch all words and display the top 5 most recently added
    recent_words = get_words_by_status('all')[:5]
    return render_template('dashboard.html', stats=stats, recent_words=recent_words)

# Route GET /flashcard -> render flashcard.html
@app.route('/flashcard')
def flashcard():
    return render_template('flashcard.html')

# Route GET /matching -> render matching.html
@app.route('/matching')
def matching():
    return render_template('matching.html')

# Route GET /fill -> render fill.html
@app.route('/fill')
def fill():
    return render_template('fill.html')

# API GET /api/words/random -> retrieves random words for games and reviews
@app.route('/api/words/random')
def api_random_words():
    n = request.args.get('n', 10, type=int)
    status = request.args.get('status', None)
    words = get_random_words(n, status)
    return jsonify(words)

# API POST /api/review -> handles word score & history review log updates
@app.route('/api/review', methods=['POST'])
def api_review_word():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    delta = data.get('delta')
    mode = data.get('mode')
    rating = data.get('rating', None)
    is_correct = data.get('is_correct', None)
    
    if word_id is None or delta is None or not mode:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
    conn = get_db()
    try:
        new_score, status_changed, new_status = _apply_score_change(
            db=conn,
            word_id=int(word_id),
            delta=int(delta),
            mode=mode,
            rating=rating,
            is_correct=is_correct
        )
        return jsonify({'status': 'success', 'upgraded': status_changed})
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Word not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

# API GET /api/flashcard/next -> retrieves next word for flashcard study
@app.route('/api/flashcard/next')
def api_flashcard_next():
    status = request.args.get('status', 'all')
    filter_type = request.args.get('filter', 'all')
    if filter_type == 'all' and status == 'all':
        filter_type = 'smart_priority'
        
    exclude_ids = request.args.getlist('exclude', type=int)
    exclude_id = request.args.get('exclude_id', type=int)
    if exclude_id is not None and exclude_id not in exclude_ids:
        exclude_ids.append(exclude_id)
    
    conn = get_db()
    try:
        queue = get_filtered_words(conn, filter_key=filter_type, status=status, limit=1, exclude_ids=exclude_ids)
        if not queue:
            # Fallback: if we excluded words but found nothing, try without excludes to prevent complete deadlock
            if exclude_ids:
                queue = get_filtered_words(conn, filter_key=filter_type, status=status, limit=1, exclude_ids=[])
            
            if not queue:
                return jsonify({'error': 'no_words'}), 404
        word = queue[0]
        pos_rows = conn.execute(
            "SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order",
            (word['id'],)
        ).fetchall()
        pos_entries = [{'pos': r['pos'], 'meaning': r['meaning']} for r in pos_rows]
    finally:
        conn.close()
        
    return jsonify({
        'id': word['id'],
        'word': word['word'],
        'phonetic': word['phonetic'],
        'translation': word['translation'],
        'short_translation': word['short_translation'],
        'status': word['status'],
        'total_score': word['total_score'],
        'knowledge_score': word['knowledge_score'],
        'review_count': word['review_count'],
        'pos_entries': pos_entries,
        'mastery_score': calculate_mastery_score(word)
    })


# API POST /api/flashcard/flip -> logs flashcard flip (increments seen count)
@app.route('/api/flashcard/flip', methods=['POST'])
def api_flashcard_flip():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
        
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Increment word_stats (for backward compatibility)
        cursor.execute("""
            INSERT INTO word_stats (word_id, exercise, seen, correct)
            VALUES (?, 'flashcard', 1, 0)
            ON CONFLICT(word_id, exercise) DO UPDATE SET seen = seen + 1
        """, (word_id,))
        
        # Increment words table V2 analytics columns
        cursor.execute("""
            UPDATE words SET
                flashcard_seen = flashcard_seen + 1,
                total_seen = total_seen + 1
            WHERE id = ?
        """, (word_id,))
        
        # Fetch current counters to recalculate score
        cursor.execute("""
            SELECT flashcard_seen, flashcard_correct,
                   mcq_seen, mcq_correct,
                   matching_seen, matching_correct,
                   fill_seen, fill_correct
            FROM words WHERE id = ?
        """, (word_id,))
        word = cursor.fetchone()
        
        if word:
            fc_seen = word['flashcard_seen'] or 0
            fc_corr = word['flashcard_correct'] or 0
            mcq_seen = word['mcq_seen'] or 0
            mcq_corr = word['mcq_correct'] or 0
            mat_seen = word['matching_seen'] or 0
            mat_corr = word['matching_correct'] or 0
            fill_seen = word['fill_seen'] or 0
            fill_corr = word['fill_correct'] or 0
            
            tot_seen = fc_seen + mcq_seen + mat_seen + fill_seen
            tot_corr = fc_corr + mcq_corr + mat_corr + fill_corr
            
            import math
            from scoring import _get_status_from_score
            if tot_seen > 0:
                accuracy = tot_corr / tot_seen
                accuracy_bonus = accuracy * 40
                frequency_bonus = min(math.log2(tot_seen + 1) * 10, 30)
                new_score = int(round(30 + accuracy_bonus + frequency_bonus))
                new_score = max(0, min(100, new_score))
            else:
                new_score = 30
                
            new_status = _get_status_from_score(new_score)
            
            cursor.execute("UPDATE words SET knowledge_score = ?, status = ? WHERE id = ?", (new_score, new_status, word_id))
            
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API POST /api/flashcard/rate -> rates a flashcard word, adjusts score and handles potential upgrades
@app.route('/api/flashcard/rate', methods=['POST'])
def api_flashcard_rate():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    rating = data.get('rating')
    is_correct = data.get('is_correct')
    
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
        
    if is_correct is None and rating is not None:
        is_correct = rating >= 4
        
    if is_correct is None:
        return jsonify({'success': False, 'message': 'Missing is_correct or rating'}), 400
        
    conn = get_db()
    try:
        # Check if seen was incremented in this card view. If not, increment it.
        cursor = conn.cursor()
        cursor.execute("SELECT seen FROM word_stats WHERE word_id = ? AND exercise = 'flashcard'", (word_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO word_stats (word_id, exercise, seen, correct) VALUES (?, 'flashcard', 1, 0)", (word_id,))
            
        new_score = update_score(int(word_id), 'flashcard', bool(is_correct), db=conn)
        word = conn.execute("SELECT status, total_score FROM words WHERE id = ?", (word_id,)).fetchone()
        conn.commit()
        return jsonify({
            'success': True,
            'new_score': new_score,
            'new_status': word['status'],
            'status_changed': True,
            'message': 'Rating updated successfully'
        })
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API POST /api/word/mark-learned -> marks word as learned
@app.route('/api/word/mark-learned', methods=['POST'])
def api_mark_learned():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
    conn = get_db()
    try:
        res = mark_as_learned(conn, int(word_id))
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API POST /api/word/mark-learning -> marks word as learning
@app.route('/api/word/mark-learning', methods=['POST'])
def api_mark_learning():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
    conn = get_db()
    try:
        res = mark_as_learning(conn, int(word_id))
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API GET /api/matching/words -> retrieves n random words for matching game
@app.route('/api/matching/words')
def api_matching_words():
    n = request.args.get('n', 6, type=int)
    if n < 4:
        n = 4
    elif n > 10:
        n = 10
        
    status = request.args.get('status', 'all')
    filter_type = request.args.get('filter', 'all')
    if filter_type == 'all' and status == 'all':
        filter_type = 'smart_priority'
        
    conn = get_db()
    try:
        words = get_filtered_words(conn, filter_key=filter_type, status=status, limit=n)
        if len(words) < n:
            all_matching = get_filtered_words(conn, filter_key=filter_type, status=status)
            matching_count = len(all_matching)
            return jsonify({'error': 'not_enough_words', 'available': matching_count})
    finally:
        conn.close()
        
    formatted_words = []
    for word in words:
        short_translation = word.get('short_translation', '')
        if not short_translation or short_translation.strip() == '':
            translation = word.get('translation', '') or ''
            short_translation = translation[:30].strip()
            
        formatted_words.append({
            'id': word['id'],
            'word': word['word'],
            'short_translation': short_translation
        })
        
    return jsonify({'words': formatted_words})


# API POST /api/matching/result -> submits review results for matching game
@app.route('/api/matching/result', methods=['POST'])
def api_matching_result():
    data = request.get_json() or {}
    results = data.get('results', [])
    
    # DEDUP: nếu 1 word_id xuất hiện nhiều lần, chỉ lấy kết quả CUỐI CÙNG
    final_results = {}
    for r in results:
        word_id = r.get('word_id')
        is_correct = r.get('is_correct')
        if word_id is not None and is_correct is not None:
            final_results[int(word_id)] = bool(is_correct)
    
    updated = []
    total_delta = 0
    
    conn = get_db()
    try:
        for word_id, is_correct in final_results.items():
            try:
                res = apply_matching_result(conn, word_id, is_correct)
                total_delta += res['delta']
                updated.append({
                    'word_id': word_id,
                    'delta': res['delta'],
                    'new_score': res['new_score']
                })
            except Exception as e:
                print(f"Error updating word {word_id} in matching result: {e}")
        conn.commit()
    finally:
        conn.close()
            
    return jsonify({
        'updated': updated,
        'total_delta': total_delta
    })

# API GET /api/fill/next -> retrieves 1 random word for fill-in-the-blank game
@app.route('/api/fill/next')
def api_fill_next():
    status = request.args.get('status', 'all')
    filter_type = request.args.get('filter', 'all')
    if filter_type == 'all' and status == 'all':
        filter_type = 'smart_priority'
        
    exclude_ids = request.args.getlist('exclude', type=int)
    exclude_id = request.args.get('exclude_id', type=int)
    if exclude_id is not None and exclude_id not in exclude_ids:
        exclude_ids.append(exclude_id)
        
    conn = get_db()
    try:
        queue = get_filtered_words(conn, filter_key=filter_type, status=status, limit=1, exclude_ids=exclude_ids)
        if not queue:
            if exclude_ids:
                queue = get_filtered_words(conn, filter_key=filter_type, status=status, limit=1, exclude_ids=[])
            if not queue:
                return jsonify({'error': 'no_words'}), 404
        word = queue[0]
    finally:
        conn.close()
        
    return jsonify({
        'id': word['id'],
        'word': word['word'],
        'phonetic': word['phonetic'],
        'translation': word['translation'],
        'short_translation': word['short_translation'],
        'status': word['status'],
        'total_score': word['total_score'],
        'knowledge_score': word['knowledge_score'],
        'mastery_score': calculate_mastery_score(word)
    })


@app.route('/api/fill/evaluate', methods=['POST'])
def api_fill_evaluate():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    is_correct = data.get('is_correct')
    
    if word_id is None or is_correct is None:
        return jsonify({'success': False, 'message': 'Missing word_id or is_correct'}), 400
        
    delta = 5 if is_correct else -1
    
    conn = get_db()
    try:
        new_score = update_score(int(word_id), 'typing', bool(is_correct), db=conn)
        word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        conn.commit()
        return jsonify({
            'success': True,
            'new_score': new_score,
            'mastery_score': calculate_mastery_score(word),
            'delta': delta,
            'consecutive_wrong': word['consecutive_wrong'],
            'needs_review': word['needs_review'],
            'status_changed': True,
            'new_status': word['status'],
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/session/start', methods=['GET'])
def session_start():
    """Khởi tạo session và trả về queue từ đã sắp xếp."""
    status = request.args.get('status', 'all')
    filter_type = request.args.get('filter', 'all')
    if filter_type == 'all' and status == 'all':
        filter_type = 'smart_priority'
        
    word_id = request.args.get('word_id', type=int)
    recent_fails = request.args.get('recent_fails', type=int)
    
    db = get_db()
    try:
        if word_id:
            # Fetch that single word
            row = db.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
            queue = [dict(row)] if row else []
        elif recent_fails:
            # Fetch fails in last 24h
            limit_time = (datetime.now() - timedelta(hours=24)).isoformat()
            rows = db.execute("""
                SELECT * FROM words 
                WHERE last_failed_at IS NOT NULL AND last_failed_at >= ?
                ORDER BY last_failed_at DESC
            """, (limit_time,)).fetchall()
            queue = [dict(r) for r in rows]
        else:
            n = int(request.args.get('n', get_setting(db, 'session_size', '10')))
            queue = get_filtered_words(db, filter_key=filter_type, status=status, limit=n)
        
        # Attach pos_entries and mastery_score to each word in the queue
        for word in queue:
            pos_rows = db.execute(
                "SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order",
                (word['id'],)
            ).fetchall()
            word['pos_entries'] = [{'pos': r['pos'], 'meaning': r['meaning']} for r in pos_rows]
            word['mastery_score'] = calculate_mastery_score(word)
            
        return jsonify({
            'queue': queue,
            'total': len(queue),
            'new_count': sum(1 for w in queue if w['status'] == 'new'),
            'review_count': sum(1 for w in queue if w['status'] != 'new'),
        })
    finally:
        db.close()


@app.route('/api/session/queue', methods=['GET'])
def session_queue():
    import random
    filter_key = request.args.get('filter', 'all')
    status = request.args.get('status', 'all')
    n = request.args.get('n', 20, type=int)
    
    if n < 1:
        n = 20
        
    db = get_db()
    try:
        words = get_filtered_words(db, filter_key=filter_key, status=status, limit=n*3)
        
        # Build composite filter labels, pool mode, use smart
        filter_keys = [fk.strip() for fk in filter_key.split(',') if fk.strip()] if filter_key else []
        labels = []
        pool_mode = False
        use_smart = False
        pool_size = 20
        
        for fk in filter_keys:
            if fk in FILTERS:
                f_obj = FILTERS[fk]
                labels.append(f_obj.get('label', fk))
                if f_obj.get('pool_mode'):
                    pool_mode = True
                    pool_size = max(pool_size, f_obj.get('pool_size', 20))
                if f_obj.get('use_smart_queue'):
                    use_smart = True
                    
        filter_label = ", ".join(labels) if labels else "Tất cả từ"
        
        # Shuffle if not pool_mode and not smart
        if not pool_mode and not use_smart:
            random.shuffle(words)
            
        # Slice lấy n từ đầu tiên
        queue_words = words[:n]
        
        # Thêm pos_entries và mastery_score
        for word in queue_words:
            pos_rows = db.execute(
                "SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order",
                (word['id'],)
            ).fetchall()
            word['pos_entries'] = [{'pos': r['pos'], 'meaning': r['meaning']} for r in pos_rows]
            word['mastery_score'] = calculate_mastery_score(word)
            
        actual_count = len(queue_words)
        
        if pool_mode:
            summary = f"{actual_count} từ {filter_label.lower()} (pool {pool_size} → shuffle)"
        elif use_smart:
            summary = f"{actual_count} từ {filter_label.lower()} (smart priority queue)"
        else:
            summary = f"{actual_count} từ {filter_label.lower()} (shuffle)"
            
        return jsonify({
            'queue': queue_words,
            'total': actual_count,
            'filter': filter_key,
            'filter_label': filter_label,
            'pool_mode': pool_mode,
            'summary': summary
        })
    finally:
        db.close()


def get_daily_progress(db):
    today = datetime.now().strftime('%Y-%m-%d')
    rows = db.execute("""
        SELECT COUNT(*) as count, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as correct
        FROM review_history
        WHERE reviewed_at LIKE ?
    """, (f'{today}%',)).fetchone()
    
    reviewed = rows['count'] or 0
    correct  = rows['correct'] or 0
    wrong    = reviewed - correct
    goal     = int(get_setting(db, 'daily_goal', '20'))
    
    return {
        'reviewed_today': reviewed,
        'correct_today': correct,
        'wrong_today': wrong,
        'accuracy_today': round(correct / reviewed * 100, 1) if reviewed > 0 else 0,
        'goal': goal,
        'goal_percent': min(100, round(reviewed / goal * 100)) if goal > 0 else 0,
    }


@app.route('/api/analytics/weak-words')
def api_weak_words():
    n = request.args.get('n', 10, type=int)
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT *, (correct_count * 1.0 / (correct_count + wrong_count)) as accuracy 
            FROM words 
            WHERE review_count >= 3 
            ORDER BY accuracy ASC 
            LIMIT ?
        """, (n,)).fetchall()
        res = []
        for r in rows:
            w_dict = dict(r)
            w_dict['mastery_score'] = calculate_mastery_score(w_dict)
            res.append(w_dict)
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/analytics/forgotten')
def api_forgotten_words():
    n = request.args.get('n', 10, type=int)
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * 
            FROM words 
            WHERE status != 'mastered' AND status != 'learned' 
            ORDER BY last_reviewed ASC NULLS FIRST 
            LIMIT ?
        """, (n,)).fetchall()
        res = []
        for r in rows:
            w_dict = dict(r)
            if w_dict.get('last_reviewed'):
                try:
                    delta = datetime.now() - datetime.fromisoformat(w_dict['last_reviewed'])
                    days_ago = int(delta.total_seconds() / 86400)
                except:
                    days_ago = 999
            else:
                if w_dict.get('date_added'):
                    try:
                        delta = datetime.now() - datetime.fromisoformat(w_dict['date_added'])
                        days_ago = int(delta.total_seconds() / 86400)
                    except:
                        days_ago = 999
                else:
                    days_ago = 999
            w_dict['days_ago'] = days_ago
            w_dict['mastery_score'] = calculate_mastery_score(w_dict)
            res.append(w_dict)
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/analytics/danger')
def api_danger_words():
    n = request.args.get('n', 10, type=int)
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT *, (correct_count * 1.0 / (correct_count + wrong_count)) as accuracy 
            FROM words 
            WHERE review_count > 5 AND (correct_count * 1.0 / (correct_count + wrong_count)) < 0.5 
            ORDER BY accuracy ASC 
            LIMIT ?
        """, (n,)).fetchall()
        res = []
        for r in rows:
            w_dict = dict(r)
            w_dict['mastery_score'] = calculate_mastery_score(w_dict)
            res.append(w_dict)
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/analytics/recent-fails')
def api_recent_fails():
    hours = request.args.get('hours', 24, type=int)
    limit_time = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * 
            FROM words 
            WHERE last_failed_at IS NOT NULL AND last_failed_at >= ? 
            ORDER BY last_failed_at DESC
        """, (limit_time,)).fetchall()
        res = []
        for r in rows:
            w_dict = dict(r)
            w_dict['mastery_score'] = calculate_mastery_score(w_dict)
            delta = datetime.now() - datetime.fromisoformat(w_dict['last_failed_at'])
            w_dict['hours_ago'] = round(delta.total_seconds() / 3600, 2)
            res.append(w_dict)
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/analytics/daily-progress')
def api_daily_progress():
    conn = get_db()
    try:
        progress = get_daily_progress(conn)
        weekly = []
        for i in range(6, -1, -1):
            day_date = datetime.now() - timedelta(days=i)
            day_str = day_date.strftime('%Y-%m-%d')
            row = conn.execute("""
                SELECT COUNT(*) as count, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as correct
                FROM review_history
                WHERE reviewed_at LIKE ?
            """, (f'{day_str}%',)).fetchone()
            
            day_reviewed = row['count'] or 0
            day_correct = row['correct'] or 0
            day_accuracy = round(day_correct / day_reviewed * 100, 1) if day_reviewed > 0 else 0
            weekly.append({
                'date': day_str,
                'day_label': day_date.strftime('%d/%m'),
                'review_count': day_reviewed,
                'accuracy': day_accuracy
            })
            
        # Get requested year, default to current year
        year = request.args.get('year', datetime.now().year, type=int)
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31T23:59:59"
        
        rows = conn.execute("""
            SELECT substr(reviewed_at, 1, 10) as day_str, COUNT(*) as count
            FROM review_history
            WHERE reviewed_at >= ? AND reviewed_at <= ?
            GROUP BY day_str
        """, (start_date, end_date)).fetchall()
        counts_by_day = {r['day_str']: r['count'] for r in rows}
        
        import calendar
        is_leap = calendar.isleap(year)
        days_in_year = 366 if is_leap else 365
        
        heatmap = []
        year_start = datetime(year, 1, 1)
        for i in range(days_in_year):
            day_date = year_start + timedelta(days=i)
            day_str = day_date.strftime('%Y-%m-%d')
            heatmap.append({
                'date': day_str,
                'review_count': counts_by_day.get(day_str, 0)
            })
            
        return jsonify({
            'today': progress,
            'weekly': weekly,
            'heatmap': heatmap
        })
    finally:
        conn.close()


@app.route('/api/words/recently-failed')
def api_recently_failed():
    hours = request.args.get('hours', 24, type=int)
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT *, 
                   ROUND((julianday('now','localtime') - julianday(last_failed_at)) * 24, 1) as hours_ago
            FROM words
            WHERE last_failed_at IS NOT NULL AND datetime(last_failed_at) >= datetime('now', ?, 'localtime')
            ORDER BY last_failed_at DESC
        """, (f'-{hours} hours',)).fetchall()
        
        res = []
        for r in rows:
            w_dict = dict(r)
            pos_rows = conn.execute(
                "SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order",
                (w_dict['id'],)
            ).fetchall()
            w_dict['pos_entries'] = [{'pos': pr['pos'], 'meaning': pr['meaning']} for pr in pos_rows]
            w_dict['mastery_score'] = calculate_mastery_score(w_dict)
            res.append(w_dict)
            
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/filters/list')
def api_filters_list():
    groups = []
    group_ids = ['time', 'combo', 'performance', 'smart']
    group_labels = {
        'time': 'Thời gian',
        'combo': 'Kết hợp',
        'performance': 'Hiệu suất',
        'smart': 'Thông minh'
    }
    for gid in group_ids:
        filters_in_group = []
        for fid, fval in FILTERS.items():
            if fval.get('group') == gid:
                item = {
                    'id': fid,
                    'label': fval['label'],
                    'pool_mode': fval.get('pool_mode', False)
                }
                if 'description' in fval:
                    item['description'] = fval['description']
                if 'pool_size' in fval:
                    item['pool_size'] = fval['pool_size']
                filters_in_group.append(item)
        groups.append({
            'id': gid,
            'label': group_labels[gid],
            'filters': filters_in_group
        })
    return jsonify({'groups': groups})


@app.route('/words')
def words_page():
    return render_template('words.html')


@app.route('/api/words/search')
def api_words_search():
    import time
    start_time = time.time()
    
    q = request.args.get('q', '').strip()
    statuses_str = request.args.get('statuses', '').strip()
    time_filters_str = request.args.get('time_filters', '').strip()
    perf_filters_str = request.args.get('perf_filters', '').strip()
    sort = request.args.get('sort', 'alpha')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 40, type=int)
    
    statuses = [s.strip() for s in statuses_str.split(',') if s.strip()] if statuses_str else []
    time_filters = [f.strip() for f in time_filters_str.split(',') if f.strip()] if time_filters_str else []
    perf_filters = [f.strip() for f in perf_filters_str.split(',') if f.strip()] if perf_filters_str else []
    
    # Backward compatibility with single status and filter params
    status_param = request.args.get('status', 'all')
    filter_param = request.args.get('filter', 'all')
    
    if not statuses and status_param != 'all':
        statuses = [status_param]
        
    if not time_filters and not perf_filters and filter_param != 'all':
        if filter_param in FILTERS:
            grp = FILTERS[filter_param].get('group')
            if grp == 'time':
                time_filters = [filter_param]
            elif grp == 'performance':
                perf_filters = [filter_param]
    
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 40
        
    conn = get_db()
    
    where_clauses = []
    params = []
    
    if q:
        where_clauses.append("(word LIKE ? OR translation LIKE ?)")
        params.append(f"%{q}%")
        params.append(f"%{q}%")
        
    # Status filter (OR logic within status group)
    if statuses:
        status_clauses = []
        for s in statuses:
            if s == 'learned':
                status_clauses.append("status = 'mastered'")
            elif s == 'learning':
                status_clauses.append("status IN ('learning', 'danger', 'familiar')")
            elif s == 'new':
                status_clauses.append("status = 'new'")
        if status_clauses:
            where_clauses.append("(" + " OR ".join(status_clauses) + ")")
            
    # Time filters (OR logic within time group)
    if time_filters:
        time_clauses = []
        for tf in time_filters:
            if tf in FILTERS:
                sql_cond = FILTERS[tf].get('sql')
                if sql_cond:
                    time_clauses.append(sql_cond)
        if time_clauses:
            where_clauses.append("(" + " OR ".join(time_clauses) + ")")
            
    # Performance filters (OR logic within performance group)
    if perf_filters:
        perf_clauses = []
        for pf in perf_filters:
            if pf in FILTERS:
                sql_cond = FILTERS[pf].get('sql')
                if sql_cond:
                    perf_clauses.append(sql_cond)
        if perf_clauses:
            where_clauses.append("(" + " OR ".join(perf_clauses) + ")")
        
    where_clause_str = ""
    if where_clauses:
        where_clause_str = "WHERE " + " AND ".join(where_clauses)
        
    sort_clauses = {
        'alpha': 'word COLLATE NOCASE ASC',
        'score_desc': 'knowledge_score DESC, id DESC',
        'score_asc': 'knowledge_score ASC, id ASC',
        'recent': 'date_added DESC, id DESC',
        'oldest_review': 'last_reviewed ASC NULLS FIRST, id ASC'
    }
    
    order_clause = sort_clauses.get(sort, 'word COLLATE NOCASE ASC')
    
    count_query = f"SELECT COUNT(*) FROM words {where_clause_str}"
    total = conn.execute(count_query, params).fetchone()[0]
    
    offset = (page - 1) * per_page
    data_query = f"""
        SELECT * FROM words 
        {where_clause_str} 
        ORDER BY {order_clause} 
        LIMIT ? OFFSET ?
    """
    
    data_params = list(params)
    data_params.extend([per_page, offset])
    
    rows = conn.execute(data_query, data_params).fetchall()
    
    words_list = []
    for r in rows:
        w_dict = dict(r)
        w_dict['mastery_score'] = calculate_mastery_score(w_dict)
        pos_rows = conn.execute(
            "SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order",
            (w_dict['id'],)
        ).fetchall()
        w_dict['pos_entries'] = [{'pos': pr['pos'], 'meaning': pr['meaning']} for pr in pos_rows]
        words_list.append(w_dict)
        
    conn.close()
    
    import math
    pages = math.ceil(total / per_page) if total > 0 else 1
    query_time = round((time.time() - start_time) * 1000, 2)
    
    return jsonify({
        'words': words_list,
        'total': total,
        'page': page,
        'pages': pages,
        'query_time_ms': query_time
    })


@app.route('/api/words/add', methods=['POST'])
def api_words_add():
    from import_csv import parse_pos_entries, get_short_translation
    
    data = request.get_json() or {}
    word = data.get('word', '').strip()
    phonetic = data.get('phonetic', '').strip()
    translation = data.get('translation', '').strip()
    example = data.get('example', '').strip()
    
    if not word or not translation:
        return jsonify({'success': False, 'error': 'invalid', 'message': 'Word and translation cannot be empty'}), 400
        
    conn = get_db()
    try:
        # Check duplicate case-insensitively
        row = conn.execute("SELECT id FROM words WHERE LOWER(word) = LOWER(?)", (word,)).fetchone()
        if row:
            return jsonify({'success': False, 'error': 'duplicate', 'message': 'Word already exists'}), 400
            
        pos_entries = parse_pos_entries(translation)
        short_translation = get_short_translation(pos_entries, translation)
        
        now = datetime.now().isoformat()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO words (word, phonetic, translation, short_translation, date_added, status, total_score, review_count, has_been_rated_five, last_reviewed, created_at, knowledge_score, example)
            VALUES (?, ?, ?, ?, ?, 'new', 0, 0, 0, NULL, ?, 30, ?)
        """, (word, phonetic or None, translation, short_translation, now[:10], now, example or None))
        
        word_id = cursor.lastrowid
        
        for i, entry in enumerate(pos_entries):
            cursor.execute("""
                INSERT INTO word_pos (word_id, pos, meaning, sort_order)
                VALUES (?, ?, ?, ?)
            """, (word_id, entry['pos'], entry['meaning'], i))
            
        conn.commit()
        
        inserted_row = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        inserted_dict = dict(inserted_row)
        inserted_dict['mastery_score'] = 0.0
        inserted_dict['pos_entries'] = pos_entries
        
        return jsonify({'success': True, 'word': inserted_dict})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/words/<int:word_id>/edit', methods=['PUT'])
def api_words_edit(word_id):
    from import_csv import parse_pos_entries, get_short_translation
    
    data = request.get_json() or {}
    word = data.get('word', '').strip()
    phonetic = data.get('phonetic', '').strip()
    translation = data.get('translation', '').strip()
    example = data.get('example', '').strip()
    
    if not word or not translation:
        return jsonify({'success': False, 'error': 'invalid', 'message': 'Word and translation cannot be empty'}), 400
        
    conn = get_db()
    try:
        # Check if the word exists
        existing = conn.execute("SELECT id FROM words WHERE id = ?", (word_id,)).fetchone()
        if not existing:
            return jsonify({'success': False, 'error': 'not_found', 'message': 'Word not found'}), 404
            
        # Check duplicate case-insensitively for other words
        dup = conn.execute("SELECT id FROM words WHERE LOWER(word) = LOWER(?) AND id != ?", (word, word_id)).fetchone()
        if dup:
            return jsonify({'success': False, 'error': 'duplicate', 'message': 'Word spelling already exists under another entry'}), 400
            
        pos_entries = parse_pos_entries(translation)
        short_translation = get_short_translation(pos_entries, translation)
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE words
            SET word = ?, phonetic = ?, translation = ?, short_translation = ?, example = ?
            WHERE id = ?
        """, (word, phonetic or None, translation, short_translation, example or None, word_id))
        
        # Reset POS list
        cursor.execute("DELETE FROM word_pos WHERE word_id = ?", (word_id,))
        for i, entry in enumerate(pos_entries):
            cursor.execute("""
                INSERT INTO word_pos (word_id, pos, meaning, sort_order)
                VALUES (?, ?, ?, ?)
            """, (word_id, entry['pos'], entry['meaning'], i))
            
        conn.commit()
        
        updated_row = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        updated_dict = dict(updated_row)
        updated_dict['mastery_score'] = calculate_mastery_score(updated_dict)
        updated_dict['pos_entries'] = pos_entries
        
        return jsonify({'success': True, 'word': updated_dict})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/words/<int:word_id>', methods=['GET'])
def api_get_word(word_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM words WHERE id = ?", (word_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Word not found'}), 404
        word = dict(row)
        
        # Load POS entries
        pos_rows = conn.execute("SELECT pos, meaning FROM word_pos WHERE word_id=? ORDER BY sort_order", (word_id,)).fetchall()
        word['pos_entries'] = [{'pos': r['pos'], 'meaning': r['meaning']} for r in pos_rows]
        
        # Load mastery score
        word['mastery_score'] = calculate_mastery_score(word)
        
        return jsonify({'success': True, 'word': word})
    finally:
        conn.close()


@app.route('/api/words/<int:word_id>', methods=['DELETE'])
def api_words_delete(word_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM review_history WHERE word_id = ?", (word_id,))
        cursor.execute("DELETE FROM word_pos WHERE word_id = ?", (word_id,))
        cursor.execute("DELETE FROM words WHERE id = ?", (word_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Word not found'}), 404
            
        conn.commit()
        return jsonify({'success': True, 'deleted_id': word_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/words/bulk-delete', methods=['POST'])
def api_words_bulk_delete():
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'message': 'Missing ids'}), 400
        
    conn = get_db()
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in ids)
        
        cursor.execute(f"DELETE FROM review_history WHERE word_id IN ({placeholders})", ids)
        cursor.execute(f"DELETE FROM word_pos WHERE word_id IN ({placeholders})", ids)
        cursor.execute(f"DELETE FROM words WHERE id IN ({placeholders})", ids)
        
        affected = cursor.rowcount
        conn.commit()
        return jsonify({'success': True, 'deleted_count': affected})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/words/<int:word_id>/history')
def api_word_history(word_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT mode, score_delta, is_correct, rating, reviewed_at
            FROM review_history
            WHERE word_id = ?
            ORDER BY reviewed_at DESC
        """, (word_id,)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()



@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings_dict = {r['key']: r['value'] for r in rows}
        
        # Calculate display_name
        user_name = settings_dict.get('user_name', '').strip()
        if not user_name or user_name.lower() == 'guest':
            settings_dict['display_name'] = 'Khách'
        else:
            settings_dict['display_name'] = user_name
            
        return jsonify(settings_dict)
    finally:
        conn.close()


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    allowed = {'daily_goal', 'session_size', 'matching_pairs', 'new_word_ratio', 'theme', 'user_name', 'tts_speed_normal', 'tts_speed_slow'}
    conn = get_db()
    try:
        for key, value in data.items():
            if key in allowed:
                set_setting(conn, key, str(value))
        return jsonify({'success': True})
    finally:
        conn.close()



# API GET /api/stats -> retrieves comprehensive progress statistics
@app.route('/api/stats')
def api_stats():
    try:
        stats = get_stats()
        total = stats.get('total', 0)
        knowledge_score_sum = stats.get('knowledge_score_sum', 0)
        
        avg_score = 0.0
        if total > 0:
            avg_score = round(knowledge_score_sum / total, 2)
            
        stats['avg_score'] = avg_score
        return jsonify(stats)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API GET /api/words/list -> retrieves sorted and paginated words list
@app.route('/api/words/list')
def api_words_list():
    status = request.args.get('status', 'all')
    sort = request.args.get('sort', 'score_desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 30
        
    conn = get_db()
    cursor = conn.cursor()
    
    query_cond = ""
    params = []
    if status == 'needs_review':
        query_cond = "WHERE needs_review = 1"
    elif status != 'all':
        query_cond = "WHERE status = ?"
        params.append(status)
        
    count_query = f"SELECT COUNT(*) FROM words {query_cond}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    sort_orders = {
        'score_desc': 'knowledge_score DESC, id DESC',
        'score_asc': 'knowledge_score ASC, id ASC',
        'alpha': 'word COLLATE NOCASE ASC',
        'date_added': 'date_added DESC, id DESC',
        'last_reviewed': 'last_reviewed DESC, id DESC'
    }
    order_clause = sort_orders.get(sort, 'total_score DESC, id DESC')
    
    limit = per_page
    offset = (page - 1) * per_page
    
    fetch_query = f"""
        SELECT *
        FROM words
        {query_cond}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    
    fetch_params = list(params)
    fetch_params.extend([limit, offset])
    
    cursor.execute(fetch_query, fetch_params)
    rows = cursor.fetchall()
    conn.close()
    
    words_list = []
    for row in rows:
        w_dict = dict(row)
        w_dict['mastery_score'] = calculate_mastery_score(w_dict)
        words_list.append(w_dict)
        
    import math
    pages = math.ceil(total / per_page) if total > 0 else 1
    
    return jsonify({
        'words': words_list,
        'total': total,
        'page': page,
        'pages': pages
    })


# API GET /api/words/top -> retrieves top n words with highest score
@app.route('/api/words/top')
def api_words_top():
    n = request.args.get('n', 5, type=int)
    if n < 1:
        n = 5
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * 
        FROM words 
        ORDER BY knowledge_score DESC, id DESC 
        LIMIT ?
    """, (n,))
    rows = cursor.fetchall()
    conn.close()
    
    top_words = []
    for r in rows:
        w_dict = dict(r)
        w_dict['mastery_score'] = calculate_mastery_score(w_dict)
        top_words.append(w_dict)
        
    return jsonify(top_words)

# API POST /api/import -> uploads and imports a CSV file
@app.route('/api/import', methods=['POST'])
def api_import_csv():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part in request'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
        
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'Uploaded file is not a CSV'}), 400
        
    try:
        # Save file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
            temp_path = temp_file.name
            file.save(temp_path)
            
        try:
            # Import from CSV
            from import_csv import import_from_csv
            result = import_from_csv(temp_path)
            return jsonify({
                'success': True,
                'imported': result['imported'],
                'updated': result['updated'],
                'skipped': result['skipped'],
                'total': result['total']
            })
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API GET /api/export -> exports database content as downloadable CSV
@app.route('/api/export')
def api_export_progress():
    export_format = request.args.get('format', 'csv')
    if export_format != 'csv':
        return jsonify({'success': False, 'error': 'Unsupported format'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Retrieve all words for CSV construction
    cursor.execute("""
        SELECT word, phonetic, translation, status, total_score, review_count, last_reviewed, date_added
        FROM words
        ORDER BY word COLLATE NOCASE ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    # Generate CSV using StringIO
    si = StringIO()
    cw = csv.writer(si)
    
    # Header row
    cw.writerow(['word', 'phonetic', 'translation', 'status', 'total_score', 'review_count', 'last_reviewed', 'date_added'])
    
    # Data rows
    for r in rows:
        cw.writerow([
            r['word'],
            r['phonetic'] or '',
            r['translation'] or '',
            r['status'],
            r['total_score'],
            r['review_count'],
            r['last_reviewed'] or '',
            r['date_added'] or ''
        ])
        
    output = si.getvalue()
    si.close()
    
    # Filename format: flashvocab_export_YYYYMMDD.csv
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"flashvocab_export_{date_str}.csv"
    
    response = make_response(output)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    
    return response

# API POST /api/word/<id>/reset -> resets statistics for a single word
@app.route('/api/word/<int:word_id>/reset', methods=['POST'])
def api_reset_word(word_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE words
            SET status = 'new',
                total_score = 0,
                has_been_rated_five = 0,
                review_count = 0,
                last_reviewed = NULL
            WHERE id = ?
        """, (word_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Word not found'}), 404
            
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# API POST /api/word/<id>/dismiss-warning -> sets needs_review = 0 for a word
@app.route('/api/word/<int:word_id>/dismiss-warning', methods=['POST'])
def api_dismiss_warning(word_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE words SET needs_review = 0 WHERE id = ?", (word_id,))
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Word not found'}), 404
            
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/word/<int:word_id>/toggle-warning', methods=['POST'])
def api_toggle_warning(word_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        row = conn.execute("SELECT needs_review FROM words WHERE id = ?", (word_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Word not found'}), 404
        new_val = 0 if row['needs_review'] else 1
        cursor.execute("UPDATE words SET needs_review = ? WHERE id = ?", (new_val, word_id))
        conn.commit()
        return jsonify({'success': True, 'needs_review': new_val})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()



# API POST /api/words/bulk-action -> applies status overrides or resets on list of words
@app.route('/api/words/bulk-action', methods=['POST'])
def api_words_bulk_action():
    data = request.get_json() or {}
    action = data.get('action')
    word_ids = data.get('word_ids', [])
    
    if not action or not word_ids:
        return jsonify({'success': False, 'message': 'Missing action or word_ids'}), 400
        
    if action not in ['mark_learned', 'mark_learning', 'reset']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Build query parameters placeholders e.g. (?, ?, ?)
        placeholders = ','.join('?' for _ in word_ids)
        
        if action == 'mark_learned':
            for wid in word_ids:
                mark_as_learned(conn, int(wid))
            affected = len(word_ids)
        elif action == 'mark_learning':
            for wid in word_ids:
                mark_as_learning(conn, int(wid))
            affected = len(word_ids)
        elif action == 'reset':
            cursor.execute(f"""
                UPDATE words
                SET status = 'new',
                    knowledge_score = 30,
                    total_score = 0,
                    has_been_rated_five = 0,
                    review_count = 0,
                    last_reviewed = NULL
                WHERE id IN ({placeholders})
            """, word_ids)
            affected = cursor.rowcount
        conn.commit()
        
        return jsonify({
            'success': True,
            'affected': affected
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

def get_mcq_options(db, word, pool_words):
    word_id = word['id']
    correct_text = word['short_translation'] or word['translation']
    if not correct_text:
        correct_text = ''
    correct_text = correct_text.strip()
    
    pos_rows = db.execute("SELECT pos FROM word_pos WHERE word_id = ?", (word_id,)).fetchall()
    pos_list = [r['pos'] for r in pos_rows if r['pos']]
    
    wrong_options = []
    
    if pos_list:
        placeholders = ','.join('?' for _ in pos_list)
        query = f"""
            SELECT DISTINCT w.id, w.word, w.translation, w.short_translation 
            FROM words w
            JOIN word_pos wp ON w.id = wp.word_id
            WHERE wp.pos IN ({placeholders}) AND w.id != ?
            ORDER BY RANDOM() LIMIT 30
        """
        params = pos_list + [word_id]
        pos_matching_rows = db.execute(query, params).fetchall()
        for row in pos_matching_rows:
            opt_text = (row['short_translation'] or row['translation'] or '').strip()
            if opt_text and opt_text != correct_text and opt_text not in wrong_options:
                wrong_options.append(opt_text)
                if len(wrong_options) >= 3:
                    break
                    
    if len(wrong_options) < 3:
        query = """
            SELECT id, word, translation, short_translation 
            FROM words 
            WHERE id != ? 
            ORDER BY RANDOM() LIMIT 30
        """
        random_rows = db.execute(query, (word_id,)).fetchall()
        for row in random_rows:
            opt_text = (row['short_translation'] or row['translation'] or '').strip()
            if opt_text and opt_text != correct_text and opt_text not in wrong_options:
                wrong_options.append(opt_text)
                if len(wrong_options) >= 3:
                    break
                    
    while len(wrong_options) < 3:
        wrong_options.append(f"Nghĩa giả lập {len(wrong_options) + 1}")
        
    wrong_options = wrong_options[:3]
    all_choices = wrong_options + [correct_text]
    import random
    random.shuffle(all_choices)
    
    return all_choices, correct_text

@app.route('/mcq')
def mcq():
    return render_template('mcq.html')

@app.route('/api/mcq/queue', methods=['GET'])
def api_mcq_queue():
    import random
    filter_key = request.args.get('filter', 'smart_priority')
    status = request.args.get('status', 'all')
    n = request.args.get('n', 10, type=int)
    
    if n < 1:
        n = 10
        
    db = get_db()
    try:
        words = get_filtered_words(db, filter_key=filter_key, status=status, limit=n*3)
        
        # Build composite filter labels, pool mode, use smart
        filter_keys = [fk.strip() for fk in filter_key.split(',') if fk.strip()] if filter_key else []
        labels = []
        pool_mode = False
        use_smart = False
        pool_size = 20
        
        for fk in filter_keys:
            if fk in FILTERS:
                f_obj = FILTERS[fk]
                labels.append(f_obj.get('label', fk))
                if f_obj.get('pool_mode'):
                    pool_mode = True
                    pool_size = max(pool_size, f_obj.get('pool_size', 20))
                if f_obj.get('use_smart_queue'):
                    use_smart = True
                    
        filter_label = ", ".join(labels) if labels else "Tất cả từ"
        
        # Shuffle if not pool_mode and not smart
        if not pool_mode and not use_smart:
            random.shuffle(words)
            
        queue_words = words[:n]
        
        queue = []
        for word in queue_words:
            wid = word['id']
            pos_rows = db.execute(
                "SELECT pos, meaning FROM word_pos WHERE word_id = ? ORDER BY sort_order", 
                (wid,)
            ).fetchall()
            word['pos_entries'] = [{'pos': r['pos'], 'meaning': r['meaning']} for r in pos_rows]
            word['mastery_score'] = calculate_mastery_score(word)
            
            choices, correct_answer = get_mcq_options(db, word, queue)
            
            queue.append({
                'id': word['id'],
                'word': word['word'],
                'phonetic': word['phonetic'],
                'translation': word['translation'],
                'short_translation': word['short_translation'],
                'status': word['status'],
                'knowledge_score': word['knowledge_score'],
                'pos_entries': word['pos_entries'],
                'mastery_score': word['mastery_score'],
                'choices': choices,
                'correct_answer': correct_answer
            })
            
        return jsonify({
            'queue': queue,
            'total': len(queue),
            'filter': filter_key,
            'filter_label': filter_label,
            'summary': f"Phiên trắc nghiệm: {len(queue)} từ"
        })
    finally:
        db.close()

@app.route('/api/mcq/evaluate', methods=['POST'])
def api_mcq_evaluate():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    is_correct = data.get('is_correct')
    choice = data.get('choice')
    
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
        
    conn = get_db()
    try:
        if choice is not None:
            word_row = conn.execute("SELECT translation, short_translation FROM words WHERE id = ?", (word_id,)).fetchone()
            if word_row:
                correct_text = (word_row['short_translation'] or word_row['translation'] or '').strip()
                is_correct = choice.strip() == correct_text
                
        if is_correct is None:
            return jsonify({'success': False, 'message': 'Missing is_correct or choice'}), 400
            
        new_score = update_score(int(word_id), 'mcq', bool(is_correct), db=conn)
        word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        conn.commit()
        return jsonify({
            'success': True,
            'new_score': new_score,
            'mastery_score': calculate_mastery_score(word),
            'is_correct': bool(is_correct),
            'new_status': word['status']
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/tts')
def api_tts():
    word = request.args.get('word', '').strip()
    speed = request.args.get('speed', 'normal').strip().lower()
    
    clean_word = sanitize_word(word)
    if not clean_word:
        return jsonify({'error': 'Invalid or empty word'}), 400
        
    is_slow = (speed == 'slow')
    filename = slugify(clean_word) + ('_slow.mp3' if is_slow else '.mp3')
    filepath = os.path.join('static', 'audio', filename)
    
    # If already cached, serve immediately
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='audio/mpeg')
        
    # Check if this file is currently being generated
    with generating_lock:
        is_generating = filename in generating_files
        if not is_generating:
            generating_files.add(filename)
            
    def run_gtts_generation():
        try:
            from gtts import gTTS
            tts = gTTS(text=clean_word, lang='en', tld='us', slow=is_slow)
            temp_fd, temp_path = tempfile.mkstemp(suffix='.mp3', dir=os.path.join('static', 'audio'))
            os.close(temp_fd)
            try:
                tts.save(temp_path)
                cleanup_audio_cache()
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                os.rename(temp_path, filepath)
                with generation_errors_lock:
                    generation_errors.pop(filename, None)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                raise e
        except Exception as e:
            app.logger.warning(f"gTTS error for word '{clean_word}': {e}")
            with generation_errors_lock:
                generation_errors[filename] = str(e)
        finally:
            with generating_lock:
                generating_files.discard(filename)

    if not is_generating:
        thread = threading.Thread(target=run_gtts_generation)
        thread.start()
        thread.join(timeout=2.0)
    else:
        import time
        start_time = time.time()
        while time.time() - start_time < 2.0:
            if os.path.exists(filepath):
                break
            time.sleep(0.1)

    # Re-check if file exists
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='audio/mpeg')
        
    with generation_errors_lock:
        error = generation_errors.get(filename)
        
    if error:
        with generation_errors_lock:
            generation_errors.pop(filename, None)
        return jsonify({'error': 'TTS generation failed', 'details': error}), 503
        
    with generating_lock:
        still_generating = filename in generating_files
        
    if still_generating:
        return jsonify({'status': 'processing', 'message': 'Audio is being generated'}), 202
    else:
        return jsonify({'error': 'TTS generation failed'}), 503

@app.route('/api/tts/cache-stats')
def api_tts_cache_stats():
    cache_dir = os.path.join('static', 'audio')
    total_files = 0
    total_size = 0
    if os.path.exists(cache_dir):
        for filename in os.listdir(cache_dir):
            if filename.endswith('.mp3'):
                filepath = os.path.join(cache_dir, filename)
                try:
                    total_files += 1
                    total_size += os.path.getsize(filepath)
                except Exception as e:
                    app.logger.warning(f"Error reading file size for {filepath}: {e}")
                    
    total_size_mb = round(total_size / (1024 * 1024), 2)
    return jsonify({
        'total_files': total_files,
        'total_size_mb': total_size_mb
    })

if __name__ == '__main__':
    # Initialize SQLite database and tables
    init_db()
    print("Database initialized successfully.")
    
    # Run the Flask app on port 5000 in debug mode
    app.run(port=5000, debug=True)
