// Core client-side state for /words route
const state = {
    query: '',
    selectedStatuses: [],
    selectedTimeFilters: [],
    selectedPerfFilters: [],
    sort: 'alpha',
    page: 1,
    perPage: 40
};

// Debounce helper to limit search fetch calls
function debounce(fn, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

// Select all DOM elements
const searchInput = document.getElementById('words-search-input');
const sortSelect = document.getElementById('words-sort-select');
const tbody = document.getElementById('words-tbody');
const totalLabel = document.getElementById('words-total-label');
const selectAllCheckbox = document.getElementById('words-select-all');
const bulkActionsBar = document.getElementById('bulk-actions-bar');
const bulkSelectedCount = document.getElementById('bulk-selected-count');
const bulkActionSelect = document.getElementById('bulk-action-select');
const paginationInfo = document.getElementById('pagination-info-label');
const paginationControls = document.getElementById('pagination-controls-wrapper');

// Register Event Listeners
if (searchInput) {
    searchInput.addEventListener('input', debounce(() => {
        state.query = searchInput.value;
        state.page = 1;
        fetchWords();
    }, 300));
}

if (sortSelect) {
    sortSelect.addEventListener('change', () => {
        state.sort = sortSelect.value;
        state.page = 1;
        fetchWords();
    });
}

// Listeners will be dynamically bound in loadFilters()

// Bulk Select All checkbox logic
if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener('change', (e) => {
        const checkboxes = document.querySelectorAll('.word-row-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
        });
        updateBulkActionsBar();
    });
}

// Core API query function
async function fetchWords() {
    // Show spinner skeleton before querying
    tbody.innerHTML = `
        <tr>
            <td colspan="6">
                <div class="spinner-container">
                    <div class="spinner"></div>
                </div>
            </td>
        </tr>
    `;
    
    // Clear select all checkbox
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
    updateBulkActionsBar();

    const params = new URLSearchParams({
        q: state.query || '',
        statuses: state.selectedStatuses.join(','),
        time_filters: state.selectedTimeFilters.join(','),
        perf_filters: state.selectedPerfFilters.join(','),
        sort: state.sort,
        page: state.page,
        per_page: state.perPage
    });

    try {
        const res = await fetch('/api/words/search?' + params);
        if (!res.ok) throw new Error('Search failed');
        const data = await res.json();
        
        renderWordList(data.words);
        renderPagination(data);
        updateResultCount(data.total);
        updateStatusCounts(); // Refresh status badge counts
    } catch (err) {
        console.error("Fetch words error:", err);
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--danger); padding: var(--sp-6);">
                    <i class="ph ph-warning-octagon" style="font-size: 2rem;"></i>
                    <p style="margin-top: var(--sp-2); font-weight: 600;">Lỗi khi kết nối với máy chủ!</p>
                </td>
            </tr>
        `;
    }
}

// Highlight word match helper
function highlightMatch(text, query) {
    if (!text) return '';
    if (!query) return text;
    // Escape special regex chars
    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(${escapedQuery})`, 'gi');
    return text.replace(re, '<mark>$1</mark>');
}

// Render search results inside table body
function renderWordList(words) {
    if (!words || words.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 3rem 1rem;">
                    <div style="font-size: 2.5rem; margin-bottom: var(--sp-2);">📭</div>
                    <p style="font-weight: 600; font-family: var(--font-display);">Không tìm thấy từ vựng nào</p>
                    <small>Thử thay đổi từ khóa hoặc bộ lọc của bạn.</small>
                </td>
            </tr>
        `;
        return;
    }

    const badgeClasses = {
        'new': 'badge-new',
        'learning': 'badge-learning',
        'learned': 'badge-learned',
        'mastered': 'badge-learned'
    };

    const badgeLabels = {
        'new': 'Mới',
        'learning': 'Học',
        'learned': 'Thuộc',
        'mastered': 'Thuộc'
    };

    let html = '';
    words.forEach(w => {
        const query = state.query;
        const highlightedSpelling = highlightMatch(w.word, query);
        const highlightedPhonetic = w.phonetic ? highlightMatch(w.phonetic, query) : '';
        const highlightedShortTranslation = highlightMatch(w.short_translation || '', query);
        const badgeClass = badgeClasses[w.status] || 'badge-new';
        const badgeLabel = badgeLabels[w.status] || 'Mới';
        
        const warningBadge = w.needs_review ? `<span class="badge-warning" style="margin-left: 6px; font-size: 10px; padding: 1px 4px;">⚠️ Cần ôn</span>` : '';

        html += `
            <tr class="word-row" id="row-${w.id}" onclick="handleRowClick(event, ${w.id})">
                <td class="cell-checkbox" onclick="event.stopPropagation()">
                    <input type="checkbox" class="word-row-checkbox" data-id="${w.id}" onchange="updateBulkActionsBar()">
                </td>
                <td class="cell-status">
                    <span class="badge ${badgeClass}">${badgeLabel}</span>
                </td>
                <td class="cell-word">
                    <div class="word-spelling-container" style="display: flex; align-items: center; gap: 8px;">
                        <span class="word-spelling" onclick="event.stopPropagation(); openDetailModal(${w.id})" style="cursor: pointer; text-decoration: underline; color: var(--primary);">${highlightedSpelling}</span>
                        <button class="btn-tts" onclick="event.stopPropagation(); playWord('${w.word.replace(/'/g, "\\'")}', 'normal')" data-word="${w.word}" aria-label="Nghe phát âm">
                            <i class="ph ph-speaker-high"></i>
                        </button>
                        ${warningBadge}
                    </div>
                    <div class="word-phonetic">${highlightedPhonetic}</div>
                </td>
                <td class="cell-translation">
                    ${highlightedShortTranslation}
                </td>
                <td class="cell-score">
                    <span class="score-badge">${w.knowledge_score}</span>
                </td>
                <td class="cell-actions" onclick="event.stopPropagation()">
                    <button class="action-btn" title="Chỉnh sửa" onclick="openEditModal(${w.id}, '${escapeQuote(w.word)}', '${escapeQuote(w.phonetic || '')}', '${escapeQuote(w.translation)}', '${escapeQuote(w.example || '')}')">
                        <i class="ph ph-pencil-simple"></i>
                    </button>
                    <button class="action-btn btn-delete" title="Xóa từ" onclick="deleteWord(${w.id}, '${escapeQuote(w.word)}')">
                        <i class="ph ph-trash"></i>
                    </button>
                </td>
            </tr>
            <tr class="word-row-detail-tr" id="detail-tr-${w.id}" onclick="event.stopPropagation()">
                <td colspan="6" style="padding: 0; border-bottom: 1px solid var(--border);">
                    <div class="word-row-detail" id="detail-div-${w.id}">
                        <div class="word-row-detail-container">
                            <div class="detail-section">
                                <!-- POS Breakdown -->
                                <div>
                                    <div class="detail-part-title">
                                        Chi tiết nghĩa vựng
                                    </div>
                                    <div class="detail-pos-list" id="detail-pos-list-${w.id}">
                                        <!-- POS entries parsed here -->
                                    </div>
                                </div>
                                <!-- Statistics -->
                                <div>
                                    <div class="detail-part-title">
                                        Tiến trình ôn tập
                                         <span style="font-size: 0.75rem; text-transform: none; font-weight: normal; color: var(--text-secondary);" id="detail-last-reviewed-${w.id}"></span>
                                    </div>
                                    <div class="detail-stats-grid">
                                        <div class="stat-item">
                                            <span class="stat-label">Độ thuần thục</span>
                                            <span class="stat-val" style="color: var(--primary);">${Math.round(w.mastery_score)}%</span>
                                        </div>
                                        <div class="stat-item">
                                            <span class="stat-label">Số lần đúng/sai</span>
                                            <span class="stat-val">${w.correct_count} / ${w.wrong_count}</span>
                                        </div>
                                        <div class="stat-item">
                                            <span class="stat-label">Tổng lượt ôn tập</span>
                                            <span class="stat-val">${w.review_count} lần</span>
                                        </div>
                                        <div class="stat-item">
                                            <span class="stat-label">Độ chính xác</span>
                                            <span class="stat-val">${w.review_count > 0 ? Math.round(w.correct_count / w.review_count * 100) : 0}%</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Detailed Action Buttons inside Expanded panel -->
                            <div class="detail-footer-actions">
                                <button class="btn btn-primary" onclick="openDetailModal(${w.id})">
                                    <i class="ph ph-file-text"></i> Xem phân tích chi tiết
                                </button>
                                <button class="btn btn-ghost" onclick="openEditModal(${w.id}, '${escapeQuote(w.word)}', '${escapeQuote(w.phonetic || '')}', '${escapeQuote(w.translation)}', '${escapeQuote(w.example || '')}')">
                                    <i class="ph ph-pencil-simple"></i> Chỉnh sửa từ
                                </button>
                                <button class="btn btn-ghost" onclick="viewHistory(${w.id}, '${escapeQuote(w.word)}', '${escapeQuote(w.short_translation || '')}')">
                                    <i class="ph ph-clock-counter-clockwise"></i> Lịch sử ôn
                                </button>
                                <button class="btn btn-ghost" id="warn-toggle-btn-${w.id}" onclick="toggleNeedsReview(${w.id})">
                                    ${w.needs_review ? '<i class="ph ph-check-square"></i> Bỏ Cần ôn' : '<i class="ph ph-warning"></i> Đánh dấu Cần ôn'}
                                </button>
                                
                                <div style="margin-left: auto; display: flex; gap: var(--sp-2);">
                                    ${w.status === 'new' ? `
                                        <button class="btn btn-primary" onclick="updateStatus(${w.id}, 'mark_learning')">
                                            <i class="ph ph-rocket-launch"></i> Bắt đầu học
                                        </button>
                                        <button class="btn btn-success" onclick="updateStatus(${w.id}, 'mark_learned')">
                                            <i class="ph ph-check-circle"></i> Đã thuộc
                                        </button>
                                    ` : (w.status === 'learning' ? `
                                        <button class="btn btn-success" onclick="updateStatus(${w.id}, 'mark_learned')">
                                            <i class="ph ph-check-circle"></i> Đã thuộc
                                        </button>
                                    ` : `
                                        <button class="btn btn-ghost" onclick="updateStatus(${w.id}, 'mark_learning')">
                                            <i class="ph ph-lock-key-open"></i> Bỏ đánh dấu
                                        </button>
                                    `)}
                                    <button class="btn btn-danger" onclick="resetWordStats(${w.id})">
                                        <i class="ph ph-sparkle"></i> Đặt lại điểm số
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

// Escape helper for strings to pass to inline JS callbacks safely
function escapeQuote(str) {
    if (!str) return '';
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// Global page cache of words to avoid roundtrips for POS listings
let pageWordsCache = [];

// Override renderWordList to save cache
const originalRenderWordList = renderWordList;
renderWordList = function(words) {
    pageWordsCache = words;
    originalRenderWordList(words);
};

// Override handleRowClick to fetch POS from cache
function handleRowClick(event, wordId) {
    if (event.target.closest('input') || event.target.closest('button') || event.target.closest('.action-btn')) {
        return;
    }

    const row = document.getElementById(`row-${wordId}`);
    const detailTr = document.getElementById(`detail-tr-${wordId}`);
    const isExpanded = row.classList.contains('expanded');

    // Collapse all other rows
    document.querySelectorAll('.word-row.expanded').forEach(r => {
        if (r.id !== `row-${wordId}`) {
            r.classList.remove('expanded');
        }
    });
    
    // Toggle current
    row.classList.toggle('expanded');
    
    if (row.classList.contains('expanded')) {
        // Find cached word
        const w = pageWordsCache.find(x => x.id === wordId);
        if (w) {
            // Render POS
            const posListContainer = document.getElementById(`detail-pos-list-${wordId}`);
            if (posListContainer) {
                if (w.pos_entries && w.pos_entries.length > 0) {
                    posListContainer.innerHTML = w.pos_entries.map(e => `
                        <div class="pos-entry">
                            <span class="pos-badge">${e.pos || 'phrase'}</span>
                            <span class="meaning-text">${e.meaning}</span>
                        </div>
                    `).join('');
                } else {
                    posListContainer.innerHTML = `<p class="meaning-text">${w.translation}</p>`;
                }
            }
            
            // Format relative review time
            const lastReviewLabel = document.getElementById(`detail-last-reviewed-${wordId}`);
            if (lastReviewLabel) {
                lastReviewLabel.textContent = `Lần ôn gần nhất: ${formatRelativeTime(w.last_reviewed)}`;
            }
        }
    }
}

// Date formatter to relative time string
function formatRelativeTime(dateStr) {
    if (!dateStr) return 'Chưa ôn tập';
    
    // Handle standard datetime string
    let dStr = dateStr;
    if (dStr.includes(' ')) {
        dStr = dStr.replace(' ', 'T'); // Convert to standard ISO if needed
    }
    
    const parsed = new Date(dStr);
    if (isNaN(parsed.getTime())) return dateStr;
    
    const now = new Date();
    const diffMs = now - parsed;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    
    if (diffSec < 60) return 'Vừa xong';
    if (diffMin < 60) return `${diffMin} phút trước`;
    if (diffHour < 24) return `${diffHour} giờ trước`;
    if (diffDay === 1) return 'Hôm qua';
    if (diffDay < 30) return `${diffDay} ngày trước`;
    
    return parsed.toLocaleDateString('vi-VN');
}

// Render table page controls
function renderPagination(data) {
    if (!data || data.pages <= 1) {
        paginationControls.innerHTML = '';
        paginationInfo.textContent = `Hiển thị 1 - ${data.total} của ${data.total} từ`;
        return;
    }

    const current = data.page;
    const totalPages = data.pages;
    const perPage = state.perPage;
    
    const startIdx = (current - 1) * perPage + 1;
    const endIdx = Math.min(current * perPage, data.total);
    
    paginationInfo.textContent = `Hiển thị ${startIdx} - ${endIdx} của ${data.total} từ`;

    let html = '';
    
    // Previous Page Button
    html += `
        <button class="page-btn" ${current === 1 ? 'disabled' : ''} onclick="goToPage(${current - 1})">
            &laquo;
        </button>
    `;
    
    // Page Numbers
    const range = 2; // numbers to show before/after current
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= current - range && i <= current + range)) {
            html += `
                <button class="page-btn ${i === current ? 'active' : ''}" onclick="goToPage(${i})">
                    ${i}
                </button>
            `;
        } else if (i === current - range - 1 || i === current + range + 1) {
            html += `<span style="padding: var(--sp-1); color: var(--text-secondary);">...</span>`;
        }
    }
    
    // Next Page Button
    html += `
        <button class="page-btn" ${current === totalPages ? 'disabled' : ''} onclick="goToPage(${current + 1})">
            &raquo;
        </button>
    `;
    
    paginationControls.innerHTML = html;
}

// Set active page
function goToPage(page) {
    state.page = page;
    fetchWords();
}

// Update results counter labels
function updateResultCount(total) {
    totalLabel.textContent = `(${total} từ)`;
}

// Fetch status totals to display beside radio items
async function updateStatusCounts() {
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) return;
        const stats = await res.json();
        
        const countAllEl = document.getElementById('count-all');
        if (countAllEl) countAllEl.textContent = stats.total || 0;
        const countNewEl = document.getElementById('count-new');
        if (countNewEl) countNewEl.textContent = stats.new || 0;
        const countLearningEl = document.getElementById('count-learning');
        if (countLearningEl) countLearningEl.textContent = stats.learning || 0;
        const countLearnedEl = document.getElementById('count-learned');
        if (countLearnedEl) countLearnedEl.textContent = stats.learned || 0;
        
        // Update sidebar nav badge count
        const sidebarBadge = document.getElementById('nav-word-count');
        if (sidebarBadge) sidebarBadge.textContent = stats.total || 0;
    } catch (err) {
        console.error("Error updating status counts:", err);
    }
}

// Enable/Disable bulk actions bar based on checked items
function updateBulkActionsBar() {
    const checkedBoxes = document.querySelectorAll('.word-row-checkbox:checked');
    const totalCheckboxes = document.querySelectorAll('.word-row-checkbox');
    const checkedCount = checkedBoxes.length;

    if (checkedCount > 0) {
        bulkSelectedCount.textContent = `${checkedCount} từ đã chọn`;
        bulkActionsBar.style.display = 'flex';
    } else {
        bulkActionsBar.style.display = 'none';
    }

    if (selectAllCheckbox && totalCheckboxes.length > 0) {
        selectAllCheckbox.checked = (checkedCount === totalCheckboxes.length);
    }
}

// Apply single word status update (mark learned / learning)
async function updateStatus(id, action) {
    const endpoint = action === 'mark_learned' ? '/api/word/mark-learned' : '/api/word/mark-learning';
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: id })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Đã cập nhật trạng thái từ vựng!", "success");
            fetchWords();
        } else {
            showToast(data.message || "Cập nhật thất bại!", "error");
        }
    } catch (err) {
        console.error(err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// Reset word stats score
async function resetWordStats(id) {
    if (!confirm("Bạn có chắc chắn muốn đặt lại điểm số và lịch sử ôn tập cho từ này về 0?")) {
        return;
    }
    try {
        const res = await fetch(`/api/word/${id}/reset`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast("Đã đặt lại thông số từ vựng!", "success");
            fetchWords();
        } else {
            showToast(data.error || "Đặt lại thất bại!", "error");
        }
    } catch (err) {
        console.error(err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// Toggle warning needs_review
async function toggleNeedsReview(id) {
    try {
        const res = await fetch(`/api/word/${id}/toggle-warning`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            const btn = document.getElementById(`warn-toggle-btn-${id}`);
            if (btn) {
                btn.innerHTML = data.needs_review ? '✅ Bỏ đánh dấu Cần ôn' : '⚠️ Đánh dấu Cần ôn lại';
            }
            showToast(data.needs_review ? "Đã đánh dấu cần ôn lại!" : "Đã gỡ đánh dấu ôn lại!", "success");
            fetchWords();
        } else {
            showToast(data.error || "Thao tác thất bại!", "error");
        }
    } catch (err) {
        console.error(err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// Single delete confirmation
async function deleteWord(id, spelling) {
    if (!confirm(`Bạn có chắc chắn muốn xóa vĩnh viễn từ vựng "${spelling}"? Hành động này không thể hoàn tác.`)) {
        return;
    }
    try {
        const res = await fetch(`/api/words/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast(`Đã xóa từ vựng "${spelling}"!`, "success");
            fetchWords();
        } else {
            showToast(data.message || "Xóa thất bại!", "error");
        }
    } catch (err) {
        console.error(err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// Bulk Actions Dispatcher
async function applyBulkAction() {
    const action = bulkActionSelect.value;
    if (!action) {
        showToast("Vui lòng chọn hành động!", "warning");
        return;
    }

    const checkedBoxes = document.querySelectorAll('.word-row-checkbox:checked');
    const wordIds = Array.from(checkedBoxes).map(cb => parseInt(cb.getAttribute('data-id')));
    
    if (wordIds.length === 0) {
        showToast("Vui lòng chọn ít nhất một từ vựng!", "warning");
        return;
    }

    // Double check if action is delete
    if (action === 'delete') {
        if (!confirm(`Bạn có chắc chắn muốn xóa vĩnh viễn ${wordIds.length} từ vựng đã chọn?`)) {
            return;
        }
        
        try {
            const res = await fetch('/api/words/bulk-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: wordIds })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã xóa thành công ${data.deleted_count} từ vựng!`, "success");
                bulkActionSelect.value = '';
                fetchWords();
            } else {
                showToast(data.error || "Xóa hàng loạt thất bại!", "error");
            }
        } catch (err) {
            console.error(err);
            showToast("Lỗi kết nối máy chủ!", "error");
        }
    } else {
        // Other bulk actions: mark_learned, mark_learning, reset
        try {
            const res = await fetch('/api/words/bulk-action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action, word_ids: wordIds })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã áp dụng hành động cho ${data.affected} từ vựng!`, "success");
                bulkActionSelect.value = '';
                fetchWords();
            } else {
                showToast(data.message || "Thao tác hàng loạt thất bại!", "error");
            }
        } catch (err) {
            console.error(err);
            showToast("Lỗi kết nối máy chủ!", "error");
        }
    }
}

// ADD & EDIT MODAL HANDLERS
const wordModal = document.getElementById('word-modal');
const wordForm = document.getElementById('word-form');
const formWordId = document.getElementById('form-word-id');
const formSpelling = document.getElementById('form-word-spelling');
const formPhonetic = document.getElementById('form-word-phonetic');
const formTranslation = document.getElementById('form-word-translation');
const wordModalTitle = document.getElementById('word-modal-title');
const formSubmitBtn = document.getElementById('form-submit-btn');

function openAddModal() {
    wordForm.reset();
    formWordId.value = '';
    const formExample = document.getElementById('form-word-example');
    if (formExample) formExample.value = '';
    wordModalTitle.textContent = 'Thêm từ vựng';
    formSubmitBtn.textContent = 'Thêm từ mới';
    wordModal.style.display = 'flex';
}

function openEditModal(id, word, phonetic, translation, example = '') {
    formWordId.value = id;
    formSpelling.value = word;
    formPhonetic.value = phonetic;
    formTranslation.value = translation;
    const formExample = document.getElementById('form-word-example');
    if (formExample) formExample.value = example;
    wordModalTitle.textContent = 'Chỉnh sửa từ vựng';
    formSubmitBtn.textContent = 'Lưu thay đổi';
    wordModal.style.display = 'flex';
}

function closeWordModal() {
    wordModal.style.display = 'none';
}

// Modal Form Submission Callback
async function handleWordSubmit(event) {
    event.preventDefault();
    const id = formWordId.value;
    const isEdit = id && id.trim() !== '';
    
    const formExample = document.getElementById('form-word-example');
    const payload = {
        word: formSpelling.value.trim(),
        phonetic: formPhonetic.value.trim(),
        translation: formTranslation.value.trim(),
        example: formExample ? formExample.value.trim() : ''
    };

    if (!payload.word || !payload.translation) {
        showToast("Vui lòng điền đầy đủ các thông tin bắt buộc!", "error");
        return;
    }

    const endpoint = isEdit ? `/api/words/${id}/edit` : '/api/words/add';
    const method = isEdit ? 'PUT' : 'POST';

    try {
        const res = await fetch(endpoint, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (data.success) {
            showToast(isEdit ? "Đã lưu thay đổi từ vựng!" : "Đã thêm từ vựng thành công!", "success");
            closeWordModal();
            fetchWords();
        } else {
            if (data.error === 'duplicate') {
                showToast("Lỗi: Từ vựng này đã tồn tại trong hệ thống!", "error");
            } else {
                showToast(data.message || "Lưu từ vựng thất bại!", "error");
            }
        }
    } catch (err) {
        console.error(err);
        showToast("Lỗi kết nối máy chủ!", "error");
    }
}

// IMPORT CSV MODAL HANDLERS
const importModal = document.getElementById('import-modal');
const dropZone = document.getElementById('drop-zone');
const filePreview = document.getElementById('file-preview');
const previewFilename = document.getElementById('preview-filename');
const previewFilesize = document.getElementById('preview-filesize');
const importLoading = document.getElementById('import-loading');
const importResult = document.getElementById('import-result');
const fileInput = document.getElementById('file-input');
let selectedFile = null;

function openImportModal() {
    resetImportModal();
    importModal.style.display = 'flex';
    
    // Register Drag and Drop events (attaches only once)
    if (dropZone && !dropZone.dataset.eventsAttached) {
        dropZone.dataset.eventsAttached = 'true';
        
        ['dragenter', 'dragover'].forEach(name => {
            dropZone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            });
        });
        
        ['dragleave', 'drop'].forEach(name => {
            dropZone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            });
        });
        
        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            handleFileSelect(files);
        });
    }
}

function handleFileSelect(files) {
    if (files.length === 0) return;
    const file = files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showToast("Vui lòng chọn file định dạng CSV!", "error");
        return;
    }
    selectedFile = file;
    previewFilename.textContent = file.name;
    
    // Format size
    const sizeKB = (file.size / 1024).toFixed(1);
    previewFilesize.textContent = `${sizeKB} KB`;
    
    dropZone.style.display = 'none';
    filePreview.style.display = 'flex';
}

function resetImportModal() {
    selectedFile = null;
    if (fileInput) fileInput.value = '';
    dropZone.style.display = 'flex';
    filePreview.style.display = 'none';
    importLoading.style.display = 'none';
    importResult.style.display = 'none';
}

function closeImportModal(shouldRefresh = false) {
    importModal.style.display = 'none';
    if (shouldRefresh) {
        state.page = 1;
        fetchWords();
    }
}

async function startImport() {
    if (!selectedFile) return;
    
    filePreview.style.display = 'none';
    importLoading.style.display = 'flex';
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
        const res = await fetch('/api/import', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        importLoading.style.display = 'none';
        importResult.style.display = 'flex';
        
        const summary = document.getElementById('result-summary');
        const details = document.getElementById('result-details');
        
        if (data.success) {
            summary.textContent = 'Import Thành Công!';
            summary.style.color = 'var(--success)';
            details.innerHTML = `
                Đã thêm mới: <strong>${data.imported}</strong> từ<br>
                Đã cập nhật: <strong>${data.updated}</strong> từ<br>
                Bị bỏ qua: <strong>${data.skipped}</strong> từ<br>
                Tổng số dòng đã quét: <strong>${data.total}</strong>
            `;
            showToast("Nhập dữ liệu thành công!", "success");
        } else {
            summary.textContent = 'Import Thất Bại';
            summary.style.color = 'var(--danger)';
            details.textContent = data.error || 'Có lỗi xảy ra trong quá trình import file CSV.';
            showToast("Import dữ liệu thất bại!", "error");
        }
    } catch (err) {
        console.error(err);
        importLoading.style.display = 'none';
        importResult.style.display = 'flex';
        document.getElementById('result-summary').textContent = 'Lỗi kết nối';
        document.getElementById('result-details').textContent = 'Không thể gửi yêu cầu import lên máy chủ.';
        showToast("Lỗi máy chủ khi import!", "error");
    }
}

// HISTORY REVIEW LOG MODAL HANDLERS
const historyModal = document.getElementById('history-modal');
const historyListWrapper = document.getElementById('history-list-wrapper');
const historyWordTitle = document.getElementById('history-word-title');
const historyWordTranslation = document.getElementById('history-word-translation');

async function viewHistory(id, word, shortTranslation) {
    historyWordTitle.textContent = word;
    historyWordTranslation.textContent = shortTranslation;
    historyListWrapper.innerHTML = `
        <div style="display: flex; justify-content: center; padding: 2rem;">
            <div class="spinner"></div>
        </div>
    `;
    historyModal.style.display = 'flex';

    try {
        const res = await fetch(`/api/words/${id}/history`);
        if (!res.ok) throw new Error("History fetch error");
        const logs = await res.json();
        
        renderHistoryLogs(logs);
    } catch (err) {
        console.error(err);
        historyListWrapper.innerHTML = `
            <div style="text-align: center; color: var(--danger); padding: var(--sp-3);">
                Không thể tải lịch sử ôn tập.
            </div>
        `;
    }
}

function renderHistoryLogs(logs) {
    if (!logs || logs.length === 0) {
        historyListWrapper.innerHTML = `
            <div style="text-align: center; color: var(--text-secondary); padding: 2rem 1rem;">
                Chưa có lượt ôn tập nào cho từ này.
            </div>
        `;
        return;
    }

    const modeLabels = {
        'flashcard': 'Thẻ ghi nhớ',
        'matching': 'Ghép cặp',
        'fill': 'Điền nghĩa'
    };

    const modeClasses = {
        'flashcard': 'history-mode-flash',
        'matching': 'history-mode-match',
        'fill': 'history-mode-fill'
    };

    let html = '';
    logs.forEach(l => {
        const modeLabel = modeLabels[l.mode] || l.mode;
        const modeClass = modeClasses[l.mode] || 'history-mode-flash';
        
        const delta = l.score_delta;
        const deltaText = delta >= 0 ? `+${delta}` : `${delta}`;
        const deltaClass = delta >= 0 ? 'plus' : 'minus';
        
        const correctIcon = l.is_correct ? '✅ Đúng' : '❌ Sai';
        const ratingText = l.rating ? ` (${l.rating}⭐)` : '';
        
        const formattedTime = formatRelativeTime(l.reviewed_at);

        html += `
            <div class="history-item">
                <div class="history-item-left">
                    <span class="history-mode-badge ${modeClass}">${modeLabel}</span>
                    <span>${correctIcon}${ratingText}</span>
                </div>
                <div style="text-align: right;">
                    <span class="history-delta ${deltaClass}">${deltaText}</span>
                    <div class="history-time">${formattedTime}</div>
                </div>
            </div>
        `;
    });
    
    historyListWrapper.innerHTML = html;
}

function closeHistoryModal() {
    historyModal.style.display = 'none';
}

// Global modal background click to close
window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
    }
});

// Reset filters button visibility helper
function updateResetButtonVisibility() {
    const hasActiveFilters = state.selectedStatuses.length > 0 || state.selectedTimeFilters.length > 0 || state.selectedPerfFilters.length > 0;
    const resetBtn = document.getElementById('btn-reset-filters');
    if (resetBtn) {
        resetBtn.style.display = hasActiveFilters ? 'flex' : 'none';
    }
}

// Dynamic filter loading
async function loadFilters() {
    try {
        const res = await fetch('/api/filters/list');
        const data = await res.json();
        
        const statusLabel = {
            'new': 'Từ mới',
            'learning': 'Đang học',
            'learned': 'Đã thuộc'
        };
        
        // Render status section (as checkboxes)
        const statusSection = document.getElementById('status-filter-section');
        if (statusSection) {
            statusSection.innerHTML = `
                <div class="filter-section-title">Trạng thái</div>
                <div class="filter-group">
                    ${['new','learning','learned'].map(s => `
                        <label class="filter-option ${state.selectedStatuses.includes(s) ? 'active' : ''}">
                            <input type="checkbox" name="status-filter" value="${s}" ${state.selectedStatuses.includes(s) ? 'checked' : ''}>
                            <span>${statusLabel[s]}</span>
                            <span class="filter-count" id="count-${s}">0</span>
                        </label>
                    `).join('')}
                </div>
            `;
        }
        
        // Render custom filter sections grouped (as checkboxes, omitting combo and smart)
        const quickWrapper = document.getElementById('quick-filter-sections-wrapper');
        if (quickWrapper) {
            let html = '';
            
            data.groups.forEach(g => {
                if (g.id === 'combo' || g.id === 'smart') return; // skip combo and smart groups
                html += `
                    <div class="filter-section">
                        <div class="filter-section-title">${g.label}</div>
                        <div class="filter-group" style="margin-bottom: var(--sp-4);">
                            ${g.filters.map(f => {
                                const isPool = f.pool_mode ? 'pool-mode' : '';
                                const isChecked = (g.id === 'time' ? state.selectedTimeFilters : state.selectedPerfFilters).includes(f.id);
                                const activeClass = isChecked ? 'active' : '';
                                const checkedAttr = isChecked ? 'checked' : '';
                                const poolSuffix = f.pool_mode ? ' <small style="opacity:0.6;">(pool)</small>' : '';
                                return `
                                    <label class="filter-option ${isPool} ${activeClass}" title="${f.description || ''}">
                                        <input type="checkbox" name="quick-filter" value="${f.id}" data-group="${g.id}" ${checkedAttr}>
                                        <span>${f.label}${poolSuffix}</span>
                                    </label>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            });
            quickWrapper.innerHTML = html;
        }
        
        // Attach status filter checkbox change listeners
        document.querySelectorAll('input[name="status-filter"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const val = e.target.value;
                if (e.target.checked) {
                    if (!state.selectedStatuses.includes(val)) {
                        state.selectedStatuses.push(val);
                    }
                    e.target.closest('.filter-option').classList.add('active');
                } else {
                    state.selectedStatuses = state.selectedStatuses.filter(s => s !== val);
                    e.target.closest('.filter-option').classList.remove('active');
                }
                updateResetButtonVisibility();
                state.page = 1;
                fetchWords();
            });
        });
        
        // Attach quick filter checkbox change listeners
        document.querySelectorAll('input[name="quick-filter"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const val = e.target.value;
                const grp = e.target.getAttribute('data-group');
                if (grp === 'time') {
                    if (e.target.checked) {
                        if (!state.selectedTimeFilters.includes(val)) {
                            state.selectedTimeFilters.push(val);
                        }
                        e.target.closest('.filter-option').classList.add('active');
                    } else {
                        state.selectedTimeFilters = state.selectedTimeFilters.filter(f => f !== val);
                        e.target.closest('.filter-option').classList.remove('active');
                    }
                } else if (grp === 'performance') {
                    if (e.target.checked) {
                        if (!state.selectedPerfFilters.includes(val)) {
                            state.selectedPerfFilters.push(val);
                        }
                        e.target.closest('.filter-option').classList.add('active');
                    } else {
                        state.selectedPerfFilters = state.selectedPerfFilters.filter(f => f !== val);
                        e.target.closest('.filter-option').classList.remove('active');
                    }
                }
                updateResetButtonVisibility();
                state.page = 1;
                fetchWords();
            });
        });

        // Attach Reset filters button click listener
        const resetBtn = document.getElementById('btn-reset-filters');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                state.selectedStatuses = [];
                state.selectedTimeFilters = [];
                state.selectedPerfFilters = [];
                
                document.querySelectorAll('input[name="status-filter"]').forEach(cb => {
                    cb.checked = false;
                    cb.closest('.filter-option').classList.remove('active');
                });
                document.querySelectorAll('input[name="quick-filter"]').forEach(cb => {
                    cb.checked = false;
                    cb.closest('.filter-option').classList.remove('active');
                });
                
                updateResetButtonVisibility();
                state.page = 1;
                fetchWords();
            });
        }
        
        // Initial totals fetch
        updateStatusCounts();
    } catch (err) {
        console.error("Error loading filters:", err);
    }
}

// Initialization
window.addEventListener('DOMContentLoaded', async () => {
    const params = new URLSearchParams(window.location.search);
    const urlQ = params.get('q');
    if (urlQ) {
        state.query = urlQ;
        if (searchInput) searchInput.value = urlQ;
    }
    await loadFilters();
    fetchWords();
});

// ═══ WORD DETAIL MODAL & ANALYTICS BREAKDOWN ═══
async function openDetailModal(id) {
    try {
        const res = await fetch(`/api/words/${id}`);
        if (!res.ok) throw new Error("Failed to fetch word details");
        const data = await res.json();
        const word = data.word;
        
        document.getElementById('detail-word-spelling').textContent = word.word;
        document.getElementById('detail-word-phonetic').textContent = word.phonetic || '';
        document.getElementById('detail-word-status-badge').textContent = getStatusLabel(word.status);
        document.getElementById('detail-word-status-badge').className = `status-badge badge badge-${word.status}`;
        document.getElementById('detail-word-score').textContent = `${word.knowledge_score || 0} ⭐`;
        
        const splitScoresEl = document.getElementById('detail-word-split-scores');
        if (splitScoresEl) {
            splitScoresEl.textContent = `En-Vi: ${word.en_vi_score || 0} | Vi-En: ${word.vi_en_score || 0}`;
        }
        
        const dateAddedEl = document.getElementById('detail-word-date-added');
        if (dateAddedEl) {
            dateAddedEl.querySelector('span').textContent = `Ngày thêm: ${word.date_added || 'Chưa rõ'}`;
        }
        
        // Populate translation
        const translationContainer = document.getElementById('detail-word-translation');
        if (translationContainer) {
            if (word.pos_entries && word.pos_entries.length > 0) {
                translationContainer.innerHTML = word.pos_entries.map(e => `
                    <div class="pos-entry" style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center;">
                        <span class="badge badge-pos badge-${e.pos || 'phrase'}" style="background: var(--primary-light); color: var(--primary); padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.75rem;">${e.pos || 'phrase'}</span>
                        <span class="meaning-text">${e.meaning}</span>
                    </div>
                `).join('');
            } else {
                translationContainer.innerHTML = `<p class="meaning-text" style="margin: 0;">${word.translation}</p>`;
            }
        }
        
        // Populate example
        const exampleContainer = document.getElementById('detail-word-example');
        if (exampleContainer) {
            exampleContainer.textContent = word.example || 'Chưa có ví dụ câu.';
        }
        
        // Set data-word attributes for TTS in details modal
        const ttsBtn = document.getElementById('detail-btn-tts');
        const ttsBtnSlow = document.getElementById('detail-btn-tts-slow');
        if (ttsBtn) ttsBtn.setAttribute('data-word', word.word);
        if (ttsBtnSlow) ttsBtnSlow.setAttribute('data-word', word.word);
        
        // Populate analytics table
        const tbody = document.getElementById('detail-analytics-tbody');
        tbody.innerHTML = '';
        
        const modes = [
            { key: 'flashcard_en_vi', name: 'Flashcard (En ➔ Vi)' },
            { key: 'flashcard_vi_en', name: 'Flashcard (Vi ➔ En)' },
            { key: 'mcq_en_vi', name: 'Trắc nghiệm (En ➔ Vi)' },
            { key: 'mcq_vi_en', name: 'Trắc nghiệm (Vi ➔ En)' },
            { key: 'matching', name: 'Nối từ (En ➔ Vi)' },
            { key: 'fill', name: 'Điền nghĩa (Vi ➔ En)' },
            { key: 'total', name: 'Tổng cộng' }
        ];
        
        modes.forEach(m => {
            const seen = word[`${m.key}_seen`] || 0;
            const correct = word[`${m.key}_correct`] || 0;
            const wrong = word[`${m.key}_wrong`] || 0;
            const accuracy = seen > 0 ? Math.round((correct / seen) * 100) : 0;
            
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid var(--border)';
            tr.innerHTML = `
                <td style="padding: 10px 12px; font-weight: ${m.key === 'total' ? '700' : 'normal'};">${m.name}</td>
                <td style="padding: 10px 12px; text-align: center;">${seen}</td>
                <td style="padding: 10px 12px; text-align: center; color: var(--success); font-weight: bold;">${correct}</td>
                <td style="padding: 10px 12px; text-align: center; color: var(--danger); font-weight: bold;">${wrong}</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: bold;">${accuracy}%</td>
            `;
            tbody.appendChild(tr);
        });
        
        // Save current editing id on edit button
        const editBtn = document.getElementById('detail-btn-edit-word');
        if (editBtn) {
            editBtn.onclick = () => {
                closeDetailModal();
                openEditModal(word.id, word.word, word.phonetic || '', word.translation, word.example || '');
            };
        }
        
        document.getElementById('detail-modal').style.display = 'flex';
    } catch (err) {
        console.error("Error loading word details:", err);
        showToast("Lỗi tải chi tiết từ vựng!", "error");
    }
}

function closeDetailModal() {
    document.getElementById('detail-modal').style.display = 'none';
}

function getStatusLabel(status) {
    switch (status) {
        case 'new': return 'Mới';
        case 'learning': return 'Học';
        case 'learned': return 'Thuộc';
        case 'mastered': return 'Thuộc';
        default: return status;
    }
}
