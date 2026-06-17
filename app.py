from flask import Flask, render_template, request, jsonify
from database import (
    init_db, 
    get_stats, 
    get_words_by_status, 
    get_random_words, 
    update_word_after_review, 
    check_and_auto_upgrade,
    get_word_by_id,
    update_word_status
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
        
    try:
        success = update_word_after_review(
            word_id=int(word_id), 
            delta=int(delta), 
            mode=mode, 
            rating=rating, 
            is_correct=is_correct
        )
        
        if success:
            # Check for automatic status upgrades if rated 5
            upgraded = check_and_auto_upgrade(int(word_id))
            return jsonify({'status': 'success', 'upgraded': upgraded})
        else:
            return jsonify({'status': 'error', 'message': 'Word not found'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
        
    word_before = get_word_by_id(word_id)
    if not word_before:
        return jsonify({'success': False, 'message': 'Word not found'}), 404
        
    old_status = word_before['status']
    
    # Update score and reviews. delta = rating
    update_word_after_review(word_id, rating, 'flashcard', rating=rating)
    
    # Check for automatic status upgrades if rating is 5
    check_and_auto_upgrade(word_id)
    
    # Fetch post-update stats
    word_after = get_word_by_id(word_id)
    new_status = word_after['status']
    new_score = word_after['total_score']
    status_changed = (old_status != new_status)
    
    return jsonify({
        'success': True,
        'new_score': new_score,
        'new_status': new_status,
        'status_changed': status_changed,
        'message': 'Rating updated successfully'
    })

# API POST /api/word/mark-learned -> marks word as learned
@app.route('/api/word/mark-learned', methods=['POST'])
def api_mark_learned():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
    try:
        update_word_status(int(word_id), 'learned')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API POST /api/word/mark-learning -> marks word as learning
@app.route('/api/word/mark-learning', methods=['POST'])
def api_mark_learning():
    data = request.get_json() or {}
    word_id = data.get('word_id')
    if word_id is None:
        return jsonify({'success': False, 'message': 'Missing word_id'}), 400
    try:
        update_word_status(int(word_id), 'learning')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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
    
    for item in results:
        word_id = item.get('word_id')
        is_correct = item.get('is_correct')
        
        if word_id is None or is_correct is None:
            continue
            
        delta = 3 if is_correct else -2
        total_delta += delta
        
        try:
            update_word_after_review(
                word_id=int(word_id),
                delta=delta,
                mode='matching',
                is_correct=bool(is_correct)
            )
            
            word = get_word_by_id(word_id)
            if word:
                updated.append({
                    'word_id': int(word_id),
                    'delta': delta,
                    'new_score': word['total_score']
                })
        except Exception as e:
            print(f"Error updating word {word_id} in matching result: {e}")
            
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
        
    delta = 5 if is_correct else -3
    
    try:
        success = update_word_after_review(
            word_id=int(word_id),
            delta=delta,
            mode='fill',
            is_correct=bool(is_correct)
        )
        
        if success:
            word = get_word_by_id(word_id)
            new_score = word['total_score'] if word else 0
            return jsonify({
                'success': True,
                'new_score': new_score,
                'delta': delta
            })
        else:
            return jsonify({'success': False, 'message': 'Word not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    # Initialize SQLite database and tables
    init_db()
    print("Database initialized successfully.")
    
    # Run the Flask app on port 5000 in debug mode
    app.run(port=5000, debug=True)
