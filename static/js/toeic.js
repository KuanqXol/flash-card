// State variables
let toeicQuestions = [];
let currentQuestionIndex = 0;
let correctAnswersCount = 0;
let secondsElapsed = 0;
let sessionTimerInterval = null;
let currentSessionDetails = [];
let loadedTopics = [];

const TENSES_LIST = [
    "Hiện tại đơn", "Hiện tại tiếp diễn", "Hiện tại hoàn thành", "Hiện tại hoàn thành tiếp diễn",
    "Quá khứ đơn", "Quá khứ tiếp diễn", "Quá khứ hoàn thành", "Quá khứ hoàn thành tiếp diễn",
    "Tương lai đơn", "Tương lai tiếp diễn", "Tương lai hoàn thành", "Tương lai hoàn thành tiếp diễn"
];

// Tab switching logic
function switchTab(tabId) {
    // Hide all tab panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.style.display = 'none';
    });

    // Remove active class from all links
    document.querySelectorAll('.tab-link').forEach(link => {
        link.classList.remove('active');
    });

    // Show selected pane and set link active
    const targetPane = document.getElementById(`tab-${tabId}`);
    if (targetPane) targetPane.style.display = 'block';

    const activeLink = Array.from(document.querySelectorAll('.tab-link')).find(link => 
        link.getAttribute('onclick').includes(tabId)
    );
    if (activeLink) activeLink.classList.add('active');

    // Trigger tab-specific loads
    if (tabId === 'history') {
        loadHistoryTable();
    } else if (tabId === 'database') {
        loadQuestionBank();
    } else if (tabId === 'practice') {
        loadTopicsDropdown();
        resetToConfigState();
    }
}

// Format duration from seconds to MM:SS
function formatDuration(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Load dynamic topics from database
async function loadTopicsDropdown() {
    try {
        const res = await fetch('/api/toeic/topics');
        const topics = await res.json();
        loadedTopics = topics;
        
        // Reset main category dropdown
        const categorySelect = document.getElementById('practice-category');
        if (categorySelect) {
            categorySelect.innerHTML = `
                <option value="all">📚 Tất cả chủ đề</option>
                <option value="wrong_questions">❌ Luyện câu làm sai</option>
                <option value="tenses">⏱ Các thì tiếng Anh (Tenses)</option>
            `;
            // Add other topics directly to the main level
            topics.forEach(t => {
                if (!TENSES_LIST.includes(t)) {
                    const opt = document.createElement('option');
                    opt.value = t;
                    opt.textContent = `🧩 ${t}`;
                    categorySelect.appendChild(opt);
                }
            });
            categorySelect.value = 'all';
        }
        
        const subtopicContainer = document.getElementById('practice-subtopic-container');
        if (subtopicContainer) {
            subtopicContainer.style.display = 'none';
        }
        
        const bankDropdown = document.getElementById('bank-filter-topic');
        if (bankDropdown) {
            bankDropdown.innerHTML = '<option value="all">Tất cả chủ đề</option>';
            
            const tensesGroup = document.createElement('optgroup');
            tensesGroup.label = "⏱ Các thì tiếng Anh";
            const othersGroup = document.createElement('optgroup');
            othersGroup.label = "🧩 Chủ đề khác";
            
            let tensesCount = 0;
            let othersCount = 0;
            
            topics.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = t;
                
                if (TENSES_LIST.includes(t)) {
                    tensesGroup.appendChild(opt);
                    tensesCount++;
                } else {
                    othersGroup.appendChild(opt);
                    othersCount++;
                }
            });
            
            if (tensesCount > 0) bankDropdown.appendChild(tensesGroup);
            if (othersCount > 0) bankDropdown.appendChild(othersGroup);
        }
        
        // Refresh question count badge
        updateQuestionCountBadge();
        // Load import batches
        await loadImportBatches();
    } catch (err) {
        console.error("Error loading TOEIC topics:", err);
    }
}

function handlePracticeCategoryChange() {
    const category = document.getElementById('practice-category').value;
    const subtopicContainer = document.getElementById('practice-subtopic-container');
    const subtopicLabel = document.getElementById('practice-subtopic-label');
    const subtopicSelect = document.getElementById('practice-subtopic');
    
    const unansweredContainer = document.getElementById('practice-unanswered-container');
    if (unansweredContainer) {
        if (category === 'wrong_questions') {
            unansweredContainer.style.display = 'none';
            const unansweredChk = document.getElementById('practice-unanswered-only');
            if (unansweredChk) unansweredChk.checked = false;
        } else {
            unansweredContainer.style.display = 'flex';
        }
    }
    
    if (!subtopicContainer || !subtopicSelect) return;
    
    if (category === 'tenses') {
        subtopicContainer.style.display = 'flex';
        subtopicSelect.innerHTML = '';
        subtopicLabel.textContent = 'Chi tiết thì';
        
        const allOpt = document.createElement('option');
        allOpt.value = 'tenses';
        allOpt.textContent = '⏱ Tất cả các thì';
        subtopicSelect.appendChild(allOpt);
        
        loadedTopics.forEach(t => {
            if (TENSES_LIST.includes(t)) {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = t;
                subtopicSelect.appendChild(opt);
            }
        });
    } else {
        // Any other category does not have a subtopic dropdown
        subtopicContainer.style.display = 'none';
    }
}

async function updateQuestionCountBadge() {
    try {
        const res = await fetch('/api/toeic/questions/list');
        const questions = await res.json();
        const badgeCount = document.getElementById('bank-count-val');
        if (badgeCount) {
            badgeCount.textContent = questions.length;
        }
    } catch (err) {
        console.error("Error updating question count badge:", err);
    }
}

// Start a practice session
async function startPracticeSession() {
    const category = document.getElementById('practice-category').value;
    let topic = category;
    
    if (category === 'tenses') {
        topic = document.getElementById('practice-subtopic').value;
    }
    
    const limitInput = document.getElementById('practice-limit');
    let limit = parseInt(limitInput.value);
    if (isNaN(limit) || limit <= 0) {
        showToast("Vui lòng nhập số lượng câu hỏi hợp lệ (lớn hơn 0)!", "warning");
        return;
    }
    
    const unansweredCheckbox = document.getElementById('practice-unanswered-only');
    const unansweredOnly = unansweredCheckbox && unansweredCheckbox.checked ? 1 : 0;
    
    // Check if there are questions in bank first
    try {
        const checkRes = await fetch('/api/toeic/questions/list');
        const totalQs = await checkRes.json();
        if (totalQs.length === 0) {
            showToast("Kho câu hỏi hiện đang trống. Hãy qua tab 'Kho câu hỏi' để nhập file Excel trước!", "warning");
            switchTab('database');
            return;
        }
    } catch (err) {
        // Continue
    }

    showToast("Đang chuẩn bị đề thi...", "info");
    
    try {
        const res = await fetch(`/api/toeic/questions?topic=${encodeURIComponent(topic)}&limit=${limit}&unanswered_only=${unansweredOnly}`);
        const questions = await res.json();
        
        if (!questions || questions.length === 0) {
            if (topic === 'wrong_questions') {
                showToast("Bạn chưa có câu hỏi nào làm sai trong lịch sử để luyện tập lại!", "warning");
            } else {
                showToast("Không tìm thấy câu hỏi phù hợp với chủ đề đã chọn!", "warning");
            }
            return;
        }
        
        // Notify user if count is less than requested limit but let them practice anyway
        if (questions.length < limit) {
            showToast(`Chỉ tìm thấy ${questions.length} câu hỏi phù hợp. Hệ thống tự động bắt đầu với ${questions.length} câu!`, "info", 4000);
        }
        
        toeicQuestions = questions;
        currentQuestionIndex = 0;
        correctAnswersCount = 0;
        secondsElapsed = 0;
        currentSessionDetails = [];
        
        // Hide config, show practice session
        document.getElementById('practice-config').style.display = 'none';
        document.getElementById('practice-completion').style.display = 'none';
        document.getElementById('practice-session').style.display = 'block';
        
        // Reset and start timer
        document.getElementById('session-timer').textContent = "00:00";
        if (sessionTimerInterval) clearInterval(sessionTimerInterval);
        sessionTimerInterval = setInterval(() => {
            secondsElapsed++;
            document.getElementById('session-timer').textContent = formatDuration(secondsElapsed);
        }, 1000);
        
        // Load the first question
        loadSessionQuestion(0);
    } catch (err) {
        console.error("Error starting TOEIC practice session:", err);
        showToast("Lỗi khi tải đề thi!", "error");
    }
}


// Load specific question during session
function loadSessionQuestion(index) {
    if (index >= toeicQuestions.length) return;
    
    const question = toeicQuestions[index];
    
    // Update progress tracking
    document.getElementById('session-progress-text').textContent = `Câu ${index + 1} / ${toeicQuestions.length}`;
    const percent = Math.round(((index + 1) / toeicQuestions.length) * 100);
    document.getElementById('session-progress-fill').style.width = `${percent}%`;
    document.getElementById('session-correct-count').textContent = correctAnswersCount;
    
    // Load question text
    document.getElementById('question-text').textContent = `${index + 1}. ${question.question}`;
    
    // Load option choices
    const grid = document.getElementById('options-grid');
    grid.innerHTML = '';
    
    const options = [
        { key: 'A', text: question.option_a },
        { key: 'B', text: question.option_b },
        { key: 'C', text: question.option_c },
        { key: 'D', text: question.option_d }
    ];
    
    options.forEach(opt => {
        const btn = document.createElement('button');
        btn.className = 'toeic-option-btn';
        btn.id = `opt-btn-${opt.key}`;
        btn.innerHTML = `
            <span class="option-prefix">${opt.key}</span>
            <span class="option-text">${opt.text}</span>
            <span class="option-status-icon"><i class="ph-fill ph-check-circle"></i></span>
        `;
        btn.onclick = () => selectSessionOption(opt.key);
        grid.appendChild(btn);
    });
    
    // Hide explanation and next button
    document.getElementById('explanation-box').style.display = 'none';
    document.getElementById('btn-session-next').style.display = 'none';
}

// Handle choosing option
function selectSessionOption(selectedKey) {
    const question = toeicQuestions[currentQuestionIndex];
    const correctKey = question.correct_option.trim().toUpperCase();
    
    // Disable all option buttons
    const btns = document.querySelectorAll('.toeic-option-btn');
    btns.forEach(btn => btn.disabled = true);
    
    const isCorrect = (selectedKey === correctKey);
    
    if (isCorrect) {
        correctAnswersCount++;
        document.getElementById('session-correct-count').textContent = correctAnswersCount;
    }
    
    // Highlight buttons
    btns.forEach(btn => {
        const key = btn.id.replace('opt-btn-', '');
        if (key === correctKey) {
            btn.classList.add('correct');
            btn.querySelector('.option-status-icon').innerHTML = '<i class="ph-fill ph-check-circle"></i>';
        } else if (key === selectedKey && !isCorrect) {
            btn.classList.add('wrong');
            btn.querySelector('.option-status-icon').innerHTML = '<i class="ph-fill ph-x-circle"></i>';
        }
    });
    
    // Populating details entry
    currentSessionDetails.push({
        question_id: question.id,
        question_text: question.question,
        option_a: question.option_a,
        option_b: question.option_b,
        option_c: question.option_c,
        option_d: question.option_d,
        user_answer: selectedKey,
        correct_answer: correctKey,
        is_correct: isCorrect,
        explanation: question.explanation,
        translation: question.translation
    });
    
    // Populate and show explanation box
    document.getElementById('exp-translation').textContent = question.translation || 'Không có dịch nghĩa.';
    document.getElementById('exp-explanation').textContent = question.explanation || 'Không có giải thích.';
    document.getElementById('explanation-box').style.display = 'block';
    
    // Show Next button
    const nextBtn = document.getElementById('btn-session-next');
    if (currentQuestionIndex === toeicQuestions.length - 1) {
        nextBtn.textContent = "Hoàn thành 🏁";
    } else {
        nextBtn.textContent = "Tiếp tục ⏭";
    }
    nextBtn.style.display = 'block';
}

// Next question trigger
function nextSessionQuestion() {
    currentQuestionIndex++;
    if (currentQuestionIndex < toeicQuestions.length) {
        loadSessionQuestion(currentQuestionIndex);
    } else {
        finishPracticeSession();
    }
}

// Finish session and log results
async function finishPracticeSession() {
    // Clear timer
    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
    
    const total = toeicQuestions.length;
    const accuracy = parseFloat(((correctAnswersCount / total) * 100).toFixed(1));
    
    const categorySelect = document.getElementById('practice-category');
    const subtopicSelect = document.getElementById('practice-subtopic');
    let topic = "Tất cả chủ đề";
    if (categorySelect) {
        const val = categorySelect.value;
        if (val === 'tenses') {
            if (subtopicSelect && subtopicSelect.value === 'tenses') {
                topic = "Các thì tiếng Anh";
            } else if (subtopicSelect) {
                topic = subtopicSelect.options[subtopicSelect.selectedIndex]?.text || subtopicSelect.value;
            }
        } else if (val === 'wrong_questions') {
            topic = "Câu hỏi làm sai";
        } else if (val === 'all') {
            topic = "Tất cả chủ đề";
        } else {
            // For custom topics directly under categorySelect, use their text representation (or value)
            topic = categorySelect.options[categorySelect.selectedIndex]?.text || val;
            // Clean up any emojis if present (e.g. "🧩 Liên từ" -> "Liên từ")
            topic = topic.replace(/^🧩\s*/, '');
        }
    }
    
    // Display results in completion stage
    document.getElementById('comp-stat-correct').textContent = `${correctAnswersCount} / ${total}`;
    document.getElementById('comp-stat-accuracy').textContent = `${accuracy}%`;
    document.getElementById('comp-stat-duration').textContent = formatDuration(secondsElapsed);
    
    // Format trophy title based on performance
    const titleEl = document.getElementById('comp-title');
    const trophyEl = document.querySelector('.trophy-container');
    if (accuracy === 100) {
        titleEl.textContent = "Xuất sắc! Đạt điểm tuyệt đối! 💯";
        trophyEl.textContent = "👑";
    } else if (accuracy >= 80) {
        titleEl.textContent = "Tuyệt vời! Bạn làm rất tốt! 👏";
        trophyEl.textContent = "🏆";
    } else if (accuracy >= 50) {
        titleEl.textContent = "Khá tốt! Hãy tiếp tục ôn tập! 👍";
        trophyEl.textContent = "🌟";
    } else {
        titleEl.textContent = "Cố gắng lên! Ôn tập kỹ hơn nhé! 💪";
        trophyEl.textContent = "📚";
    }

    // Populate results summary table
    const tableBody = document.getElementById('session-results-table-body');
    tableBody.innerHTML = '';
    
    currentSessionDetails.forEach((det, i) => {
        const tr = document.createElement('tr');
        
        let displayUserChoice = det.user_answer;
        let correctOptionText = '';
        if (det.correct_answer === 'A') correctOptionText = det.option_a;
        else if (det.correct_answer === 'B') correctOptionText = det.option_b;
        else if (det.correct_answer === 'C') correctOptionText = det.option_c;
        else if (det.correct_answer === 'D') correctOptionText = det.option_d;
        
        tr.innerHTML = `
            <td>
                <div style="font-weight:600; color:var(--text-primary);">${i + 1}. ${det.question_text}</div>
                <div id="row-exp-${i}" style="display:none; font-size:var(--text-xs); color:var(--text-secondary); margin-top:var(--sp-2); padding:var(--sp-2) var(--sp-3); border-radius:var(--radius-md); background:var(--surface-sunken); border-left: 3px solid var(--color-primary);">
                    <div><strong>Dịch nghĩa:</strong> ${det.translation || 'Không có.'}</div>
                    <div style="margin-top:4px;"><strong>Giải thích:</strong> ${det.explanation || 'Không có.'}</div>
                </div>
            </td>
            <td>
                <span class="badge ${det.is_correct ? 'badge-success' : 'badge-danger'}">${det.user_answer}</span>
            </td>
            <td><strong>${det.correct_answer}</strong> <span style="font-size:var(--text-xs); color:var(--text-muted); opacity:0.8;">(${correctOptionText})</span></td>
            <td style="text-align:center;">
                <button class="btn btn-ghost btn-action-sm" onclick="toggleSessionRowExp(${i})">
                    <i class="ph ph-caret-down" id="arrow-icon-${i}"></i>
                </button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
    
    // Send to backend
    try {
        await fetch('/api/toeic/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic,
                total_questions: total,
                correct_count: correctAnswersCount,
                accuracy: accuracy,
                duration_seconds: secondsElapsed,
                details: currentSessionDetails
            })
        });
        showToast("Lưu kết quả thành công!", "success");
    } catch (err) {
        console.error("Error submitting TOEIC results:", err);
        showToast("Lỗi kết nối khi lưu kết quả!", "error");
    }
    
    // Show completion stage
    document.getElementById('practice-session').style.display = 'none';
    document.getElementById('practice-completion').style.display = 'block';
}

function toggleSessionRowExp(index) {
    const div = document.getElementById(`row-exp-${index}`);
    const arrow = document.getElementById(`arrow-icon-${index}`);
    if (div && arrow) {
        const isHidden = div.style.display === 'none';
        div.style.display = isHidden ? 'block' : 'none';
        arrow.className = isHidden ? 'ph ph-caret-up' : 'ph ph-caret-down';
    }
}

// Reset state
function resetToConfigState() {
    document.getElementById('practice-config').style.display = 'block';
    document.getElementById('practice-session').style.display = 'none';
    document.getElementById('practice-completion').style.display = 'none';
    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
}

function quitSessionToConfig() {
    resetToConfigState();
}

function confirmQuitSession() {
    if (confirm("Bạn có chắc chắn muốn hủy phiên ôn tập hiện tại? Kết quả chưa hoàn tất sẽ bị mất.")) {
        resetToConfigState();
        showToast("Đã hủy phiên làm bài.", "info");
    }
}

function restartSession() {
    startPracticeSession();
}

// Load and populate History Table
async function loadHistoryTable() {
    const tableBody = document.getElementById('history-table-body');
    tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:var(--sp-6);">Đang tải lịch sử...</td></tr>';
    
    try {
        const res = await fetch('/api/toeic/history');
        const sessions = await res.json();
        
        if (!sessions || sessions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:var(--sp-6);">Không có lịch sử làm bài. Hãy ôn tập trước!</td></tr>';
            return;
        }
        
        tableBody.innerHTML = '';
        sessions.forEach(sess => {
            const tr = document.createElement('tr');
            
            // Format timestamp (ISO or sqlite default)
            let formattedTime = sess.timestamp;
            try {
                const date = new Date(sess.timestamp.replace(' ', 'T'));
                formattedTime = date.toLocaleString('vi-VN', { hour12: false });
            } catch(e) {}
            
            tr.innerHTML = `
                <td><strong>${formattedTime}</strong></td>
                <td><span class="badge badge-info">${sess.topic}</span></td>
                <td>${sess.correct_count} / ${sess.total_questions}</td>
                <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div class="progress-track" style="width: 50px; height: 6px; margin:0;">
                            <div class="progress-fill" style="width: ${sess.accuracy}%; background: ${sess.accuracy >= 80 ? 'var(--color-success)' : sess.accuracy >= 50 ? 'var(--color-warning)' : 'var(--color-danger)'}"></div>
                        </div>
                        <span style="font-weight: 700; color: ${sess.accuracy >= 80 ? 'var(--color-success)' : sess.accuracy >= 50 ? 'var(--color-warning)' : 'var(--color-danger)'}">${sess.accuracy}%</span>
                    </div>
                </td>
                <td><i class="ph ph-clock" style="margin-right:2px; font-size:12px;"></i> ${formatDuration(sess.duration_seconds)}</td>
                <td style="text-align:right;">
                    <button class="btn btn-secondary btn-action-sm" onclick="viewSessionDetails(${sess.id})"><i class="ph ph-eye"></i> Chi tiết</button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading TOEIC history:", err);
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--color-danger); padding:var(--sp-6);">Lỗi kết nối khi tải lịch sử.</td></tr>';
    }
}

// Modal view detail session history
async function viewSessionDetails(sessionId) {
    const modal = document.getElementById('session-detail-modal');
    const modalBody = document.getElementById('modal-session-body');
    const modalTitle = document.getElementById('modal-session-title');
    
    modalBody.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">Đang tải chi tiết...</div>';
    modal.classList.add('show');
    
    try {
        const res = await fetch('/api/toeic/history');
        const sessions = await res.json();
        const session = sessions.find(s => s.id === sessionId);
        
        if (!session) {
            modalBody.innerHTML = '<div style="text-align:center; padding:30px; color:var(--color-danger);">Không tìm thấy thông tin phiên làm bài này.</div>';
            return;
        }
        
        modalTitle.textContent = `Chi tiết làm bài: ${session.topic}`;
        
        // Parse details JSON
        let details = [];
        try {
            details = JSON.parse(session.details);
        } catch (e) {
            console.error("Error parsing details:", e);
        }
        
        if (details.length === 0) {
            modalBody.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">Không có thông tin chi tiết từng câu hỏi.</div>';
            return;
        }
        
        modalBody.innerHTML = '';
        
        details.forEach((det, i) => {
            const div = document.createElement('div');
            div.className = 'modal-detail-item';
            
            let correctOptionText = '';
            if (det.correct_answer === 'A') correctOptionText = det.option_a;
            else if (det.correct_answer === 'B') correctOptionText = det.option_b;
            else if (det.correct_answer === 'C') correctOptionText = det.option_c;
            else if (det.correct_answer === 'D') correctOptionText = det.option_d;
            
            let userChoiceText = '';
            if (det.user_answer === 'A') userChoiceText = det.option_a;
            else if (det.user_answer === 'B') userChoiceText = det.option_b;
            else if (det.user_answer === 'C') userChoiceText = det.option_c;
            else if (det.user_answer === 'D') userChoiceText = det.option_d;
            
            div.innerHTML = `
                <div style="font-weight: 700; color: var(--text-primary); font-size: var(--text-base); margin-bottom: var(--sp-3);">${i + 1}. ${det.question_text}</div>
                
                <div style="display: grid; grid-template-columns: 1fr; gap: 8px; margin-bottom: var(--sp-4);" class="config-grid">
                    <div style="padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; ${det.user_answer === 'A' ? (det.is_correct ? 'background:var(--color-success-subtle); border-color:var(--color-success);' : 'background:var(--color-danger-subtle); border-color:var(--color-danger);') : ''}">
                        <span>A. ${det.option_a}</span>
                        ${det.correct_answer === 'A' ? '<span style="color:var(--color-success); font-weight:700;"><i class="ph-fill ph-check-circle"></i></span>' : ''}
                    </div>
                    <div style="padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; ${det.user_answer === 'B' ? (det.is_correct ? 'background:var(--color-success-subtle); border-color:var(--color-success);' : 'background:var(--color-danger-subtle); border-color:var(--color-danger);') : ''}">
                        <span>B. ${det.option_b}</span>
                        ${det.correct_answer === 'B' ? '<span style="color:var(--color-success); font-weight:700;"><i class="ph-fill ph-check-circle"></i></span>' : ''}
                    </div>
                    <div style="padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; ${det.user_answer === 'C' ? (det.is_correct ? 'background:var(--color-success-subtle); border-color:var(--color-success);' : 'background:var(--color-danger-subtle); border-color:var(--color-danger);') : ''}">
                        <span>C. ${det.option_c}</span>
                        ${det.correct_answer === 'C' ? '<span style="color:var(--color-success); font-weight:700;"><i class="ph-fill ph-check-circle"></i></span>' : ''}
                    </div>
                    <div style="padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; ${det.user_answer === 'D' ? (det.is_correct ? 'background:var(--color-success-subtle); border-color:var(--color-success);' : 'background:var(--color-danger-subtle); border-color:var(--color-danger);') : ''}">
                        <span>D. ${det.option_d}</span>
                        ${det.correct_answer === 'D' ? '<span style="color:var(--color-success); font-weight:700;"><i class="ph-fill ph-check-circle"></i></span>' : ''}
                    </div>
                </div>

                <div style="background: var(--surface-sunken); border-radius: 8px; padding: 12px 16px; font-size: var(--text-sm);">
                    <div style="display:flex; gap:16px; margin-bottom:8px;">
                        <div>Đáp án của bạn: <span class="badge ${det.is_correct ? 'badge-success' : 'badge-danger'}">${det.user_answer}</span></div>
                        <div>Đáp án đúng: <span class="badge badge-success">${det.correct_answer}</span></div>
                    </div>
                    <div style="margin-bottom:6px;"><strong>Dịch nghĩa:</strong> ${det.translation || 'Không có.'}</div>
                    <div><strong>Giải thích:</strong> ${det.explanation || 'Không có.'}</div>
                </div>
            `;
            modalBody.appendChild(div);
        });
    } catch(err) {
        console.error("Error showing modal detail:", err);
        modalBody.innerHTML = '<div style="text-align:center; padding:30px; color:var(--color-danger);">Lỗi tải thông tin chi tiết.</div>';
    }
}

function closeDetailModal(e) {
    const modal = document.getElementById('session-detail-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

// Load Question Bank Table
async function loadQuestionBank() {
    const tableBody = document.getElementById('bank-table-body');
    tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:var(--sp-6);">Đang tải danh sách...</td></tr>';
    
    const searchVal = document.getElementById('bank-search-input').value.trim();
    const topicVal = document.getElementById('bank-filter-topic').value;
    const batchSelect = document.getElementById('bank-filter-batch');
    const batchVal = batchSelect ? batchSelect.value : 'all';
    
    try {
        const res = await fetch(`/api/toeic/questions/list?q=${encodeURIComponent(searchVal)}&topic=${encodeURIComponent(topicVal)}&batch=${encodeURIComponent(batchVal)}`);
        const questions = await res.json();
        
        if (!questions || questions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:var(--sp-6);">Không tìm thấy câu hỏi nào trong kho.</td></tr>';
            return;
        }
        
        tableBody.innerHTML = '';
        questions.forEach(q => {
            const tr = document.createElement('tr');
            
            tr.innerHTML = `
                <td><span class="badge badge-info">${q.topic}</span></td>
                <td>
                    <div style="font-weight:600; color:var(--text-primary);">${q.question}</div>
                    <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                        A. ${q.option_a} | B. ${q.option_b} | C. ${q.option_c} | D. ${q.option_d}
                    </div>
                </td>
                <td style="font-weight:700; color:var(--color-success);">${q.correct_option}</td>
                <td style="text-align:right;">
                    <button class="btn btn-ghost" onclick="deleteSingleQuestion(${q.id})" style="color:var(--color-danger); padding:var(--sp-1-5);"><i class="ph ph-trash"></i></button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
        
        // Update total questions count badge
        document.getElementById('bank-count-val').textContent = questions.length;
    } catch(err) {
        console.error("Error loading question bank:", err);
        tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--color-danger); padding:var(--sp-6);">Lỗi tải câu hỏi từ DB.</td></tr>';
    }
}

// Debounced bank filter trigger
let filterTimeout = null;
function filterQuestionBank() {
    if (filterTimeout) clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => {
        loadQuestionBank();
    }, 200);
}

// Delete single question
async function deleteSingleQuestion(qid) {
    if (confirm("Bạn có chắc chắn muốn xóa câu hỏi này khỏi kho dữ liệu?")) {
        try {
            const res = await fetch(`/api/toeic/questions/${qid}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                showToast("Đã xóa câu hỏi.", "success");
                loadQuestionBank();
                loadTopicsDropdown();
            } else {
                showToast("Lỗi khi xóa câu hỏi!", "error");
            }
        } catch(err) {
            showToast("Lỗi kết nối khi xóa!", "error");
        }
    }
}

// Delete all database questions
async function confirmDeleteAllQuestions() {
    if (confirm("CẢNH BÁO: Hành động này sẽ XÓA SẠCH toàn bộ câu hỏi và lịch sử làm bài TOEIC. Bạn có chắc chắn muốn tiếp tục?")) {
        try {
            const res = await fetch('/api/toeic/questions/delete-all', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast("Đã xóa sạch kho dữ liệu TOEIC.", "success");
                loadQuestionBank();
                loadTopicsDropdown();
            } else {
                showToast("Lỗi khi xóa sạch kho dữ liệu!", "error");
            }
        } catch(err) {
            showToast("Lỗi kết nối!", "error");
        }
    }
}

// Trigger file input
function triggerFileInput() {
    document.getElementById('excel-file-input').click();
}

// Handle file drop
function handleFileSelect(e) {
    const files = e.target.files || e.dataTransfer.files;
    if (files.length === 0) return;
    
    const file = files[0];
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
        showToast("Vui lòng chỉ tải lên file Excel (.xlsx, .xls)!", "error");
        return;
    }
    
    uploadExcelFile(file);
}

// Upload file using AJAX XHR
function uploadExcelFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    showToast("Đang tải file lên và xử lý...", "info");
    
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/toeic/import', true);
    
    xhr.onload = function() {
        if (xhr.status === 200) {
            try {
                const res = JSON.parse(xhr.responseText);
                if (res.success) {
                    showToast(`Nhập dữ liệu thành công! Đã thêm: ${res.imported} | Cập nhật: ${res.updated} | Bỏ qua: ${res.skipped}`, "success", 5000);
                    // Refresh components
                    loadQuestionBank();
                    loadTopicsDropdown();
                } else {
                    showToast(`Import thất bại: ${res.error}`, "error");
                }
            } catch(e) {
                showToast("Lỗi phản hồi dữ liệu từ máy chủ!", "error");
            }
        } else {
            showToast(`Lỗi máy chủ (${xhr.status})!`, "error");
        }
    };
    
    xhr.onerror = function() {
        showToast("Lỗi kết nối mạng khi tải lên!", "error");
    };
    
    xhr.send(formData);
}

// Setup drag and drop elements
function initDragAndDrop() {
    const zone = document.getElementById('excel-drag-drop');
    if (!zone) return;
    
    ['dragenter', 'dragover'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        }, false);
    });
    
    zone.addEventListener('drop', (e) => {
        handleFileSelect(e);
    }, false);
}

async function loadImportBatches() {
    try {
        const res = await fetch('/api/toeic/batches');
        const batches = await res.json();
        const batchSelect = document.getElementById('bank-filter-batch');
        if (batchSelect) {
            const currentVal = batchSelect.value;
            batchSelect.innerHTML = '<option value="all">Tất cả đợt nhập</option>';
            batches.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b;
                opt.textContent = b;
                batchSelect.appendChild(opt);
            });
            if (batches.includes(currentVal)) {
                batchSelect.value = currentVal;
            } else {
                batchSelect.value = 'all';
            }
        }
    } catch (err) {
        console.error("Error loading import batches:", err);
    }
}

async function deleteSelectedBatch() {
    const batchSelect = document.getElementById('bank-filter-batch');
    if (!batchSelect) return;
    const batchVal = batchSelect.value;
    if (batchVal === 'all') {
        showToast("Vui lòng chọn một đợt nhập cụ thể để xóa!", "warning");
        return;
    }
    
    if (confirm(`Bạn có chắc chắn muốn xóa toàn bộ câu hỏi thuộc đợt nhập "${batchVal}"?`)) {
        try {
            const res = await fetch(`/api/toeic/batches/${encodeURIComponent(batchVal)}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã xóa thành công đợt nhập "${batchVal}" (${data.deleted_count} câu hỏi).`, "success");
                loadQuestionBank();
                loadTopicsDropdown();
            } else {
                showToast("Lỗi khi xóa đợt nhập!", "error");
            }
        } catch (err) {
            console.error("Error deleting batch:", err);
            showToast("Lỗi kết nối khi xóa đợt nhập!", "error");
        }
    }
}

// Run initial configurations
document.addEventListener('DOMContentLoaded', () => {
    loadTopicsDropdown();
    initDragAndDrop();
});
