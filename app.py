import os
import tempfile
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, jsonify, make_response
from database import (
    init_db, 
    get_stats, 
    get_words_by_status, 
    get_random_words, 
    get_word_by_id,
    get_db
)
from scoring import (
    apply_flashcard_rating,
    apply_matching_result,
    apply_fill_result,
    mark_as_learned,
    mark_as_learning,
    _apply_score_change
)

app = Flask(__name__)

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
    exclude_id = request.args.get('exclude_id', None, type=int)
    
    words = get_random_words(1, status, exclude_id)
    if not words:
        # If no words matching the filter were found, try without excluding the ID
        if exclude_id is not None:
            words = get_random_words(1, status, None)
            
        if not words:
            return jsonify({'error': 'no_words'})
            
    word = words[0]
    return jsonify({
        'id': word['id'],
        'word': word['word'],
        'phonetic': word['phonetic'],
        'translation': word['translation'],
        'short_translation': word['short_translation'],
        'status': word['status'],
        'total_score': word['total_score'],
        'review_count': word['review_count']
    })

# API POST /api/flashcard/rate -> rates a flashcard word, adjusts score and handles potential upgrades
@app.route('/api/flashcard/rate', methods=['POST'])
def api_flashcard_rate():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    rating = data.get('rating')
    
    if word_id is None or rating is None:
        return jsonify({'success': False, 'message': 'Missing word_id or rating'}), 400
        
    try:
        word_id = int(word_id)
        rating = int(rating)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid type for word_id or rating'}), 400
        
    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        
    conn = get_db()
    try:
        res = apply_flashcard_rating(conn, word_id, rating)
        return jsonify({
            'success': True,
            'new_score': res['new_score'],
            'new_status': res['new_status'],
            'status_changed': res['status_changed'],
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
    
    words = get_random_words(n, status)
    if len(words) < n:
        matching_count = len(get_words_by_status(status))
        return jsonify({'error': 'not_enough_words', 'available': matching_count})
        
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
    
    updated = []
    total_delta = 0
    
    conn = get_db()
    try:
        for item in results:
            word_id = item.get('word_id')
            is_correct = item.get('is_correct')
            
            if word_id is None or is_correct is None:
                continue
                
            try:
                res = apply_matching_result(conn, int(word_id), bool(is_correct))
                total_delta += res['delta']
                updated.append({
                    'word_id': int(word_id),
                    'delta': res['delta'],
                    'new_score': res['new_score']
                })
            except Exception as e:
                print(f"Error updating word {word_id} in matching result: {e}")
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
    exclude_id = request.args.get('exclude_id', None, type=int)
    
    words = get_random_words(1, status, exclude_id)
    if not words:
        if exclude_id is not None:
            words = get_random_words(1, status, None)
            
        if not words:
            return jsonify({'error': 'no_words'})
            
    word = words[0]
    return jsonify({
        'id': word['id'],
        'word': word['word'],
        'phonetic': word['phonetic'],
        'translation': word['translation'],
        'short_translation': word['short_translation'],
        'status': word['status'],
        'total_score': word['total_score']
    })

# API POST /api/fill/evaluate -> evaluates user spelling/meaning guess and updates score
@app.route('/api/fill/evaluate', methods=['POST'])
def api_fill_evaluate():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    is_correct = data.get('is_correct')
    
    if word_id is None or is_correct is None:
        return jsonify({'success': False, 'message': 'Missing word_id or is_correct'}), 400
        
    conn = get_db()
    try:
        res = apply_fill_result(conn, int(word_id), bool(is_correct))
        return jsonify({
            'success': True,
            'new_score': res['new_score'],
            'delta': res['delta']
        })
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API GET /api/stats -> retrieves comprehensive progress statistics
@app.route('/api/stats')
def api_stats():
    try:
        stats = get_stats()
        total = stats.get('total', 0)
        total_score_sum = stats.get('total_score_sum', 0)
        
        avg_score = 0.0
        if total > 0:
            avg_score = round(total_score_sum / total, 2)
            
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
    if status != 'all':
        query_cond = "WHERE status = ?"
        params.append(status)
        
    count_query = f"SELECT COUNT(*) FROM words {query_cond}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    sort_orders = {
        'score_desc': 'total_score DESC, id DESC',
        'score_asc': 'total_score ASC, id ASC',
        'alpha': 'word COLLATE NOCASE ASC',
        'date_added': 'date_added DESC, id DESC',
        'last_reviewed': 'last_reviewed DESC, id DESC'
    }
    order_clause = sort_orders.get(sort, 'total_score DESC, id DESC')
    
    limit = per_page
    offset = (page - 1) * per_page
    
    fetch_query = f"""
        SELECT id, word, phonetic, short_translation, status, total_score, review_count, last_reviewed, translation
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
        words_list.append({
            'id': row['id'],
            'word': row['word'],
            'phonetic': row['phonetic'],
            'short_translation': row['short_translation'],
            'translation': row['translation'],
            'status': row['status'],
            'total_score': row['total_score'],
            'review_count': row['review_count'],
            'last_reviewed': row['last_reviewed']
        })
        
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
        SELECT id, word, total_score, status, review_count 
        FROM words 
        ORDER BY total_score DESC, id DESC 
        LIMIT ?
    """, (n,))
    rows = cursor.fetchall()
    conn.close()
    
    top_words = []
    for r in rows:
        top_words.append({
            'id': r['id'],
            'word': r['word'],
            'total_score': r['total_score'],
            'status': r['status'],
            'review_count': r['review_count']
        })
        
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
            cursor.execute(f"UPDATE words SET status = 'learned' WHERE id IN ({placeholders})", word_ids)
        elif action == 'mark_learning':
            cursor.execute(f"UPDATE words SET status = 'learning' WHERE id IN ({placeholders})", word_ids)
        elif action == 'reset':
            cursor.execute(f"""
                UPDATE words
                SET status = 'new',
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

if __name__ == '__main__':
    # Initialize SQLite database and tables
    init_db()
    print("Database initialized successfully.")
    
    # Run the Flask app on port 5000 in debug mode
    app.run(port=5000, debug=True)
