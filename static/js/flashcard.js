// Toast Notification System
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Icon selection based on type
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-text">${message}</span>`;
    document.body.appendChild(toast);
    
    // Smooth transition trigger
    setTimeout(() => {
        toast.classList.add('visible');
    }, 10);
    
    // Auto removal
    setTimeout(() => {
        toast.classList.remove('visible');
        toast.classList.add('fade-out');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 2500);
}

// Flashcard Game State
const state = {
    currentWord: null,
    isFlipped: false,
    currentFilter: 'all',
    sessionCount: 0,
    sessionScore: 0
};

// DOM Cache
const cardEl = document.getElementById('flashcard');
const wordEl = document.getElementById('card-word');
const phoneticEl = document.getElementById('card-phonetic');
const statusBadgeEl = document.getElementById('card-status-badge');
const translationEl = document.getElementById('card-translation');
const cardScoreEl = document.getElementById('card-score');
const cardReviewsEl = document.getElementById('card-reviews');
const showMeaningHintEl = document.getElementById('show-meaning-hint');
const ratingBarEl = document.getElementById('rating-bar');
const btnFlipEl = document.getElementById('btn-flip');

const sessionCountEl = document.getElementById('session-count');
const sessionScoreEl = document.getElementById('session-score');
const filterDropdownEl = document.getElementById('filter-dropdown');

// Setup event listeners
function init() {
    // Dropdown change
    if (filterDropdownEl) {
        filterDropdownEl.addEventListener('change', (e) => {
            state.currentFilter = e.target.value;
            loadNextWord();
        });
    }

    // Keyboard bindings
    document.addEventListener('keydown', handleKeyDown);

    // Initial load
    loadNextWord();
}

// Keyboard shortcuts
function handleKeyDown(e) {
    if (e.code === 'Space') {
        e.preventDefault();
        flipCard();
    } else if (e.key >= '1' && e.key <= '5') {
        if (state.isFlipped && state.currentWord) {
            rateWord(parseInt(e.key));
        }
    } else if (e.key === 'Enter') {
        e.preventDefault();
        // Skip current word without score changes
        showToast("⏭ Bỏ qua từ này", "info");
        loadNextWord();
    }
}

// Fetch next word
async function loadNextWord() {
    try {
        state.isFlipped = false;
        if (cardEl) {
            cardEl.classList.remove('flipped');
        }
        
        // Hide rating and show flip controls
        if (ratingBarEl) ratingBarEl.classList.remove('visible');
        if (btnFlipEl) btnFlipEl.style.display = 'block';

        const excludeId = state.currentWord ? state.currentWord.id : '';
        const url = `/api/flashcard/next?status=${state.currentFilter}&exclude_id=${excludeId}`;
        
        const response = await fetch(url);
        const data = await response.json();

        if (data.error === 'no_words') {
            state.currentWord = null;
            displayEmptyState();
            return;
        }

        state.currentWord = data;
        displayWord(data);
    } catch (err) {
        console.error("Error loading next word:", err);
        showToast("Lỗi tải từ vựng!", "error");
    }
}

function displayEmptyState() {
    if (wordEl) wordEl.textContent = "Hết từ vựng";
    if (phoneticEl) phoneticEl.style.display = 'none';
    if (statusBadgeEl) {
        statusBadgeEl.textContent = "Trống";
        statusBadgeEl.className = "status-badge badge-empty";
    }
    if (translationEl) translationEl.textContent = "Không có từ vựng nào khớp với bộ lọc đã chọn.";
    if (cardScoreEl) cardScoreEl.textContent = "Điểm: 0 ⭐";
    if (cardReviewsEl) cardReviewsEl.textContent = "Đã ôn: 0 lần";
    if (btnFlipEl) btnFlipEl.style.display = 'none';
    if (ratingBarEl) ratingBarEl.classList.remove('visible');
}

function displayWord(word) {
    if (wordEl) wordEl.textContent = word.word;
    
    // Phonetic handling: hide if "--", null, or empty
    if (phoneticEl) {
        if (word.phonetic && word.phonetic !== '--' && word.phonetic.trim() !== '') {
            phoneticEl.textContent = word.phonetic;
            phoneticEl.style.display = 'block';
        } else {
            phoneticEl.style.display = 'none';
        }
    }

    // Status Badge styling
    if (statusBadgeEl) {
        statusBadgeEl.textContent = getStatusText(word.status);
        statusBadgeEl.className = `status-badge badge-${word.status}`;
    }

    // Back card content
    if (translationEl) translationEl.textContent = word.translation || 'Không có nghĩa';
    if (cardScoreEl) cardScoreEl.textContent = `Điểm: ${word.total_score || 0} ⭐`;
    if (cardReviewsEl) cardReviewsEl.textContent = `Đã ôn: ${word.review_count || 0} lần`;
}

function getStatusText(status) {
    switch (status) {
        case 'new': return 'Từ mới';
        case 'learning': return 'Đang học';
        case 'learned': return 'Đã thuộc';
        default: return status;
    }
}

// Flip logic
function flipCard() {
    if (!state.currentWord) return;
    
    state.isFlipped = !state.isFlipped;
    
    if (cardEl) {
        cardEl.classList.toggle('flipped', state.isFlipped);
    }
    
    if (state.isFlipped) {
        if (btnFlipEl) btnFlipEl.style.display = 'none';
        if (ratingBarEl) ratingBarEl.classList.add('visible');
        resetStars();
    } else {
        if (btnFlipEl) btnFlipEl.style.display = 'block';
        if (ratingBarEl) ratingBarEl.classList.remove('visible');
    }
}

// Rate logic
async function rateWord(rating) {
    if (!state.currentWord) return;

    try {
        const response = await fetch('/api/flashcard/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word_id: state.currentWord.id,
                rating: rating
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.status_changed) {
                showToast("🎉 Chuyển sang Đang học!", "success");
            }
            showToast(`+${rating} điểm`, "success");
            
            // Update Session count and score
            state.sessionScore += rating;
            state.sessionCount++;
            
            updateSessionUI();
            
            // Highlight chosen star and load next word after 800ms
            highlightChosenStar(rating);
            
            setTimeout(() => {
                loadNextWord();
            }, 800);
        } else {
            showToast(data.message || "Lỗi đánh giá!", "error");
        }
    } catch (err) {
        console.error("Error rating word:", err);
        showToast("Lỗi gửi đánh giá!", "error");
    }
}

// Mark Learned logic
async function markLearned() {
    if (!state.currentWord) return;
    
    try {
        const response = await fetch('/api/word/mark-learned', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: state.currentWord.id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast("✅ Đã thuộc!", "success");
            loadNextWord();
        } else {
            showToast("Không thể cập nhật trạng thái!", "error");
        }
    } catch (err) {
        console.error("Error marking learned:", err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// Mark Learning logic
async function markLearning() {
    if (!state.currentWord) return;
    
    try {
        const response = await fetch('/api/word/mark-learning', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: state.currentWord.id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast("Chuyển sang Đang học!", "info");
            loadNextWord();
        } else {
            showToast("Không thể cập nhật trạng thái!", "error");
        }
    } catch (err) {
        console.error("Error marking learning:", err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

function updateSessionUI() {
    if (sessionCountEl) sessionCountEl.textContent = state.sessionCount;
    if (sessionScoreEl) sessionScoreEl.textContent = state.sessionScore;
}

// Star rating UI updates
function highlightChosenStar(rating) {
    const stars = document.querySelectorAll('.star-rating svg');
    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.add('selected');
        } else {
            star.classList.remove('selected');
        }
    });
}

function resetStars() {
    const stars = document.querySelectorAll('.star-rating svg');
    stars.forEach(star => {
        star.classList.remove('selected');
    });
}

// Bind direct hover/click handlers to star SVG items
document.addEventListener('DOMContentLoaded', () => {
    const stars = document.querySelectorAll('.star-rating svg');
    stars.forEach(star => {
        star.addEventListener('mouseenter', function() {
            if (!state.isFlipped) return;
            const val = parseInt(this.dataset.val);
            stars.forEach((s, idx) => {
                if (idx < val) s.classList.add('hover');
                else s.classList.remove('hover');
            });
        });
        
        star.addEventListener('mouseleave', function() {
            stars.forEach(s => s.classList.remove('hover'));
        });
        
        star.addEventListener('click', function(e) {
            e.stopPropagation(); // prevent flipping back
            if (!state.isFlipped) return;
            const val = parseInt(this.dataset.val);
            rateWord(val);
        });
    });

    init();
});
