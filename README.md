# 📚 FlashVocab

Ứng dụng học từ vựng tiếng Anh cá nhân hóa chạy trên local, hỗ trợ nhiều chế độ luyện tập, hệ thống chấm điểm thông minh, và bộ lọc nâng cao.

---

## ✨ Tính năng chính

### 🎴 Flashcard
- Lật thẻ xem nghĩa, phiên âm IPA, ví dụ minh họa.
- Đánh giá bản thân: **Tạm nhớ** / **Chưa thuộc** / **Đã thuộc**.
- Tự động phát âm TTS (tốc độ bình thường & đọc chậm).

### 📝 Trắc nghiệm (MCQ)
- 4 đáp án cho mỗi câu hỏi, tự động sinh đáp án nhiễu từ pool từ vựng.
- Đánh giá ngay lập tức, cộng/trừ điểm theo kết quả.

### ✍️ Điền nghĩa (Fill)
- Gợi ý nghĩa tiếng Việt, người dùng gõ từ tiếng Anh.
- So khớp thông minh, hỗ trợ gợi ý ký tự đầu.

### 🔗 Nối từ (Matching)
- Ghép cặp từ – nghĩa trong thời gian giới hạn.
- Giao diện kéo thả trực quan.

### 📖 Quản lý từ vựng
- Xem tất cả từ vựng với bộ lọc đa dạng (trạng thái, thời gian, hiệu suất).
- Thêm / sửa / xóa từ vựng trực tiếp trên giao diện.
- Xem chi tiết từ: lịch sử ôn tập, thống kê theo bài tập, ngày thêm.
- Import CSV hàng loạt & Export CSV.

### 📊 Dashboard
- Tổng quan thống kê: tổng từ, từ mới, đang học, đã thuộc.
- Biểu đồ tiến trình hàng ngày (heatmap).
- Danh sách từ yếu, từ nguy hiểm, từ hay quên.

### 🔍 Hệ thống bộ lọc nâng cao
- **Multi-select checkbox**: Tick chọn nhiều bộ lọc cùng lúc.
- **Nhóm bộ lọc**:
  - ⏰ **Thời gian**: Thêm hôm nay, thêm tuần này, chưa ôn hôm nay, chưa ôn 3/7 ngày, vừa sai…
  - 📈 **Hiệu suất**: Điểm thấp nhất, accuracy thấp nhất, sai nhiều nhất, chưa ôn lần nào, từ nguy hiểm.
  - 🧠 **Thông minh**: Ưu tiên thông minh (dựa trên thuật toán scoring).
- **Loại trừ tương hỗ**: "Ưu tiên thông minh" tự động tắt khi chọn bộ lọc khác.
- **Đồng bộ trạng thái**: Pills trạng thái ↔ checkbox trong dropdown.

### 🔊 Text-to-Speech (TTS)
- Phát âm từ vựng bằng giọng tiếng Anh tự nhiên (gTTS).
- 2 tốc độ: bình thường & đọc chậm (tùy chỉnh trong Cài đặt).
- Cache audio local tự động, LRU eviction khi vượt 100MB.

### ⚙️ Cài đặt
- Tùy chỉnh tốc độ đọc chậm.
- Chế độ sáng / tối (Dark mode).
- Lưu cài đặt persistent trong database.

---

## 🏗️ Tech Stack

| Thành phần | Công nghệ | Ghi chú |
|---|---|---|
| Backend | Python 3.10+ / Flask | REST API, server-side rendering |
| Frontend | HTML5 + CSS3 + Vanilla JS | Không cần build step |
| Database | SQLite (`sqlite3` built-in) | Zero-config, 1 file `.db` |
| TTS | gTTS (Google Text-to-Speech) | Sinh file `.mp3` cache local |
| Data import | pandas | Đọc CSV, xử lý encoding |

---

## 🚀 Cài đặt & Chạy

```bash
# 1. Clone repo
git clone <repo-url>
cd flash-card

# 2. Tạo virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Chạy ứng dụng
python app.py
```

Mở trình duyệt tại **http://localhost:5000**

> **Lưu ý**: Database `flashcards.db` tự động tạo khi chạy lần đầu. Từ vựng mới import sẽ có điểm mặc định **30**.

---

## 📊 Cấu trúc CSV đầu vào

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `Word` | Từ / cụm từ tiếng Anh | `representative`, `the nasal spray` |
| `Phonetic` | Phiên âm IPA (có thể là `--`) | `/ˌreprɪˈzentətɪv/` |
| `Translation` | Nghĩa tiếng Việt, prefix từ loại, phân cách `;` | `n. người đại diện; adj. đại diện` |
| `Date` | Ngày thêm từ | `2026-06-17` |

---

## 🧮 Hệ thống chấm điểm

### Điểm kiến thức (Knowledge Score)

Mỗi từ có điểm **0 – 100**, quyết định trạng thái:

| Khoảng điểm | Trạng thái | Biểu tượng |
|---|---|---|
| 0 – 29 | Danger (Nguy hiểm) | 🔴 |
| 30 – 49 | New (Từ mới) | 🟡 |
| 50 – 69 | Learning (Đang học) | 🔵 |
| 70 – 89 | Familiar (Quen thuộc) | 🟢 |
| 90 – 100 | Mastered (Đã thuộc) | ⭐ |

### Điểm cộng/trừ theo bài tập

| Bài tập | Đúng | Sai |
|---|---|---|
| Flashcard | +1 | 0 |
| Matching | +2 | −3 |
| MCQ | +3 | −2 |
| Fill (Typing) | +5 | −1 |

> Điểm được tính dựa trên **accuracy tổng hợp** và **tần suất ôn tập**, không chỉ đơn thuần cộng/trừ tuyến tính.

---

## 📁 Cấu trúc thư mục

```
flash-card/
├── app.py                  # Flask backend — tất cả API routes (~50 endpoints)
├── database.py             # SQLite schema, queries, bộ lọc FILTERS
├── scoring.py              # Thuật toán tính điểm V2, spaced repetition logic
├── import_csv.py           # Script import CSV vào DB
├── migrate_v2.py           # Script migration database lên schema V2
├── migrate_scores.py       # Script migration điểm
│
├── templates/
│   ├── base.html           # Layout chung + initStudyHeaderFilters()
│   ├── dashboard.html      # Trang chủ & thống kê tổng quan
│   ├── flashcard.html      # Chế độ flashcard
│   ├── mcq.html            # Chế độ trắc nghiệm
│   ├── fill.html           # Chế độ điền nghĩa
│   ├── matching.html       # Chế độ nối từ
│   └── words.html          # Quản lý tất cả từ vựng
│
├── static/
│   ├── css/style.css       # CSS design system (2000+ dòng)
│   ├── js/
│   │   ├── flashcard.js    # Logic flashcard
│   │   ├── mcq.js          # Logic trắc nghiệm
│   │   ├── fill.js         # Logic điền nghĩa
│   │   ├── matching.js     # Logic nối từ
│   │   ├── words.js        # Logic quản lý từ vựng
│   │   ├── theme.js        # Dark/light mode toggle
│   │   └── tts.js          # Text-to-speech client
│   └── audio/              # Cache file .mp3 TTS (tự sinh)
│
├── data/                   # Thư mục chứa file CSV gốc
├── tests/                  # Unit tests
├── flashcards.db           # SQLite DB (tự tạo khi chạy)
├── requirements.txt        # Dependencies: flask, pandas, gTTS
└── README.md
```