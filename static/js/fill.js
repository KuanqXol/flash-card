// Điền Nghĩa Game State
let state = {
    currentWord: null,
    mode: 'en_to_vi', // 'en_to_vi' or 'vi_to_en'
    filter: 'all',
    phase: 'input', // 'input' or 'evaluate'
    sessionCount: 0,
    sessionScore: 0
};

let actionLocked = false;

// DOM Cache
const flagEl = document.getElementById('question-flag');
const promptEl = document.getElementById('question-prompt');
const hintLabelEl = document.getElementById('question-hint-label');
const phoneticEl = document.getElementById('question-phonetic');
const statusBadgeEl = document.getElementById('card-status-badge');
const wordScoreEl = document.getElementById('card-score');

const answerInputEl = document.getElementById('answer-input');
const btnActionEl = document.getElementById('btn-action');
const answerBoxEl = document.getElementById('answer-box');
const shortAnsEl = document.getElementById('short-answer');
const fullAnsEl = document.getElementById('full-answer');

const sessionCountEl = document.getElementById('session-count');
const sessionScoreEl = document.getElementById('session-score');
const filterDropdownEl = document.getElementById('filter-dropdown');
const toggleModeBtnEl = document.getElementById('btn-toggle-mode');

// Init game
function initGame() {
    // Dropdown and mode toggle
    if (filterDropdownEl) {
        filterDropdownEl.addEventListener('change', (e) => {
            state.filter = e.target.value;
            loadNext();
        });
    }

    if (toggleModeBtnEl) {
        toggleModeBtnEl.addEventListener('click', toggleMode);
    }

    // Bind check button
    if (btnActionEl) {
        btnActionEl.addEventListener('click', () => {
            if (state.phase === 'input') {
                submitAnswer();
            }
        });
    }

    // Keyboard bindings
    document.addEventListener('keydown', handleKeyDown);

    loadNext();
}

function toggleMode() {
    state.mode = state.mode === 'en_to_vi' ? 'vi_to_en' : 'en_to_vi';
    
    // Update button text
    if (toggleModeBtnEl) {
        toggleModeBtnEl.textContent = state.mode === 'en_to_vi' ? '🇬🇧 EN → 🇻🇳 VI' : '🇻🇳 VI → 🇬🇧 EN';
    }
    
    loadNext();
}

function handleKeyDown(e) {
    if (e.key === 'Enter') {
        if (state.phase === 'input') {
            e.preventDefault();
            submitAnswer();
        }
        // If phase is evaluate, Enter does nothing to prevent accidental rating clicks
    } else if (state.phase === 'evaluate' && !actionLocked) {
        if (e.key.toLowerCase() === 'y' || e.key === 'ArrowUp') {
            e.preventDefault();
            evaluate(true);
        } else if (e.key.toLowerCase() === 'n' || e.key === 'ArrowDown') {
            e.preventDefault();
            evaluate(false);
        }
    }
}

// Fetch Next Word
async function loadNext() {
    try {
        state.phase = 'input';
        actionLocked = false;
        
        // Hide answer box
        if (answerBoxEl) answerBoxEl.style.display = 'none';
        
        // Reset inputs
        if (answerInputEl) {
            answerInputEl.value = '';
            answerInputEl.disabled = false;
            answerInputEl.placeholder = state.mode === 'en_to_vi' ? 'Nhập nghĩa tiếng Việt...' : 'Type English spelling here...';
            answerInputEl.focus();
        }
        
        if (btnActionEl) {
            btnActionEl.style.display = 'inline-block';
            btnActionEl.textContent = 'Kiểm tra →';
        }

        const excludeId = state.currentWord ? state.currentWord.id : '';
        const url = `/api/fill/next?status=${state.filter}&mode=${state.mode}&exclude_id=${excludeId}`;
        
        const response = await fetch(url);
        const data = await response.json();

        if (data.error === 'no_words') {
            state.currentWord = null;
            displayEmptyState();
            return;
        }

        // Hide empty state, show game container
        document.getElementById('fill-empty-state').style.display = 'none';
        document.getElementById('fill-stage-container').style.display = 'block';

        state.currentWord = data;
        displayWord(data);
    } catch (err) {
        console.error("Error loading next spelling card:", err);
        showToast("Lỗi tải từ vựng!", "error");
    }
}

function displayEmptyState() {
    document.getElementById('fill-stage-container').style.display = 'none';
    document.getElementById('fill-empty-state').style.display = 'flex';
}

function displayWord(word) {
    // Badges and stats
    if (statusBadgeEl) {
        statusBadgeEl.textContent = getStatusText(word.status);
        statusBadgeEl.className = `status-badge badge-${word.status}`;
    }
    if (wordScoreEl) {
        wordScoreEl.textContent = `Điểm: ${word.total_score || 0} ⭐`;
    }

    // Display based on game mode
    if (state.mode === 'en_to_vi') {
        // EN -> VI
        if (flagEl) flagEl.textContent = '🇬🇧';
        if (promptEl) promptEl.textContent = word.word;
        if (hintLabelEl) hintLabelEl.textContent = 'Nghĩa tiếng Việt là gì?';
        
        if (phoneticEl) {
            if (word.phonetic && word.phonetic !== '--' && word.phonetic.trim() !== '') {
                phoneticEl.textContent = word.phonetic;
                phoneticEl.style.display = 'block';
            } else {
                phoneticEl.style.display = 'none';
            }
        }
    } else {
        // VI -> EN
        if (flagEl) flagEl.textContent = '🇻🇳';
        // Use short translation as prompt. If empty, use translation[:30]
        let promptText = word.short_translation;
        if (!promptText || promptText.trim() === '') {
            promptText = (word.translation || '').substring(0, 30);
        }
        if (promptEl) promptEl.textContent = promptText;
        if (hintLabelEl) hintLabelEl.textContent = 'Từ tiếng Anh là gì?';
        if (phoneticEl) phoneticEl.style.display = 'none'; // Hide phonetic to not give away English spelling
    }
}

function getStatusText(status) {
    switch (status) {
        case 'new': return 'Từ mới';
        case 'learning': return 'Đang học';
        case 'learned': return 'Đã thuộc';
        default: return status;
    }
}

// Submit answer to show evaluations
function submitAnswer() {
    if (!state.currentWord || state.phase !== 'input') return;
    
    state.phase = 'evaluate';
    
    if (answerInputEl) {
        answerInputEl.disabled = true;
    }
    if (btnActionEl) {
        btnActionEl.style.display = 'none';
    }
    
    // Setup answer box content
    if (state.mode === 'en_to_vi') {
        if (shortAnsEl) shortAnsEl.textContent = state.currentWord.short_translation || 'N/A';
        if (fullAnsEl) fullAnsEl.textContent = state.currentWord.translation || '';
    } else {
        if (shortAnsEl) shortAnsEl.textContent = state.currentWord.word;
        // Display both phonetic and Vietnamese definitions in details
        const details = [];
        if (state.currentWord.phonetic && state.currentWord.phonetic !== '--') {
            details.push(state.currentWord.phonetic);
        }
        if (state.currentWord.translation) {
            details.push(state.currentWord.translation);
        }
        if (fullAnsEl) fullAnsEl.textContent = details.join(' | ');
    }
    
    // Show box
    if (answerBoxEl) {
        answerBoxEl.style.display = 'block';
        
        // Scroll into view
        setTimeout(() => {
            answerBoxEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
    }
}

// Self-Evaluation POST
async function evaluate(isCorrect) {
    if (!state.currentWord || state.phase !== 'evaluate' || actionLocked) return;
    actionLocked = true;
    
    try {
        const response = await fetch('/api/fill/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word_id: state.currentWord.id,
                is_correct: isCorrect
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Toast rating alert
            const pointsLabel = isCorrect ? '+5 điểm ✅' : '-3 điểm ❌';
            const toastType = isCorrect ? 'success' : 'error';
            showToast(pointsLabel, toastType);
            
            // Session score updates
            state.sessionScore += data.delta;
            state.sessionCount++;
            
            updateSessionUI();
            
            // Load next word after 1000ms
            setTimeout(() => {
                loadNext();
            }, 1000);
            
        } else {
            showToast(data.message || "Lỗi đánh giá!", "error");
            actionLocked = false;
        }
        
    } catch (err) {
        console.error("Error evaluating guess:", err);
        showToast("Lỗi đồng bộ máy chủ!", "error");
        actionLocked = false;
    }
}

function skipWord() {
    showToast("⏭ Bỏ qua từ này", "info");
    loadNext();
}

function updateSessionUI() {
    if (sessionCountEl) sessionCountEl.textContent = state.sessionCount;
    if (sessionScoreEl) {
        const scoreVal = state.sessionScore;
        sessionScoreEl.textContent = scoreVal >= 0 ? `+${scoreVal}` : scoreVal;
    }
}

// Bind direct skip buttons
document.addEventListener('DOMContentLoaded', () => {
    const skipBtn = document.getElementById('btn-skip');
    if (skipBtn) skipBtn.addEventListener('click', skipWord);
    
    initGame();
});
