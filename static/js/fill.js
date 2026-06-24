// Spelling / Fill Mode Game State
const session = {
    queue: [],
    index: 0,
    filter: 'smart_priority',
    status: 'all',
    mode: 'en_to_vi',      // 'en_to_vi' or 'vi_to_en'
    phase: 'input',        // 'input' or 'evaluate'
    sessionScore: 0,
    startedAt: null,
    currentWord: null
};

let actionLocked = false;

// DOM Cache
let flagEl = null;
let promptEl = null;
let hintLabelEl = null;
let phoneticEl = null;
let statusBadgeEl = null;
let wordScoreEl = null;
let answerInputEl = null;
let btnActionEl = null;
let answerBoxEl = null;
let shortAnsEl = null;
let fullAnsEl = null;
let btnSkipEl = null;
let progressTextEl = null;
let progressFillEl = null;
let toggleModeBtnEl = null;

function initDOMCache() {
    flagEl = document.getElementById('question-flag');
    promptEl = document.getElementById('question-prompt');
    hintLabelEl = document.getElementById('question-hint-label');
    phoneticEl = document.getElementById('question-phonetic');
    statusBadgeEl = document.getElementById('card-status-badge');
    wordScoreEl = document.getElementById('card-score');
    answerInputEl = document.getElementById('answer-input');
    btnActionEl = document.getElementById('btn-action');
    answerBoxEl = document.getElementById('answer-box');
    shortAnsEl = document.getElementById('short-answer');
    fullAnsEl = document.getElementById('full-answer');
    btnSkipEl = document.getElementById('btn-skip');
    
    // Header elements
    progressTextEl = document.getElementById('progress-text');
    progressFillEl = document.getElementById('progress-fill');
    toggleModeBtnEl = document.getElementById('btn-toggle-mode');
    
    if (toggleModeBtnEl) {
        // Re-bind to ensure no double listeners on restarts
        const newToggle = toggleModeBtnEl.cloneNode(true);
        toggleModeBtnEl.parentNode.replaceChild(newToggle, toggleModeBtnEl);
        toggleModeBtnEl = newToggle;
        toggleModeBtnEl.addEventListener('click', toggleMode);
        toggleModeBtnEl.textContent = session.mode === 'en_to_vi' ? '🇬🇧 EN → 🇻🇳 VI' : '🇻🇳 VI → 🇬🇧 EN';
    }
    
    if (btnActionEl) {
        btnActionEl.addEventListener('click', () => {
            if (session.phase === 'input') {
                submitAnswer();
            }
        });
    }
    
    if (btnSkipEl) {
        btnSkipEl.addEventListener('click', skipWord);
    }
}

// Setup Game
async function init() {
    // Store original container HTML to restore on session restarts
    window.originalCardContainerHTML = document.getElementById('card-container').innerHTML;
    
    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyDown);
    
    // Auto refocus input when clicking elsewhere on the page
    document.addEventListener('click', (e) => {
        if (answerInputEl && !answerInputEl.disabled && !e.target.closest('button') && !e.target.closest('input') && !e.target.closest('select') && !e.target.closest('a')) {
            answerInputEl.focus();
        }
    });
    
    // Setup filter headers
    await initStudyHeaderFilters(async (filter, status) => {
        session.filter = filter;
        session.status = status;
        await startSession();
    });
}

function toggleMode() {
    session.mode = session.mode === 'en_to_vi' ? 'vi_to_en' : 'en_to_vi';
    if (toggleModeBtnEl) {
        toggleModeBtnEl.textContent = session.mode === 'en_to_vi' ? '🇬🇧 EN → 🇻🇳 VI' : '🇻🇳 VI → 🇬🇧 EN';
    }
    
    // If there is a current word, refresh its display and clear input/answer box
    if (session.currentWord) {
        session.phase = 'input';
        if (answerBoxEl) answerBoxEl.style.display = 'none';
        if (answerInputEl) {
            answerInputEl.value = '';
            answerInputEl.disabled = false;
            answerInputEl.classList.remove('correct-pulse', 'wrong-pulse', 'shake');
            answerInputEl.placeholder = session.mode === 'en_to_vi' ? 'Nhập nghĩa tiếng Việt...' : 'Type English spelling here...';
            answerInputEl.focus();
        }
        if (btnActionEl) {
            btnActionEl.style.display = 'inline-block';
            btnActionEl.textContent = 'Kiểm tra →';
        }
        displayWord(session.currentWord);
    }
}

function handleKeyDown(e) {
    if (e.key === 'Enter') {
        if (session.phase === 'input') {
            e.preventDefault();
            submitAnswer();
        }
    } else if (session.phase === 'evaluate' && !actionLocked) {
        if (e.key.toLowerCase() === 'y' || e.key === 'ArrowUp') {
            e.preventDefault();
            evaluate(true);
        } else if (e.key.toLowerCase() === 'n' || e.key === 'ArrowDown') {
            e.preventDefault();
            evaluate(false);
        }
    }
}

// Khởi tạo session mới
async function startSession() {
    document.getElementById('card-container').innerHTML = window.originalCardContainerHTML;
    initDOMCache();

    // Hide empty state
    document.getElementById('fill-empty-state').style.display = 'none';

    try {
        let n = 15;
        try {
            const settingsRes = await fetch('/api/settings');
            const settings = await settingsRes.json();
            n = parseInt(settings.session_size) || 15;
        } catch (e) {
            console.error("Error loading session size setting:", e);
        }
        if (progressTextEl) progressTextEl.textContent = `0 / ${n}`;

        const res = await fetch(`/api/session/queue?filter=${session.filter}&status=${session.status}&n=${n}`);
        const data = await res.json();
        
        if (!data.queue || data.queue.length === 0) {
            document.getElementById('fill-empty-state').style.display = 'flex';
            document.getElementById('empty-state-text').textContent = `Không có từ nào phù hợp với bộ lọc "${data.filter_label}"`;
            document.getElementById('card-container').innerHTML = ''; // Clear container
            updateProgressUI();
            return;
        }
        
        session.queue = data.queue;
        session.index = 0;
        session.sessionScore = 0;
        session.startedAt = Date.now();
        
        // Show summary info
        const infoEl = document.getElementById('session-summary-info');
        if (infoEl) {
            infoEl.textContent = data.summary || `Phiên học: ${session.queue.length} từ`;
        }
        
        showWordAtIndex();
    } catch (err) {
        console.error("Error starting session:", err);
        showToast("Lỗi khởi tạo phiên học!", "error");
    }
}

function showWordAtIndex() {
    session.phase = 'input';
    actionLocked = false;
    
    // Hide answer box
    if (answerBoxEl) answerBoxEl.style.display = 'none';
    
    // Reset inputs
    if (answerInputEl) {
        answerInputEl.value = '';
        answerInputEl.disabled = false;
        answerInputEl.classList.remove('correct-pulse', 'wrong-pulse', 'shake');
        answerInputEl.placeholder = session.mode === 'en_to_vi' ? 'Nhập nghĩa tiếng Việt...' : 'Type English spelling here...';
        answerInputEl.focus();
    }
    
    if (btnActionEl) {
        btnActionEl.style.display = 'inline-block';
        btnActionEl.textContent = 'Kiểm tra →';
    }
    
    session.currentWord = session.queue[session.index];
    displayWord(session.currentWord);
    updateProgressUI();
}

function displayWord(word) {
    if (statusBadgeEl) {
        statusBadgeEl.textContent = getStatusText(word.status);
        statusBadgeEl.className = `status-badge badge-${word.status}`;
    }
    if (wordScoreEl) {
        wordScoreEl.textContent = `Điểm: ${word.knowledge_score || 0} ⭐`;
    }

    const fillPromptGroup = document.getElementById('fill-prompt-tts-group');
    const fillPromptBtn = document.getElementById('fill-prompt-btn-tts');
    const fillPromptBtnSlow = document.getElementById('fill-prompt-btn-tts-slow');

    if (session.mode === 'en_to_vi') {
        if (flagEl) flagEl.textContent = '🇬🇧';
        if (promptEl) promptEl.textContent = word.word;
        if (hintLabelEl) hintLabelEl.textContent = 'Nghĩa tiếng Việt là gì?';
        
        if (fillPromptBtn) fillPromptBtn.setAttribute('data-word', word.word);
        if (fillPromptBtnSlow) fillPromptBtnSlow.setAttribute('data-word', word.word);
        if (fillPromptGroup) fillPromptGroup.style.display = 'inline-flex';
        
        if (phoneticEl) {
            if (word.phonetic && word.phonetic !== '--' && word.phonetic.trim() !== '') {
                phoneticEl.textContent = word.phonetic;
                phoneticEl.style.display = 'block';
            } else {
                phoneticEl.style.display = 'none';
            }
        }
    } else {
        if (flagEl) flagEl.textContent = '🇻🇳';
        let promptText = word.short_translation;
        if (!promptText || promptText.trim() === '') {
            promptText = (word.translation || '').substring(0, 30);
        }
        if (promptEl) promptEl.textContent = promptText;
        if (hintLabelEl) hintLabelEl.textContent = 'Từ tiếng Anh là gì?';
        
        if (fillPromptGroup) {
            fillPromptGroup.style.display = 'none';
        }
        
        if (phoneticEl) phoneticEl.style.display = 'none';
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

function submitAnswer() {
    if (!session.currentWord || session.phase !== 'input') return;
    
    session.phase = 'evaluate';
    
    const typed = answerInputEl.value.trim().toLowerCase();
    let isMatch = false;
    
    if (session.mode === 'en_to_vi') {
        const shortTr = (session.currentWord.short_translation || '').trim().toLowerCase();
        const fullTr = (session.currentWord.translation || '').trim().toLowerCase();
        isMatch = (typed.length > 0) && (shortTr.includes(typed) || fullTr.includes(typed) || typed.includes(shortTr));
    } else {
        const expected = session.currentWord.word.trim().toLowerCase();
        isMatch = (typed === expected);
    }
    
    if (answerInputEl) {
        answerInputEl.disabled = true;
        if (isMatch) {
            answerInputEl.classList.add('correct-pulse');
        } else {
            answerInputEl.classList.add('wrong-pulse', 'shake');
            setTimeout(() => {
                answerInputEl.classList.remove('shake');
            }, 500);
        }
    }
    
    // Highlight correct or incorrect self-evaluation options
    const btnCorrect = document.querySelector('.eval-actions .btn-correct');
    const btnWrong = document.querySelector('.eval-actions .btn-wrong');
    if (btnCorrect && btnWrong) {
        btnCorrect.classList.remove('highlight-eval');
        btnWrong.classList.remove('highlight-eval');
        if (isMatch) {
            btnCorrect.classList.add('highlight-eval');
        } else {
            btnWrong.classList.add('highlight-eval');
        }
    }
    
    if (btnActionEl) {
        btnActionEl.style.display = 'none';
    }
    
    // Setup answer box content
    if (session.mode === 'en_to_vi') {
        if (shortAnsEl) shortAnsEl.textContent = session.currentWord.short_translation || 'N/A';
        if (fullAnsEl) fullAnsEl.textContent = session.currentWord.translation || '';
    } else {
        if (shortAnsEl) shortAnsEl.textContent = session.currentWord.word;
        const details = [];
        if (session.currentWord.phonetic && session.currentWord.phonetic !== '--') {
            details.push(session.currentWord.phonetic);
        }
        if (session.currentWord.translation) {
            details.push(session.currentWord.translation);
        }
        if (fullAnsEl) fullAnsEl.textContent = details.join(' | ');
    }
    
    // Set data-word attribute for TTS button inside answer box
    const fillAnswerBtn = document.getElementById('fill-answer-btn-tts');
    const fillAnswerBtnSlow = document.getElementById('fill-answer-btn-tts-slow');
    if (session.currentWord) {
        if (fillAnswerBtn) fillAnswerBtn.setAttribute('data-word', session.currentWord.word);
        if (fillAnswerBtnSlow) fillAnswerBtnSlow.setAttribute('data-word', session.currentWord.word);
    }
    
    if (answerBoxEl) {
        answerBoxEl.style.display = 'block';
        setTimeout(() => {
            answerBoxEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
    }
}

async function evaluate(isCorrect) {
    if (!session.currentWord || session.phase !== 'evaluate' || actionLocked) return;
    actionLocked = true;
    
    try {
        const response = await fetch('/api/fill/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word_id: session.currentWord.id,
                is_correct: isCorrect
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const pointsLabel = isCorrect ? '+5 điểm ✅' : '-3 điểm ❌';
            const toastType = isCorrect ? 'success' : 'error';
            showToast(pointsLabel, toastType);
            
            session.sessionScore += data.delta;
            
            setTimeout(() => {
                nextWord();
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
    nextWord();
}

function nextWord() {
    session.index++;
    updateProgressUI();
    
    if (session.index >= session.queue.length) {
        showSessionComplete();
        return;
    }
    
    showWordAtIndex();
}

function updateProgressUI() {
    if (progressTextEl) {
        progressTextEl.textContent = `${session.index} / ${session.queue.length}`;
    }
    if (progressFillEl && session.queue.length > 0) {
        const percent = Math.min(100, Math.round((session.index / session.queue.length) * 100));
        progressFillEl.style.width = `${percent}%`;
    }
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

// Bind load hooks
document.addEventListener('DOMContentLoaded', () => {
    init();
});
