from flask import Flask, render_template, request, jsonify
from database import (
    init_db, 
    get_stats, 
    get_words_by_status, 
    get_random_words, 
    update_word_after_review, 
    check_and_auto_upgrade
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

if __name__ == '__main__':
    # Initialize SQLite database and tables
    init_db()
    print("Database initialized successfully.")
    
    # Run the Flask app on port 5000 in debug mode
    app.run(port=5000, debug=True)
