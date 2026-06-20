// State management for MCQ Session
let session = {
    queue: [],
    currentIndex: 0,
    correctAnswers: 0,
    results: [],
    hasAnsweredCurrent: false
};

// Initialize session when DOM loads
document.addEventListener('DOMContentLoaded', () => {
    startNewSession();
    
    // Keyboard shortcuts listener
    document.addEventListener('keydown', handleKeyPress);
});

// Start / Fetch MCQ queue
async function startNewSession() {
    // Show loading or reset UI
    document.getElementById('game-stage').style.display = 'block';
    document.getElementById('completion-stage').style.display = 'none';
    
    session = {
        queue: [],
        currentIndex: 0,
        correctAnswers: 0,
        results: [],
        hasAnsweredCurrent: false
    };
    
    document.getElementById('correct-count').textContent = '0';
    document.getElementById('progress-val').textContent = '0/10';
    document.getElementById('progress-fill').style.width = '0%';
    
    try {
        const response = await fetch('/api/mcq/queue');
        if (!response.ok) {
            throw new Error("Failed to fetch MCQ queue");
        }
        
        const data = await response.json();
        session.queue = data.queue || [];
        
        if (session.queue.length === 0) {
            // Handle empty state
            showEmptyState();
            return;
        }
        
        renderQuestion();
    } catch (err) {
        console.error("Error starting MCQ session:", err);
        showToast("Lỗi tải dữ liệu luyện tập!", "error");
    }
}

function showEmptyState() {
    const stage = document.getElementById('game-stage');
    stage.innerHTML = `
        <div class="prompt-card" style="padding: var(--sp-12);">
            <div style="font-size: 3rem; margin-bottom: var(--sp-4);">🔍</div>
            <h2 style="font-family: var(--font-display); font-weight: 700; margin-bottom: var(--sp-2);">Không có từ cần ôn trắc nghiệm!</h2>
            <p style="color: var(--text-secondary); margin-bottom: var(--sp-6);">Tất cả từ đã thuộc (mastered) hoặc chưa có từ nào được thêm.</p>
            <a href="/" class="btn btn-primary" style="display: inline-block;">Quay lại Dashboard</a>
        </div>
    `;
}

// Render the current question
function renderQuestion() {
    if (session.currentIndex >= session.queue.length) {
        showCompletionScreen();
        return;
    }
    
    session.hasAnsweredCurrent = false;
    
    const word = session.queue[session.currentIndex];
    
    // Progress
    const total = session.queue.length;
    const progressText = `${session.currentIndex + 1}/${total}`;
    document.getElementById('progress-val').textContent = progressText;
    
    const percent = ((session.currentIndex) / total) * 100;
    document.getElementById('progress-fill').style.width = `${percent}%`;
    
    // Prompt
    document.getElementById('word-prompt').textContent = word.word;
    document.getElementById('phonetic-prompt').textContent = word.phonetic || '';
    
    // Set data-word attributes for TTS
    const promptCard = document.getElementById('prompt-card');
    if (promptCard) promptCard.setAttribute('data-word', word.word);
    const btnTts = document.getElementById('mcq-btn-tts');
    if (btnTts) btnTts.setAttribute('data-word', word.word);
    
    // Autoplay pronunciation when new question loads
    setTimeout(() => {
        if (session.queue[session.currentIndex] && session.queue[session.currentIndex].word === word.word) {
            playWord(word.word, 'normal');
        }
    }, 300);
    
    // POS Badges
    const posContainer = document.getElementById('pos-container');
    posContainer.innerHTML = '';
    if (word.pos_entries && word.pos_entries.length > 0) {
        // Collect unique POS tags
        const uniquePos = [...new Set(word.pos_entries.map(e => e.pos).filter(Boolean))];
        uniquePos.forEach(pos => {
            const badge = document.createElement('span');
            badge.className = `badge badge-pos badge-${pos}`;
            badge.textContent = pos;
            posContainer.appendChild(badge);
        });
    }
    
    // Choices Grid
    const choicesGrid = document.getElementById('choices-grid');
    choicesGrid.innerHTML = '';
    
    word.choices.forEach((choice, index) => {
        const btn = document.createElement('button');
        btn.className = 'choice-btn';
        btn.setAttribute('data-choice', choice);
        btn.onclick = () => selectChoice(choice, index);
        
        btn.innerHTML = `
            <span class="choice-number">${index + 1}</span>
            <span class="choice-text">${choice}</span>
            <span class="choice-status-icon"></span>
        `;
        
        choicesGrid.appendChild(btn);
    });
    
    document.getElementById('btn-next').style.display = 'none';
}

// Keyboard shortcuts handler
function handleKeyPress(e) {
    // If completion stage is active, ignore
    if (document.getElementById('completion-stage').style.display === 'block') return;
    
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    // Option selection keys: 1, 2, 3, 4
    if (!session.hasAnsweredCurrent && ['1', '2', '3', '4'].includes(e.key)) {
        const index = parseInt(e.key) - 1;
        const buttons = document.querySelectorAll('.choice-btn');
        if (buttons[index]) {
            buttons[index].click();
        }
    }
    
    // Next word shortcut: Enter / Space / right arrow
    if (session.hasAnsweredCurrent && (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowRight')) {
        e.preventDefault();
        nextQuestion();
    }
}

// User selects a choice
async function selectChoice(selectedChoice, selectedIndex) {
    if (session.hasAnsweredCurrent) return;
    session.hasAnsweredCurrent = true;
    
    const word = session.queue[session.currentIndex];
    
    // Disable all options
    const buttons = document.querySelectorAll('.choice-btn');
    buttons.forEach(btn => btn.disabled = true);
    
    try {
        const response = await fetch('/api/mcq/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word_id: word.id,
                choice: selectedChoice
            })
        });
        
        if (!response.ok) {
            throw new Error("Evaluation request failed");
        }
        
        const data = await response.json();
        
        const isCorrect = data.is_correct;
        const delta = isCorrect ? 3 : -2;
        
        // Save results for results screen
        session.results.push({
            id: word.id,
            word: word.word,
            phonetic: word.phonetic,
            correct_answer: word.correct_answer,
            user_choice: selectedChoice,
            is_correct: isCorrect,
            old_score: word.knowledge_score,
            new_score: data.new_score,
            status: data.new_status
        });
        
        // Show correct/incorrect styles on choices
        buttons.forEach((btn, index) => {
            const btnChoice = btn.getAttribute('data-choice');
            if (btnChoice === word.correct_answer) {
                btn.classList.add('correct');
                btn.querySelector('.choice-status-icon').innerHTML = '✔️';
            } else if (index === selectedIndex && !isCorrect) {
                btn.classList.add('wrong');
                btn.querySelector('.choice-status-icon').innerHTML = '❌';
            }
        });
        
        if (isCorrect) {
            session.correctAnswers++;
            document.getElementById('correct-count').textContent = session.correctAnswers;
            showToast(`+3 điểm`, "success");
        } else {
            // Check if score changed (might not change if word is mastered)
            const scoreDiff = data.new_score - word.knowledge_score;
            if (scoreDiff === 0 && word.status === 'mastered') {
                showToast("Sai! Không trừ điểm (Từ đã thuộc)", "warning");
            } else {
                showToast(`Sai! -2 điểm`, "error");
            }
        }
        
        // Show next button
        document.getElementById('btn-next').style.display = 'block';
        
    } catch (err) {
        console.error("Error evaluating MCQ choice:", err);
        showToast("Lỗi chấm điểm trắc nghiệm!", "error");
        // Fallback: allow moving forward
        document.getElementById('btn-next').style.display = 'block';
    }
}

// Next Question
function nextQuestion() {
    session.currentIndex++;
    
    if (session.currentIndex < session.queue.length) {
        renderQuestion();
    } else {
        // Complete the progress fill bar to 100%
        document.getElementById('progress-fill').style.width = '100%';
        document.getElementById('progress-val').textContent = `${session.queue.length}/${session.queue.length}`;
        showCompletionScreen();
    }
}

// Show Completion screen
function showCompletionScreen() {
    document.getElementById('game-stage').style.display = 'none';
    document.getElementById('completion-stage').style.display = 'block';
    
    const total = session.queue.length;
    document.getElementById('stat-total-words').textContent = total;
    document.getElementById('stat-correct-count').textContent = session.correctAnswers;
    
    const accuracy = total > 0 ? Math.round((session.correctAnswers / total) * 100) : 0;
    document.getElementById('stat-accuracy').textContent = `${accuracy}%`;
    
    // Choose trophy and title based on accuracy
    const trophyEl = document.getElementById('trophy-icon');
    const titleEl = document.getElementById('completion-title');
    
    if (accuracy === 100) {
        trophyEl.textContent = '👑';
        titleEl.textContent = 'Tuyệt đối! Xuất sắc!';
    } else if (accuracy >= 80) {
        trophyEl.textContent = '🏆';
        titleEl.textContent = 'Giỏi quá!';
    } else if (accuracy >= 50) {
        trophyEl.textContent = '🌟';
        titleEl.textContent = 'Đạt yêu cầu!';
    } else {
        trophyEl.textContent = '💪';
        titleEl.textContent = 'Cố gắng lên!';
    }
    
    // Populate detailed words reviewed table
    const tableBody = document.getElementById('results-table-body');
    tableBody.innerHTML = '';
    
    session.results.forEach(res => {
        const tr = document.createElement('tr');
        
        // Status badge template
        let badgeClass = 'badge-new';
        let badgeLabel = 'Mới';
        if (res.status === 'learning') {
            badgeClass = 'badge-learning';
            badgeLabel = 'Đang học';
        } else if (res.status === 'mastered') {
            badgeClass = 'badge-learned';
            badgeLabel = 'Đã thuộc';
        }
        
        // Score change indicator
        const scoreDiff = res.new_score - res.old_score;
        let scoreDiffBadge = '';
        if (scoreDiff > 0) {
            scoreDiffBadge = `<span class="badge-score-diff up">+${scoreDiff}</span>`;
        } else if (scoreDiff < 0) {
            scoreDiffBadge = `<span class="badge-score-diff down">${scoreDiff}</span>`;
        } else {
            scoreDiffBadge = `<span class="badge-score-diff" style="background: var(--surface-sunken); color: var(--text-muted);">0</span>`;
        }
        
        // Correct check mark
        const resultIndicator = res.is_correct 
            ? `<span style="color: var(--color-success); font-weight: 700; margin-right: 0.5rem;">✔️</span>` 
            : `<span style="color: var(--color-danger); font-weight: 700; margin-right: 0.5rem;">❌</span>`;
            
        // Inline manual mark learned action button
        const showMarkLearnedButton = res.status !== 'mastered';
        const buttonHtml = showMarkLearnedButton 
            ? `<button class="btn btn-success btn-action-sm" onclick="markWordLearned(${res.id}, this)">✅ Thuộc</button>`
            : `<button class="btn btn-success btn-action-sm" disabled style="opacity: 0.5;">✓ Thuộc</button>`;
            
        tr.innerHTML = `
            <td>
                <div style="font-weight: 700; color: var(--text-primary);">${res.word}</div>
                <div style="font-size: var(--text-xs); color: var(--text-muted);">${res.phonetic || ''}</div>
            </td>
            <td>
                <div style="display: flex; align-items: center;">
                    ${resultIndicator}
                    <span>${res.correct_answer}</span>
                </div>
            </td>
            <td>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span class="badge ${badgeClass}" id="badge-status-${res.id}">${badgeLabel}</span>
                    <span style="font-weight: 700;" id="score-val-${res.id}">${res.new_score}</span>
                    ${scoreDiffBadge}
                </div>
            </td>
            <td id="action-cell-${res.id}">
                ${buttonHtml}
            </td>
        `;
        
        tableBody.appendChild(tr);
    });
}

// Manual Override: Mark Word as Mastered in results table
async function markWordLearned(wordId, btn) {
    if (!wordId || btn.disabled) return;
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/word/mark-learned', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: wordId })
        });
        
        if (!response.ok) {
            throw new Error("Manual mark learned failed");
        }
        
        const data = await response.json();
        if (data.success) {
            showToast("Đã đánh dấu thuộc!", "success");
            
            // Update UI elements in table row
            const scoreValEl = document.getElementById(`score-val-${wordId}`);
            if (scoreValEl) scoreValEl.textContent = '95';
            
            const badgeEl = document.getElementById(`badge-status-${wordId}`);
            if (badgeEl) {
                badgeEl.className = 'badge badge-learned';
                badgeEl.textContent = 'Đã thuộc';
            }
            
            // Update action cell button
            const cell = document.getElementById(`action-cell-${wordId}`);
            if (cell) {
                cell.innerHTML = `<button class="btn btn-success btn-action-sm" disabled style="opacity: 0.5;">✓ Thuộc</button>`;
            }
        } else {
            showToast("Không thể cập nhật trạng thái!", "error");
            btn.disabled = false;
        }
    } catch (err) {
        console.error("Error manually marking learned in MCQ table:", err);
        showToast("Lỗi cập nhật trạng thái!", "error");
        btn.disabled = false;
    }
}

// Restart session
function restartSession() {
    startNewSession();
}

// Quit session
function quitSession() {
    window.location.href = '/';
}
