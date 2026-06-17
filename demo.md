# 📚 FlashVocab — Vibe Coding Checklist

> App học từ vựng tiếng Anh cá nhân, chạy local trên Windows.
> Dùng file này như "spec" để feed vào Cursor / Claude / Copilot từng bước.

---

## 📊 Cấu trúc CSV đầu vào

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `Word` | Từ / cụm từ tiếng Anh | `representative`, `the nasal spray` |
| `Phonetic` | Phiên âm IPA (có thể là `--`) | `/ˌreprɪˈzentətɪv/` |
| `Translation` | Nghĩa tiếng Việt, có prefix từ loại, phân cách `;` | `n. người đại diện; adj. đại diện; web. tiêu biểu` |
| `Date` | Ngày thêm từ | `2026-06-17` |

---

## 🏗️ Tech Stack

| Thành phần | Công nghệ | Lý do |
|---|---|---|
| Backend | Python 3.10+ + Flask | Đơn giản, chạy local dễ |
| Frontend | HTML5 + CSS3 + Vanilla JS | Không cần build step, dễ iterate |
| Database | SQLite (thư viện `sqlite3` có sẵn) | Zero-config, 1 file `.db` |
| Data import | `pandas` | Đọc CSV nhanh, xử lý encoding tốt |
| Chạy app | `python app.py` → mở `http://localhost:5000` | |

```bash
# Cài đặt duy nhất cần thiết:
pip install flask pandas
```

---

## 📁 Cấu trúc thư mục

```
flashcard-app/
├── app.py                  # Flask backend — tất cả API routes
├── database.py             # SQLite init + helper functions
├── scoring.py              # Logic tính điểm & chuyển trạng thái
├── import_csv.py           # Script import CSV vào DB
│
├── data/
│   └── words.csv           # File CSV gốc (copy vào đây)
│
├── templates/
│   ├── base.html           # Layout chung (nav + head)
│   ├── dashboard.html      # Trang chủ & thống kê
│   ├── flashcard.html      # Chế độ flash card
│   ├── matching.html       # Chế độ nối từ
│   └── fill.html           # Chế độ điền nghĩa
│
├── static/
│   ├── css/style.css       # CSS toàn bộ app
│   └── js/
│       ├── flashcard.js
│       ├── matching.js
│       └── fill.js
│
├── flashcards.db           # SQLite DB (tự tạo khi chạy lần đầu)
├── requirements.txt
└── README.md
```

---

## 🎯 Luật hệ thống (đọc kỹ trước khi code)

### Phân loại từ & điều kiện chuyển trạng thái

| Trạng thái | Mô tả | Màu |
|---|---|---|
| 🆕 `new` (Từ mới) | Mặc định khi import | Xám |
| 📚 `learning` (Đang học) | Đã được rate **5 sao ít nhất 1 lần** | Vàng/Cam |
| ✅ `learned` (Đã thuộc) | User bấm nút "Đã thuộc" thủ công | Xanh lá |

**Chuyển trạng thái:**
- `new` → `learning`: **Tự động** khi flashcard được rate 5 ≥ 1 lần
- `learning` → `learned`: **Thủ công** — user phải bấm nút "Đã thuộc"
- `learned` → `learning`: **Thủ công** — user bấm nút "Ôn lại" (reset về learning)
- Điểm số KHÔNG ảnh hưởng trực tiếp đến trạng thái (chỉ rate 5 mới trigger)

### Hệ thống điểm (luỹ kế)

| Hành động | Điểm thay đổi |
|---|---|
| Flashcard rate 1 sao | +1 |
| Flashcard rate 2 sao | +2 |
| Flashcard rate 3 sao | +3 |
| Flashcard rate 4 sao | +4 |
| Flashcard rate 5 sao ⭐ | +5 (+ trigger `has_been_rated_five = 1`) |
| Nối từ đúng ✓ | **+3** |
| Nối từ sai ✗ | **-2** |
| Điền nghĩa — tự đánh giá Đúng ✓ | **+5** (cao nhất) |
| Điền nghĩa — tự đánh giá Sai ✗ | **-3** (thấp nhất) |

**Rules bổ sung:**
- Điểm không bao giờ âm: `total_score = MAX(0, total_score + delta)`
- Mỗi lần ôn (kể cả sai) đều tăng `review_count += 1`
- Luôn cập nhật `last_reviewed` = current datetime

---

## ✅ Checklist Tính Năng

### Phase 1 — Setup & Database
- [ ] Tạo cấu trúc thư mục
- [ ] Viết `database.py` với schema SQLite và helper functions
- [ ] Viết `import_csv.py` — đọc CSV, parse short_translation, upsert vào DB
- [ ] Viết `app.py` Flask cơ bản (route `/` → dashboard)
- [ ] Test: chạy `python import_csv.py data/words.csv` → thấy "60 từ đã import"
- [ ] Test: `python app.py` → mở localhost:5000 không lỗi

### Phase 2 — Flash Card Mode
- [ ] API `GET /api/flashcard/next?status=all` — lấy từ ngẫu nhiên
- [ ] API `POST /api/flashcard/rate` — nhận rating 1-5, cập nhật điểm + status
- [ ] API `POST /api/word/mark-learned` — đánh dấu đã thuộc thủ công
- [ ] UI: card flip animation 3D (mặt trước: từ + phonetic, mặt sau: nghĩa)
- [ ] UI: rating stars 1-5 (hiện sau khi lật thẻ)
- [ ] UI: filter chọn nhóm từ (Tất cả / Từ mới / Đang học / Đã thuộc)
- [ ] UI: toast notification "+5 điểm!" / "Chuyển sang Đang học!"
- [ ] UI: nút "✅ Đã thuộc" luôn hiển thị
- [ ] Keyboard: Space = lật thẻ, 1-5 = rating

### Phase 3 — Matching Game (Nối Từ)
- [ ] API `GET /api/matching/words?n=6&status=all`
- [ ] API `POST /api/matching/result` — nhận list {word_id, is_correct}
- [ ] UI: 2 cột (Tiếng Anh trái, Tiếng Việt phải xáo trộn)
- [ ] Logic: click chọn, click lần 2 để ghép cặp
- [ ] Animation: đúng = xanh, sai = đỏ + shake
- [ ] Màn hình kết quả: số đúng/tổng + điểm nhận được
- [ ] Nút "Chơi lại" (load 6 từ mới ngẫu nhiên)

### Phase 4 — Fill-in-the-blank (Điền Nghĩa)
- [ ] API `GET /api/fill/next?mode=en_to_vi&status=all`
- [ ] API `POST /api/fill/evaluate` — nhận {word_id, is_correct}
- [ ] UI: input text để điền, nút "Kiểm tra"
- [ ] UI: sau submit → hiện đáp án đầy đủ
- [ ] UI: 2 nút lớn "✅ Tôi đúng (+5)" và "❌ Tôi sai (-3)"
- [ ] Chế độ: EN→VI và VI→EN (toggle)
- [ ] Keyboard: Enter = submit, Y = đúng, N = sai

### Phase 5 — Dashboard
- [ ] API `GET /api/stats`
- [ ] API `GET /api/words/list?status=all&sort=score_desc`
- [ ] UI: 4 stat cards (Từ mới / Đang học / Đã thuộc / Ôn hôm nay)
- [ ] UI: progress bar 3 màu (new | learning | learned)
- [ ] UI: quick action buttons → các chế độ học
- [ ] UI: word list với filter tabs và sort dropdown
- [ ] UI: nút "Đã thuộc" inline trên từng row
- [ ] UI: click vào từ → expand xem full translation

### Phase 6 — UI Polish
- [ ] Navigation (sidebar desktop / bottom bar mobile)
- [ ] Toast notification system toàn cục
- [ ] Loading skeletons khi đang fetch
- [ ] Empty states (khi không có từ)
- [ ] Keyboard shortcuts global (D/F/M/T/Esc)
- [ ] Responsive (desktop + mobile)
- [ ] Import CSV từ UI (upload file)
- [ ] Export progress ra CSV

---