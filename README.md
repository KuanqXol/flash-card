# FlashVocab

FlashVocab là ứng dụng học tiếng Anh cá nhân hóa chạy trên môi trường local. Ứng dụng hỗ trợ học từ vựng theo phương pháp Spaced Repetition (Lặp lại ngắt quãng) kết hợp luyện tập ngữ pháp trắc nghiệm TOEIC Part 5.

## Tính năng chính

*   **Flashcard**: Học từ vựng, phiên âm IPA, ví dụ và phát âm tự động (TTS) với 2 tốc độ.
*   **Trắc nghiệm (MCQ)**: Ôn tập từ vựng với đáp án nhiễu tự động sinh từ kho dữ liệu.
*   **Điền nghĩa (Fill)**: Gõ từ tiếng Anh dựa trên gợi ý nghĩa tiếng Việt và ký tự đầu.
*   **Nối từ (Matching)**: Ghép cặp từ - nghĩa trong thời gian giới hạn bằng thao tác kéo thả.
*   **Luyện TOEIC Part 5**:
    *   Học theo chủ đề ngữ pháp chi tiết (các thì tiếng Anh, giới từ, liên từ...).
    *   Hiển thị dịch nghĩa và giải thích chi tiết ngay sau khi chọn đáp án.
*   **Quản lý từ vựng**: Bộ lọc nâng cao (thời gian thêm, hiệu suất học, thuật toán ưu tiên thông minh) giúp lọc danh sách từ vựng. Hỗ trợ import/export CSV.
*   **Dashboard**: Thống kê tổng quan tiến độ học tập, biểu đồ hoạt động 7 ngày gần nhất, và khối phân tích điểm mạnh/yếu đối với từng chủ đề ngữ pháp TOEIC.

## Công nghệ sử dụng

*   **Backend**: Python / Flask (REST API và rendering)
*   **Frontend**: HTML, CSS, Vanilla JavaScript (không cần build step)
*   **Cơ sở dữ liệu**: SQLite
*   **Phát âm**: Google Text-to-Speech (gTTS) với cache local tự động dọn dẹp
*   **Xử lý dữ liệu**: Pandas và OpenPyXL (đọc Excel/CSV)

## Hướng dẫn cài đặt và chạy

1.  **Cài đặt môi trường:**
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # macOS/Linux:
    source .venv/bin/activate
    ```

2.  **Cài đặt dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Chạy ứng dụng:**
    ```bash
    python app.py
    ```
    Mở trình duyệt tại địa chỉ: `http://localhost:5000`

## Định dạng file dữ liệu

### File từ vựng (CSV)

*   **Word**: Từ / cụm từ tiếng Anh (ví dụ: `representative`).
*   **Phonetic**: Phiên âm IPA (ví dụ: `/ˌreprɪˈzentətɪv/`, có thể để trống hoặc ghi `--`).
*   **Translation**: Nghĩa tiếng Việt, đi kèm phân loại từ loại (n., v., adj., adv., prep., conj., pron.), phân cách bằng dấu `;` (ví dụ: `n. người đại diện; adj. đại diện`).
*   **Date**: Ngày thêm từ (ví dụ: `2026-06-22`).

### File câu hỏi TOEIC (Excel - .xlsx)

*   **Chu De**: Chủ đề ngữ pháp hoặc từ vựng của câu hỏi (ví dụ: `Hiện tại đơn`, `Giới từ`).
*   **Cau Hoi**: Nội dung câu hỏi trắc nghiệm tiếng Anh (chứa dấu gạch trống `___`).
*   **Dap An A / B / C / D**: Các phương án lựa chọn trắc nghiệm.
*   **Dap An Dung**: Chữ cái in hoa đáp án chính xác (`A`, `B`, `C` hoặc `D`).
*   **Giai Thich**: Lời giải thích tại sao chọn đáp án đó.
*   **Dich Nghia**: Bản dịch nghĩa câu hỏi và các phương án lựa chọn.