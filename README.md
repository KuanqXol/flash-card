# 📚 FlashVocab

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