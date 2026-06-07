# BurgerPrintsAgent - AI Fulfillment Advisor for POD Sellers

Live Demo: [http://bp1.zorinlab.space](http://bp1.zorinlab.space)   

BurgerPrintsAgent là một trợ lý ảo AI thông minh được phát triển để hỗ trợ các seller bán hàng Print-On-Demand (POD) trên nền tảng BurgerPrints. Ứng dụng giúp tìm kiếm, so sánh sản phẩm tối ưu, đối chiếu chất lượng và giá cả giữa các factory/partner, theo dõi tồn kho và chuẩn bị đơn hàng tự động.

---

## 🎯 Mục Tiêu Giải Quyết
1. **Tối ưu hóa Fulfillment**: Phân tích dữ liệu vận hành thực tế từ các factory để tư vấn cho seller lựa chọn xưởng in có base cost rẻ nhất hoặc thời gian sản xuất nhanh nhất.
2. **Khắc phục Out-of-Stock**: Tự động đối chiếu trạng thái tồn kho thực tế qua BurgerPrints API, đề xuất sản phẩm thay thế phù hợp khi sản phẩm chính hết hàng.
3. **Trải nghiệm Chat Tốc độ Cao**: Hỗ trợ cơ chế Server-Sent Events (SSE) streaming thực tế để giảm thiểu tối đa Time-to-First-Token (TTFT), mang lại cảm giác phản hồi tức thì giống như ChatGPT.
4. **Vận hành đơn hàng (Order Support)**: Cho phép tạo, xem và thanh toán đơn hàng trực tiếp trên giao diện.

---

## 📁 Cấu Trúc Dự Án
Dự án được cấu trúc dưới dạng ứng dụng Django REST Framework phục vụ SPA (Single Page Application) React được compile sẵn.

```text
├── burgerprints_agent/    # Django Project Settings & Routing
├── agent/                 # Django App chính
│   ├── graph/             # Core logic LangGraph, workflows, nodes
│   ├── services/          # Các integration với BurgerPrints API & Cache
│   ├── zorin/             # Module xử lý NLP, Intent Analysis, Object Store
│   ├── views.py           # REST API Endpoints & SSE Streaming Controller
│   └── api_urls.py        # Các URL API (Chat, Orders, Cache,...)
├── templates/             # Thư mục template HTML của Django
│   └── agent/
│       ├── chat.html      # Điểm neo load SPA React đã build hoàn chỉnh
│       └── graph.html     # Giao diện trực quan hóa Graph Nodes
├── static/                # Static assets của Django (bao gồm JS/CSS build của React)
│   ├── assets/            # SPA React bundle static files
│   └── css/               # Tailwind & styles bổ sung
├── frontend/              # Source code phát triển React (Vite + React 19) - ĐÃ IGNORE KHI COMMIT
│   ├── src/               # React components, state quản lý chat & orders
│   └── vite.config.js     # Vite configuration
├── deploy.bat             # Script tự động thiết lập & chạy trên Windows
├── deploy.sh              # Script tự động thiết lập & chạy trên Linux/macOS
├── requirements.txt       # Danh sách thư viện Python
├── db.sqlite3             # Database cục bộ lưu session & lịch sử hội thoại
└── README.md              # Tài liệu hướng dẫn này
```

---

## 🛠️ Hướng Dẫn Cài Đặt (Cho BTC Hackathon)

Bạn có thể chạy dự án thông qua **Script tự động** hoặc **Cài đặt thủ công**.

### Cách 1: Sử Dụng Script Tự Động Hóa (Khuyên Dùng)

#### Trên Windows (cmd / powershell):
Chỉ cần chạy file `deploy.bat` ở thư mục gốc:
```cmd
deploy.bat
```
*Script sẽ tự động kiểm tra Python, tạo Virtual Environment (`venv`), cài đặt thư viện, tạo file `.env` mẫu, chạy database migrations, build React SPA (nếu có Node.js), copy static files và khởi động server Django tại port 8000.*

#### Trên Linux / macOS (terminal):
Chạy file `deploy.sh` từ thư mục gốc:
```bash
chmod +x deploy.sh
./deploy.sh
```

---

### Cách 2: Thiết Lập Thủ Công Từng Bước

#### Bước 1: Clone dự án và tạo môi trường ảo Python
```bash
# Clone repository
git clone https://github.com/huybuivibecode/Crafted-with-passion-code-B-i-Quang-Huy-2026.git
cd Crafted-with-passion-code-B-i-Quang-Huy-2026

# Tạo môi trường python venv
python -m venv venv

# Kích hoạt venv
# Trên Windows:
venv\Scripts\activate
# Trên Linux/macOS:
source venv/bin/activate

# Nâng cấp pip và cài đặt thư viện
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 2: Thiết lập File Biến Môi Trường `.env`
Tạo file `.env` tại thư mục gốc của dự án với nội dung mẫu sau:
```env
DJANGO_SECRET_KEY=django-insecure-burgerprints-agent-dev-key-change-in-prod
DEBUG=True
BURGER_PRINTS_API_KEY=your_burgerprints_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
CATALOG_CACHE_TTL=300
```
*(Hãy thay `your_gemini_api_key_here` và `your_burgerprints_api_key_here` bằng Key thực tế của bạn).*

#### Bước 3: Chạy database migrations
```bash
python manage.py migrate
```

#### Bước 4: Khởi chạy ứng dụng Django
```bash
python manage.py runserver 0.0.0.0:8000
```
Truy cập vào ứng dụng tại địa chỉ: [http://localhost:8000](http://localhost:8000)

---

## ⚙️ Các Biến Môi Trường Cấu Hình

| Biến | Ý nghĩa | Mặc định |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | Secret Key của ứng dụng Django | `django-insecure-...` |
| `DEBUG` | Chế độ debug của Django | `True` |
| `BURGER_PRINTS_API_KEY` | API Key kết nối với hệ thống BurgerPrints | *Yêu cầu* |
| `GEMINI_API_KEY` | API Key kết nối với Google Gemini AI | *Yêu cầu* |
| `GEMINI_MODEL` | Model LLM sử dụng trong Zorin Agent | `gemini-2.0-flash` |
| `CATALOG_CACHE_TTL` | Thời gian sống của cache sản phẩm (giây) | `300` (5 phút) |

---

## ⚡ Các Tính Năng Kỹ Thuật Nổi Bật
* **Real-time SSE Streaming**: Server-Sent Events giúp đẩy trực tiếp các token thô được trả về từ Gemini API đến box chat của client mà không qua bộ lọc JSON chặn, tạo cảm giác chat mượt mà, tức thì.
* **Smart Catalog Cache**: Hệ thống lưu cache trong bộ nhớ trong 5 phút đối với danh sách 500 sản phẩm và 2 phút đối với sản phẩm Out-Of-Stock, giảm tải API BurgerPrints và giảm latency tối đa.
* **LangGraph Agent Workflow**: Các bước phân tích ý định (Intent), định tuyến tác vụ (Router), lấy dữ liệu (Data Agent), ra quyết định (Function) và kiểm duyệt (Output Validator) được liên kết dưới dạng đồ thị trạng thái chặt chẽ.
