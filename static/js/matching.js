// Fisher-Yates Shuffle Algorithm
function shuffle(array) {
    let currentIndex = array.length, randomIndex;
    const newArray = [...array];
    
    while (currentIndex !== 0) {
        randomIndex = Math.floor(Math.random() * currentIndex);
        currentIndex--;
        [newArray[currentIndex], newArray[randomIndex]] = [
            newArray[randomIndex], newArray[currentIndex]
        ];
    }
    return newArray;
}

// Matching Game State
const session = {
    matchingPool: [],    // All words from queue
    round: 1,            // Current round (1 to totalRounds)
    roundSize: 6,
    totalRounds: 3,
    words: [],           // Words in current round
    viList: [],          // Shuffled meanings for current round
    selectedEn: null,    // id
    selectedVi: null,    // id
    matched: new Set(),  // set of correct word_ids in current round
    failedWords: new Set(), // set of word_ids mismatched in current round
    results: [],         // results of current round
    finalResults: {},    // {word_id: is_correct}
    sessionScore: 0,
    startedAt: null,
    filter: 'smart_priority',
    status: 'all',
    sessionSubmitted: false
};

let gridLocked = false;

// DOM Cache
let enColumnEl = null;
let viColumnEl = null;
let progressTextEl = null;
let progressFillEl = null;
let btnSubmitEl = null;
let roundIndicatorEl = null;

// Modal Elements
const modalEl = document.getElementById('result-modal');
const modalPointsEl = document.getElementById('modal-points');
const modalRatioEl = document.getElementById('modal-ratio');
const modalTableBodyEl = document.getElementById('modal-table-body');
const modalFooterEl = document.querySelector('#result-modal .modal div:last-child'); // action buttons container

function initDOMCache() {
    enColumnEl = document.getElementById('en-column');
    viColumnEl = document.getElementById('vi-column');
    progressTextEl = document.getElementById('progress-text');
    progressFillEl = document.getElementById('progress-fill');
    btnSubmitEl = document.getElementById('btn-submit');
    roundIndicatorEl = document.getElementById('round-indicator');
    
    // Submit btn
    if (btnSubmitEl) {
        // Remove existing listener if any, recreate
        const newBtn = btnSubmitEl.cloneNode(true);
        btnSubmitEl.parentNode.replaceChild(newBtn, btnSubmitEl);
        btnSubmitEl = newBtn;
        btnSubmitEl.addEventListener('click', () => {
            if (session.matched.size === 0) {
                showToast("Bạn chưa ghép cặp nào!", "error");
                return;
            }
            submitResults();
        });
    }
}

// Setup Game
async function init() {
    // Store original container HTML to restore on session restarts
    window.originalCardContainerHTML = document.getElementById('card-container').innerHTML;
    
    // Initial load and setup of headers
    await initStudyHeaderFilters(async (filter, status) => {
        session.filter = filter;
        session.status = status;
        await startSession();
    });
}

// Khởi tạo session mới
async function startSession() {
    // Restore stage container HTML
    document.getElementById('card-container').innerHTML = window.originalCardContainerHTML;
    initDOMCache();
    closeModal();

    // Hide empty state
    document.getElementById('matching-empty-state').style.display = 'none';

    try {
        const res = await fetch(`/api/session/queue?filter=${session.filter}&status=${session.status}&n=18`);
        const data = await res.json();
        
        if (!data.queue || data.queue.length === 0) {
            document.getElementById('matching-empty-state').style.display = 'flex';
            document.getElementById('empty-state-text').textContent = `Không có từ nào phù hợp với bộ lọc "${data.filter_label}"`;
            document.getElementById('card-container').innerHTML = ''; // Clear container
            updateProgressUI(0, 0);
            return;
        }
        
        // Dynamically compute round parameters
        const pool = data.queue;
        if (pool.length >= 18) {
            session.roundSize = 6;
            session.totalRounds = 3;
            session.matchingPool = pool.slice(0, 18);
        } else if (pool.length >= 12) {
            session.roundSize = 6;
            session.totalRounds = 2;
            session.matchingPool = pool.slice(0, 12);
        } else if (pool.length >= 6) {
            session.roundSize = 6;
            session.totalRounds = 1;
            session.matchingPool = pool.slice(0, 6);
        } else if (pool.length >= 4) {
            session.roundSize = pool.length;
            session.totalRounds = 1;
            session.matchingPool = pool;
        } else {
            // Less than 4 words, show empty state
            document.getElementById('matching-empty-state').style.display = 'flex';
            document.getElementById('empty-state-text').textContent = `Không đủ từ vựng để chơi! Cần tối thiểu 4 từ.`;
            document.getElementById('card-container').innerHTML = '';
            updateProgressUI(0, 0);
            return;
        }
        
        session.round = 1;
        session.sessionScore = 0;
        session.finalResults = {};
        session.startedAt = Date.now();
        
        // Show summary info
        const infoEl = document.getElementById('session-summary-info');
        if (infoEl) {
            infoEl.textContent = data.summary || `Phiên học: ${session.matchingPool.length} từ`;
        }
        
        startRound();
    } catch (err) {
        console.error("Error starting session:", err);
        showToast("Lỗi khởi tạo phiên học!", "error");
    }
}

function startRound() {
    const startIdx = (session.round - 1) * session.roundSize;
    session.words = session.matchingPool.slice(startIdx, startIdx + session.roundSize);
    session.viList = shuffle(session.words.map(w => ({ id: w.id, text: w.short_translation })));
    session.selectedEn = null;
    session.selectedVi = null;
    session.matched.clear();
    session.failedWords.clear();
    session.results = [];
    session.sessionSubmitted = false;
    gridLocked = false;
    
    if (btnSubmitEl) btnSubmitEl.disabled = true;
    if (roundIndicatorEl) {
        roundIndicatorEl.textContent = `Vòng ${session.round} / ${session.totalRounds}`;
    }
    
    updateRoundProgressUI();
    renderColumns();
}

function updateRoundProgressUI() {
    const matchedTotal = (session.round - 1) * session.roundSize + session.matched.size;
    updateProgressUI(matchedTotal, session.matchingPool.length);
}

function updateProgressUI(matchedCount, totalCount) {
    if (progressTextEl) {
        progressTextEl.textContent = `${matchedCount} / ${totalCount}`;
    }
    if (progressFillEl && totalCount > 0) {
        const percent = Math.min(100, Math.round((matchedCount / totalCount) * 100));
        progressFillEl.style.width = `${percent}%`;
    }
}

function renderColumns() {
    if (!enColumnEl || !viColumnEl) return;
    
    // Render English items
    enColumnEl.innerHTML = '';
    session.words.forEach(w => {
        const card = document.createElement('div');
        card.className = 'match-card';
        card.dataset.id = w.id;
        card.dataset.type = 'en';
        card.setAttribute('data-word', w.word);
        card.innerHTML = `
            <span style="flex-grow: 1;">${w.word}</span>
            <button class="btn-tts" data-word="${w.word}" onclick="event.stopPropagation(); playWord('${w.word.replace(/'/g, "\\'")}', 'normal')" style="margin-left: 8px;" aria-label="Nghe phát âm">
                <i class="ph ph-speaker-high"></i>
            </button>
        `;
        card.addEventListener('click', handleEnClick);
        enColumnEl.appendChild(card);
    });
    
    // Render Shuffled Vietnamese items
    viColumnEl.innerHTML = '';
    session.viList.forEach(vi => {
        const card = document.createElement('div');
        card.className = 'match-card';
        card.dataset.id = vi.id;
        card.dataset.type = 'vi';
        card.textContent = vi.text;
        card.addEventListener('click', handleViClick);
        viColumnEl.appendChild(card);
    });
}

// Selection handlers
function handleEnClick() {
    if (gridLocked || session.matched.has(parseInt(this.dataset.id))) return;
    
    const id = parseInt(this.dataset.id);
    session.selectedEn = id;
    
    // Highlight
    document.querySelectorAll('#en-column .match-card').forEach(c => c.classList.remove('selected'));
    this.classList.add('selected');
    
    tryMatch();
}

function handleViClick() {
    if (gridLocked || session.matched.has(parseInt(this.dataset.id))) return;
    
    const id = parseInt(this.dataset.id);
    session.selectedVi = id;
    
    // Highlight
    document.querySelectorAll('#vi-column .match-card').forEach(c => c.classList.remove('selected'));
    this.classList.add('selected');
    
    tryMatch();
}

// Match evaluation
function tryMatch() {
    if (session.selectedEn === null || session.selectedVi === null) return;
    
    const enCard = document.querySelector(`#en-column .match-card[data-id="${session.selectedEn}"]`);
    const viCard = document.querySelector(`#vi-column .match-card[data-id="${session.selectedVi}"]`);
    
    if (session.selectedEn === session.selectedVi) {
        // MATCH CORRECT
        const wordId = session.selectedEn;
        session.matched.add(wordId);
        
        // Push result: check if ever failed in this round
        const isCorrectFirstTry = !session.failedWords.has(wordId);
        recordMatch(wordId, isCorrectFirstTry);
        
        enCard.classList.remove('selected');
        viCard.classList.remove('selected');
        enCard.classList.add('correct');
        viCard.classList.add('correct');
        
        if (btnSubmitEl) btnSubmitEl.disabled = false;
        
        resetSelections();
        updateRoundProgressUI();
        
        // Auto submit when complete
        if (session.matched.size === session.words.length) {
            setTimeout(() => {
                submitResults();
            }, 600);
        }
        
    } else {
        // MATCH INCORRECT
        const enId = session.selectedEn;
        const viId = session.selectedVi;
        
        // Mark both IDs as mismatched in current session round
        session.failedWords.add(enId);
        session.failedWords.add(viId);
        recordMatch(enId, false);
        recordMatch(viId, false);
        
        enCard.classList.remove('selected');
        viCard.classList.remove('selected');
        enCard.classList.add('wrong', 'shake');
        viCard.classList.add('wrong', 'shake');
        
        gridLocked = true;
        
        setTimeout(() => {
            enCard.classList.remove('wrong', 'shake');
            viCard.classList.remove('wrong', 'shake');
            gridLocked = false;
        }, 600);
        
        resetSelections();
    }
}

function recordMatch(wordId, isCorrect) {
    session.finalResults[wordId] = isCorrect;  // overwrite → chỉ giữ kết quả cuối
}

function resetSelections() {
    session.selectedEn = null;
    session.selectedVi = null;
}

// Submit Results to API
async function submitResults() {
    if (session.sessionSubmitted) return;
    session.sessionSubmitted = true;
    
    // Ensure all remaining unmatched words are pushed as incorrect in results
    session.words.forEach(w => {
        if (session.finalResults[w.id] === undefined) {
            session.finalResults[w.id] = false;
        }
    });

    const roundResultsList = session.words.map(w => ({
        word_id: w.id,
        is_correct: session.finalResults[w.id]
    }));

    try {
        const response = await fetch('/api/matching/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ results: roundResultsList })
        });
        
        const data = await response.json();
        session.results = roundResultsList;
        session.sessionScore += data.total_delta;
        showResultModal(data);
        
    } catch (err) {
        console.error("Error submitting results:", err);
        showToast("Lỗi đồng bộ kết quả game!", "error");
        session.sessionSubmitted = false;
    }
}

// Results Modal Rendering
function showResultModal(response) {
    if (!modalEl) return;
    
    // Set Points text
    const delta = response.total_delta;
    if (delta >= 0) {
        modalPointsEl.textContent = `+${delta} điểm`;
        modalPointsEl.style.color = '#10b981'; // Green
    } else {
        modalPointsEl.textContent = `${delta} điểm`;
        modalPointsEl.style.color = '#f43f5e'; // Red
    }
    
    // Match ratio
    const correctCount = session.results.filter(r => r.is_correct).length;
    modalRatioEl.textContent = `Đúng: ${correctCount} / ${session.words.length} cặp`;
    
    // Render details table
    if (modalTableBodyEl) {
        modalTableBodyEl.innerHTML = '';
        session.words.forEach(w => {
            const row = document.createElement('tr');
            
            // Check result mapping
            const isCorrect = session.results.find(r => r.word_id === w.id)?.is_correct;
            const resultIcon = isCorrect ? '<span style="color:#10b981; font-weight:700;">✓</span>' : '<span style="color:#f43f5e; font-weight:700;">✗</span>';
            
            row.innerHTML = `
                <td>${w.word}</td>
                <td>${w.short_translation}</td>
                <td style="text-align:center;">${resultIcon}</td>
            `;
            modalTableBodyEl.appendChild(row);
        });
    }
    
    // Render action buttons
    if (modalFooterEl) {
        if (session.round < session.totalRounds) {
            modalFooterEl.innerHTML = `
                <button class="btn btn-ghost" onclick="closeModal(); returnToDashboard();" style="margin-right: auto;">Về Dashboard</button>
                <button class="btn btn-primary" onclick="closeModal(); nextRound();">Vòng tiếp theo (${session.round + 1}/${session.totalRounds}) ➔</button>
            `;
        } else {
            modalFooterEl.innerHTML = `
                <button class="btn btn-ghost" onclick="closeModal(); returnToDashboard();" style="margin-right: auto;">Về Dashboard</button>
                <button class="btn btn-primary" onclick="closeModal(); finishSession();">Xem tổng kết ➔</button>
            `;
        }
    }
    
    // Display Modal
    modalEl.style.display = 'flex';
}

function closeModal() {
    if (modalEl) modalEl.style.display = 'none';
}

function returnToDashboard() {
    window.location.href = '/';
}

function nextRound() {
    session.round++;
    startRound();
}

function finishSession() {
    showSessionComplete();
}

function showSessionComplete() {
    const duration = Math.max(1, Math.round((Date.now() - session.startedAt) / 1000 / 60));
    
    document.getElementById('card-container').innerHTML = `
        <div class="session-complete">
          <div class="complete-icon">🎉</div>
          <h2>Hoàn thành phiên học!</h2>
          <div class="complete-stats">
            <div class="stat">
              <span class="stat-number">${session.matchingPool.length}</span>
              <span class="stat-label">Từ đã ôn</span>
            </div>
            <div class="stat">
              <span class="stat-number">${session.sessionScore >= 0 ? '+' : ''}${session.sessionScore}</span>
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

// Start Game on Page Ready
document.addEventListener('DOMContentLoaded', () => {
    init();
});
