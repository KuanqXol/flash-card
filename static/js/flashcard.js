// Flashcard Game State
const session = {
    queue: [],
    index: 0,
    filter: 'smart_priority',
    status: 'all',
    sessionScore: 0,
    sessionCorrect: 0,
    sessionWrong: 0,
    startedAt: null,
    currentWord: null,
    isFlipped: false
};

// DOM Cache (mutable since innerHTML gets replaced on restarts)
let cardEl = null;
let wordEl = null;
let phoneticEl = null;
let statusBadgeEl = null;
let translationEl = null;
let cardScoreEl = null;
let cardReviewsEl = null;
let ratingBarEl = null;
let btnFlipEl = null;

const progressTextEl = document.getElementById('progress-text');
const progressFillEl = document.getElementById('progress-fill');

function initDOMCache() {
    cardEl = document.getElementById('flashcard');
    wordEl = document.getElementById('card-word');
    phoneticEl = document.getElementById('card-phonetic');
    statusBadgeEl = document.getElementById('card-status-badge');
    translationEl = document.getElementById('card-translation');
    cardScoreEl = document.getElementById('card-score');
    cardReviewsEl = document.getElementById('card-reviews');
    ratingBarEl = document.getElementById('rating-bar');
    btnFlipEl = document.getElementById('btn-flip');
    
    setupStars();
}

// Setup event listeners
async function init() {
    // Store original container HTML to restore on session restarts
    window.originalCardContainerHTML = document.getElementById('card-container').innerHTML;

    // Keyboard bindings
    document.addEventListener('keydown', handleKeyDown);

    // Initial load and setup of headers
    await initStudyHeaderFilters(async (filter, status) => {
        session.filter = filter;
        session.status = status;
        await startSession();
    });
}

// Keyboard shortcuts
function handleKeyDown(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.code === 'Space') {
        e.preventDefault();
        flipCard();
    } else if (e.key === '1') {
        if (session.isFlipped && session.currentWord) {
            rateWord(false);
        }
    } else if (e.key === '2') {
        if (session.isFlipped && session.currentWord) {
            rateWord(true);
        }
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (session.isFlipped) {
            rateWord(true);
        } else {
            flipCard();
        }
    }
}

// Khởi tạo session mới
async function startSession() {
    // Restore stage container HTML
    document.getElementById('card-container').innerHTML = window.originalCardContainerHTML;
    initDOMCache();

    // Hide empty state
    document.getElementById('flashcard-empty-state').style.display = 'none';

    try {
        const res = await fetch(`/api/session/queue?filter=${session.filter}&status=${session.status}&n=20`);
        const data = await res.json();
        
        if (!data.queue || data.queue.length === 0) {
            document.getElementById('flashcard-empty-state').style.display = 'flex';
            document.getElementById('empty-state-text').textContent = `Không có từ nào phù hợp với bộ lọc "${data.filter_label}"`;
            document.getElementById('card-container').innerHTML = ''; // Clear container
            updateProgressText("0 / 0");
            updateProgressFill(0);
            return;
        }
        
        session.queue = data.queue;
        session.index = 0;
        session.sessionScore = 0;
        session.sessionCorrect = 0;
        session.sessionWrong = 0;
        session.startedAt = Date.now();
        
        // Show summary info
        const infoEl = document.getElementById('session-summary-info');
        if (infoEl) {
            infoEl.textContent = data.summary || `Phiên học: ${session.queue.length} từ`;
        }
        
        showCard(session.queue[0]);
        updateProgressUI();
    } catch (err) {
        console.error("Error starting session:", err);
        showToast("Lỗi khởi tạo phiên học!", "error");
    }
}

function showCard(word) {
    session.currentWord = word;
    session.isFlipped = false;
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
    nextWord();
}

function nextWord() {
    session.index++;
    updateProgressUI();
    if (session.index >= session.queue.length) {
        showSessionComplete();
        return;
    }
    showCard(session.queue[session.index]);
}

function showSessionComplete() {
    session.currentWord = null;
    const duration = Math.max(1, Math.round((Date.now() - session.startedAt) / 1000 / 60));
    
    document.getElementById('card-container').innerHTML = `
        <div class="session-complete">
          <div class="complete-icon">🎉</div>
          <h2>Hoàn thành phiên học!</h2>
          <div class="complete-stats">
            <div class="stat">
              <span class="stat-number">${session.queue.length}</span>
              <span class="stat-label">Từ đã ôn</span>
            </div>
            <div class="stat">
              <span class="stat-number">+${session.sessionScore}</span>
              <span class="stat-label">Điểm</span>
            </div>
            <div class="stat">
              <span class="stat-number">${duration} phút</span>
              <span class="stat-label">Thời gian</span>
            </div>
          </div>
          <div class="complete-actions">
            <button class="btn btn-primary" onclick="startSession()">Bắt đầu lại</button>
            <a href="/" class="btn btn-ghost">Về Dashboard</a>
          </div>
        </div>
    `;
    
    // Confetti animation
    if (typeof confetti !== 'undefined') {
        confetti({ particleCount: 80, spread: 60, origin: { y: 0.6 } });
    }
}

function updateProgressUI() {
    const textVal = `${session.index} / ${session.queue.length}`;
    updateProgressText(textVal);
    
    if (session.queue.length > 0) {
        const percent = Math.min(100, Math.round((session.index / session.queue.length) * 100));
        updateProgressFill(percent);
    }
}

function updateProgressText(text) {
    if (progressTextEl) progressTextEl.textContent = text;
}

function updateProgressFill(percent) {
    if (progressFillEl) progressFillEl.style.width = `${percent}%`;
}

function displayWord(word) {
    session.hasLoggedFlip = false;
    if (wordEl) wordEl.textContent = word.word;
    
    // Set data-word attributes for TTS
    const cardContainer = document.getElementById('flashcard');
    if (cardContainer) cardContainer.setAttribute('data-word', word.word);
    
    const btnTts = document.getElementById('card-btn-tts');
    const btnTtsSlow = document.getElementById('card-btn-tts-slow');
    if (btnTts) btnTts.setAttribute('data-word', word.word);
    if (btnTtsSlow) btnTtsSlow.setAttribute('data-word', word.word);
    
    // Autoplay pronunciation after 300ms
    setTimeout(() => {
        if (session.currentWord && session.currentWord.word === word.word) {
            playWord(word.word, 'normal');
        }
    }, 300);
    
    // Phonetic handling
    if (phoneticEl) {
        if (word.phonetic && word.phonetic !== '--' && word.phonetic.trim() !== '') {
            phoneticEl.textContent = word.phonetic;
            phoneticEl.style.display = 'block';
        } else {
            phoneticEl.style.display = 'none';
        }
    }

    // Status Badge
    if (statusBadgeEl) {
        statusBadgeEl.textContent = getStatusText(word.status);
        statusBadgeEl.className = `badge badge-${word.status}`;
    }

    // Warning Badge
    const warningBadgeEl = document.getElementById('card-warning-badge');
    if (warningBadgeEl) {
        warningBadgeEl.style.display = word.needs_review === 1 ? 'inline-block' : 'none';
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
    if (!session.currentWord) return;
    
    session.isFlipped = !session.isFlipped;
    
    if (cardEl) {
        cardEl.classList.toggle('flipped', session.isFlipped);
    }
    
    if (session.isFlipped) {
        if (btnFlipEl) btnFlipEl.style.display = 'none';
        if (ratingBarEl) ratingBarEl.classList.add('visible');
        
        // Log flip event to increment seen count (only once per card view)
        if (!session.hasLoggedFlip) {
            session.hasLoggedFlip = true;
            fetch('/api/flashcard/flip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ word_id: session.currentWord.id })
            }).catch(err => console.error("Error logging flip:", err));
        }
    } else {
        if (btnFlipEl) btnFlipEl.style.display = 'block';
        if (ratingBarEl) ratingBarEl.classList.remove('visible');
    }
}

// Rate logic
async function rateWord(isCorrect) {
    if (!session.currentWord) return;

    try {
        const response = await fetch('/api/flashcard/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word_id: session.currentWord.id,
                is_correct: isCorrect
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (isCorrect) {
                showToast(`+1 điểm`, "success");
                session.sessionScore += 1;
            } else {
                showToast(`Ghi nhận đã xem`, "info");
            }
            
            setTimeout(() => {
                nextWord();
            }, 600);
        } else {
            showToast(data.message || "Lỗi đánh giá!", "error");
        }
    } catch (err) {
        console.error("Error rating word:", err);
        showToast("Lỗi gửi đánh giá!", "error");
    }
}

// Mark Learned logic
async function markLearned(event) {
    if (event) event.stopPropagation();
    if (!session.currentWord) return;
    
    try {
        const response = await fetch('/api/word/mark-learned', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: session.currentWord.id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast("✅ Đã thuộc!", "success");
            nextWord();
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
    if (!session.currentWord) return;
    
    try {
        const response = await fetch('/api/word/mark-learning', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: session.currentWord.id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast("Chuyển sang Đang học!", "info");
            nextWord();
        } else {
            showToast("Không thể cập nhật trạng thái!", "error");
        }
    } catch (err) {
        console.error("Error marking learning:", err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
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

function setupStars() {
    const stars = document.querySelectorAll('.star-rating svg');
    stars.forEach(star => {
        star.addEventListener('mouseenter', function() {
            if (!session.isFlipped) return;
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
            e.stopPropagation();
            if (!session.isFlipped) return;
            const val = parseInt(this.dataset.val);
            rateWord(val);
        });
    });
}

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

// Bind load hooks
document.addEventListener('DOMContentLoaded', () => {
    init();
});
