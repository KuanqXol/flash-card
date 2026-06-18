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
let state = {
    words: [],           // [{id, word, short_translation}]
    viList: [],          // [{id, text}] shuffled
    selectedEn: null,    // id
    selectedVi: null,    // id
    matched: new Set(),  // set of correct word_ids
    failedWords: new Set(), // set of word_ids mismatched during this session
    results: [],         // [{word_id, is_correct}] for UI details display
    finalResults: {}     // {word_id: is_correct} (dict, overwrite if exist)
};

let gridLocked = false;
let sessionSubmitted = false;

// DOM Cache
const enColumnEl = document.getElementById('en-column');
const viColumnEl = document.getElementById('vi-column');
const progressTextEl = document.getElementById('progress-text');
const btnSubmitEl = document.getElementById('btn-submit');
const selectPairsEl = document.getElementById('select-pairs');
const selectFilterEl = document.getElementById('select-filter');

// Modal Elements
const modalEl = document.getElementById('result-modal');
const modalPointsEl = document.getElementById('modal-points');
const modalRatioEl = document.getElementById('modal-ratio');
const modalTableBodyEl = document.getElementById('modal-table-body');

// Setup Game
function initGame() {
    // Dropdowns
    if (selectPairsEl) selectPairsEl.addEventListener('change', loadWords);
    if (selectFilterEl) selectFilterEl.addEventListener('change', loadWords);
    
    // Submit btn
    if (btnSubmitEl) {
        btnSubmitEl.addEventListener('click', () => {
            if (state.matched.size === 0) {
                showToast("Bạn chưa ghép cặp nào!", "error");
                return;
            }
            submitResults();
        });
    }
    
    loadWords();
}

// Fetch and Render
async function loadWords() {
    try {
        const n = selectPairsEl ? selectPairsEl.value : 6;
        const status = selectFilterEl ? selectFilterEl.value : 'all';
        
        const response = await fetch(`/api/matching/words?n=${n}&status=${status}`);
        const data = await response.json();
        
        if (data.error === 'not_enough_words') {
            showToast(`Không đủ từ vựng! Chỉ có ${data.available} từ thỏa mãn.`, "error");
            displayEmptyState(data.available);
            return;
        }
        
        // Reset state
        state.words = data.words;
        state.viList = shuffle(data.words.map(w => ({ id: w.id, text: w.short_translation })));
        state.selectedEn = null;
        state.selectedVi = null;
        state.matched.clear();
        state.failedWords.clear();
        state.results = [];
        state.finalResults = {};
        gridLocked = false;
        sessionSubmitted = false;
        
        // Hide empty state, show game container
        document.getElementById('matching-empty-state').style.display = 'none';
        document.getElementById('matching-stage-container').style.display = 'block';
        
        if (btnSubmitEl) btnSubmitEl.disabled = true;
        updateProgressUI();
        renderColumns();
        
    } catch (err) {
        console.error("Error loading matching words:", err);
        showToast("Lỗi tải từ vựng ôn tập!", "error");
    }
}

function displayEmptyState(available) {
    document.getElementById('matching-stage-container').style.display = 'none';
    document.getElementById('matching-empty-state').style.display = 'flex';
}

function renderColumns() {
    if (!enColumnEl || !viColumnEl) return;
    
    // Render English items
    enColumnEl.innerHTML = '';
    state.words.forEach(w => {
        const card = document.createElement('div');
        card.className = 'match-card';
        card.dataset.id = w.id;
        card.dataset.type = 'en';
        card.textContent = w.word;
        card.addEventListener('click', handleEnClick);
        enColumnEl.appendChild(card);
    });
    
    // Render Shuffled Vietnamese items
    viColumnEl.innerHTML = '';
    state.viList.forEach(vi => {
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
    if (gridLocked || state.matched.has(parseInt(this.dataset.id))) return;
    
    const id = parseInt(this.dataset.id);
    state.selectedEn = id;
    
    // Highlight
    document.querySelectorAll('#en-column .match-card').forEach(c => c.classList.remove('selected'));
    this.classList.add('selected');
    
    tryMatch();
}

function handleViClick() {
    if (gridLocked || state.matched.has(parseInt(this.dataset.id))) return;
    
    const id = parseInt(this.dataset.id);
    state.selectedVi = id;
    
    // Highlight
    document.querySelectorAll('#vi-column .match-card').forEach(c => c.classList.remove('selected'));
    this.classList.add('selected');
    
    tryMatch();
}

// Match evaluation
function tryMatch() {
    if (state.selectedEn === null || state.selectedVi === null) return;
    
    const enCard = document.querySelector(`#en-column .match-card[data-id="${state.selectedEn}"]`);
    const viCard = document.querySelector(`#vi-column .match-card[data-id="${state.selectedVi}"]`);
    
    if (state.selectedEn === state.selectedVi) {
        // MATCH CORRECT
        const wordId = state.selectedEn;
        state.matched.add(wordId);
        
        // Push result: check if ever failed
        const isCorrectFirstTry = !state.failedWords.has(wordId);
        recordMatch(wordId, isCorrectFirstTry);
        
        enCard.classList.remove('selected');
        viCard.classList.remove('selected');
        enCard.classList.add('correct');
        viCard.classList.add('correct');
        
        if (btnSubmitEl) btnSubmitEl.disabled = false;
        
        resetSelections();
        updateProgressUI();
        
        // Auto submit when complete
        if (state.matched.size === state.words.length) {
            setTimeout(() => {
                submitResults();
            }, 600);
        }
        
    } else {
        // MATCH INCORRECT
        const enId = state.selectedEn;
        const viId = state.selectedVi;
        
        // Mark both IDs as mismatched in current session
        state.failedWords.add(enId);
        state.failedWords.add(viId);
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
    state.finalResults[wordId] = isCorrect;  // overwrite → chỉ giữ kết quả cuối
}

function resetSelections() {
    state.selectedEn = null;
    state.selectedVi = null;
}

function updateProgressUI() {
    if (progressTextEl) {
        progressTextEl.textContent = `${state.matched.size}/${state.words.length} cặp đã nối`;
    }
}

// Submit Results to API
async function submitResults() {
    if (sessionSubmitted) return;
    sessionSubmitted = true;
    
    // Ensure all remaining unmatched words are pushed as incorrect in results
    state.words.forEach(w => {
        if (state.finalResults[w.id] === undefined) {
            state.finalResults[w.id] = false;
        }
    });

    const finalResults = Object.entries(state.finalResults).map(([id, correct]) => ({
        word_id: parseInt(id),
        is_correct: correct
    }));

    try {
        const response = await fetch('/api/matching/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ results: finalResults })
        });
        
        const data = await response.json();
        state.results = finalResults;
        showResultModal(data);
        
    } catch (err) {
        console.error("Error submitting results:", err);
        showToast("Lỗi đồng bộ kết quả game!", "error");
        sessionSubmitted = false;
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
    const correctCount = state.results.filter(r => r.is_correct).length;
    modalRatioEl.textContent = `Đúng: ${correctCount} / ${state.words.length} cặp`;
    
    // Render details table
    if (modalTableBodyEl) {
        modalTableBodyEl.innerHTML = '';
        state.words.forEach(w => {
            const row = document.createElement('tr');
            
            // Check result mapping
            const isCorrect = state.results.find(r => r.word_id === w.id)?.is_correct;
            const resultIcon = isCorrect ? '<span style="color:#10b981; font-weight:700;">✓</span>' : '<span style="color:#f43f5e; font-weight:700;">✗</span>';
            
            row.innerHTML = `
                <td>${w.word}</td>
                <td>${w.short_translation}</td>
                <td style="text-align:center;">${resultIcon}</td>
            `;
            modalTableBodyEl.appendChild(row);
        });
    }
    
    // Display Modal
    modalEl.style.display = 'flex';
}

function closeModal() {
    if (modalEl) modalEl.style.display = 'none';
}

// Start Game on Page Ready
window.addEventListener('DOMContentLoaded', () => {
    initGame();
});
