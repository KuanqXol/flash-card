// Flashcard Game State
const state = {
    currentWord: null,
    isFlipped: false,
    currentFilter: 'all',
    sessionCount: 0,
    sessionScore: 0,
    useUrlParams: true
};

// Session State
const sessionState = {
    seenIds: [],       // word_ids đã xem trong phiên này
    queue: [],         // queue từ /api/session/start
    currentIndex: 0,
};

// DOM Cache
const cardEl = document.getElementById('flashcard');
const wordEl = document.getElementById('card-word');
const phoneticEl = document.getElementById('card-phonetic');
const statusBadgeEl = document.getElementById('card-status-badge');
const translationEl = document.getElementById('card-translation');
const cardScoreEl = document.getElementById('card-score');
const cardReviewsEl = document.getElementById('card-reviews');
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
            startSession();
        });
    }

    // Keyboard bindings
    document.addEventListener('keydown', handleKeyDown);

    // Initial load
    startSession();
}

// Keyboard shortcuts
function handleKeyDown(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.code === 'Space') {
        e.preventDefault();
        flipCard();
    } else if (e.key >= '1' && e.key <= '5') {
        if (state.isFlipped && state.currentWord) {
            rateWord(parseInt(e.key));
        }
    } else if (e.key === 'Enter') {
        e.preventDefault();
        skipWord();
    }
}

// Khi load phiên mới:
async function startSession() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        let queue = [];
        
        if (state.currentFilter === 'recent_fails' || (state.useUrlParams && urlParams.get('mode') === 'recent_fails')) {
            state.useUrlParams = false; // only use once
            state.currentFilter = 'recent_fails';
            
            const res = await fetch('/api/words/recently-failed?hours=24');
            queue = await res.json();
            
            if (filterDropdownEl) {
                let opt = filterDropdownEl.querySelector('option[value="recent_fails"]');
                if (!opt) {
                    opt = document.createElement('option');
                    opt.value = 'recent_fails';
                    opt.textContent = '🔁 Từ vừa sai (24h)';
                    filterDropdownEl.appendChild(opt);
                }
                filterDropdownEl.value = 'recent_fails';
            }
        } else {
            let queryParams = `?status=${state.currentFilter}`;
            if (state.useUrlParams && window.location.search) {
                queryParams = window.location.search;
                state.useUrlParams = false; // only use once
            }
            const res = await fetch(`/api/session/start${queryParams}`);
            const data = await res.json();
            queue = data.queue || [];
        }
        
        sessionState.queue = queue;
        sessionState.currentIndex = 0;
        sessionState.seenIds = [];
        
        state.sessionCount = 0;
        state.sessionScore = 0;
        updateSessionUI();

        // Hide completion state and empty state
        const sessionCompleteEl = document.getElementById('flashcard-session-complete');
        if (sessionCompleteEl) sessionCompleteEl.style.display = 'none';
        
        const emptyStateEl = document.getElementById('flashcard-empty-state');
        if (emptyStateEl) emptyStateEl.style.display = 'none';

        if (sessionState.queue.length === 0) {
            state.currentWord = null;
            displayEmptyState();
            return;
        }

        const stageContainer = document.getElementById('flashcard-stage-container');
        if (stageContainer) stageContainer.style.display = 'block';
        
        showNextFromQueue();
    } catch (err) {
        console.error("Error starting session:", err);
        showToast("Lỗi khởi tạo phiên học!", "error");
    }
}

// Khi lấy từ tiếp theo:
function showNextFromQueue() {
    if (sessionState.currentIndex >= sessionState.queue.length) {
        showSessionComplete();
        return;
    }
    const word = sessionState.queue[sessionState.currentIndex++];
    sessionState.seenIds.push(word.id);
    renderCard(word);
}

function renderCard(word) {
    state.currentWord = word;
    state.isFlipped = false;
    if (cardEl) {
        cardEl.classList.remove('flipped');
    }
    
    // Hide rating and show flip controls
    if (ratingBarEl) ratingBarEl.classList.remove('visible');
    if (btnFlipEl) btnFlipEl.style.display = 'block';

    displayWord(word);
}

function skipWord() {
    showToast("⏭ Bỏ qua từ này", "info");
    showNextFromQueue();
}

function showSessionComplete() {
    state.currentWord = null;
    const stageContainer = document.getElementById('flashcard-stage-container');
    if (stageContainer) stageContainer.style.display = 'none';
    
    const emptyStateEl = document.getElementById('flashcard-empty-state');
    if (emptyStateEl) emptyStateEl.style.display = 'none';
    
    const sessionCompleteEl = document.getElementById('flashcard-session-complete');
    if (sessionCompleteEl) {
        sessionCompleteEl.style.display = 'flex';
        const countEl = document.getElementById('session-complete-count');
        const scoreEl = document.getElementById('session-complete-score');
        if (countEl) countEl.textContent = state.sessionCount;
        if (scoreEl) scoreEl.textContent = state.sessionScore;
    }
}

function displayEmptyState() {
    const stageContainer = document.getElementById('flashcard-stage-container');
    if (stageContainer) stageContainer.style.display = 'none';
    
    const emptyStateEl = document.getElementById('flashcard-empty-state');
    if (emptyStateEl) emptyStateEl.style.display = 'flex';
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
        statusBadgeEl.className = `badge badge-${word.status}`;
    }

    // Warning Badge styling
    const warningBadgeEl = document.getElementById('card-warning-badge');
    if (warningBadgeEl) {
        if (word.needs_review === 1) {
            warningBadgeEl.style.display = 'inline-block';
        } else {
            warningBadgeEl.style.display = 'none';
        }
    }

    // Back card content
    if (translationEl) {
        translationEl.innerHTML = renderPosEntries(word.pos_entries, word.translation || 'Không có nghĩa');
    }
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
                showNextFromQueue();
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
            showNextFromQueue();
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
            showNextFromQueue();
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

// Reset Star ratings
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

function renderPosEntries(posEntries, fullTranslation) {
  if (!posEntries || posEntries.length === 0) {
    return `<p class="meaning-full" style="font-size: 1.2rem; color: #5b21b6; font-weight: 600; line-height: 1.6; text-align: center; width: 100%;">${fullTranslation}</p>`;
  }
  const posLabels = { n: 'n.', v: 'v.', adj: 'adj.', adv: 'adv.', 
                      prep: 'prep.', conj: 'conj.', pron: 'pron.' };
  return posEntries.map(e => `
    <div class="pos-entry">
      ${e.pos ? `<span class="pos-badge">${posLabels[e.pos] || e.pos}</span>` : ''}
      <span class="meaning-text">${e.meaning}</span>
    </div>
  `).join('');
}
