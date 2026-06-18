# FTA - Face Time Attendance System

Hệ thống chấm công nhân sự bằng nhận diện khuôn mặt (Face Recognition) dành cho doanh nghiệp nhỏ (~50 nhân viên).

## 🚀 Tính năng

- **Nhận diện khuôn mặt real-time** bằng InsightFace (ArcFace) + FAISS, Không cần retrain khi có data mới
- **Chấm công tự động** khi nhận diện được nhân viên qua camera
- **Chống giả mạo** (Anti-spoofing) - phát hiện ảnh in, màn hình
- **Dashboard trực quan** với thống kê real-time
- **Quản lý nhân viên** - CRUD, phòng ban, đăng ký khuôn mặt
- **Báo cáo & xuất Excel** - Báo cáo tháng, tỷ lệ chuyên cần
- **WebSocket streaming** - Camera feed trực tiếp với face overlay

## 📋 Yêu cầu hệ thống

- Python 3.10+
- Webcam (USB) hoặc IP Camera (RTSP)
- RAM: tối thiểu 4GB (khuyến nghị 8GB)
- CPU: Intel i5 trở lên (có GPU NVIDIA thì càng tốt)

## ⚡ Cài đặt nhanh

```bash
# 1. Clone & tạo virtual environment
clone https://github.com/Datdevpro/FTA---Face-Tracking-Attendance.git
python -m venv {your_venv_name}
.\your_venv_name\Scripts\activate

# 2. Cài đặt dependencies
pip install -r requirements.txt

# 3. Khởi tạo database
python -m scripts.init_db

# 4. Chạy server
.\start-fta.ps1
# hoặc double-click start-fta.bat trên Windows

# Chạy thủ công nếu cần
python -m app.main
# hoặc
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🌐 Truy cập

- **Dashboard**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Login mặc định**: `admin` / `admin123`

## 📁 Cấu trúc dự án

```
FTA/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Configuration
│   ├── api/                    # API routes
│   ├── core/                   # DB, security, dependencies
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # Business logic & AI engine
│   └── websocket/              # Real-time camera stream
├── frontend/                   # Web dashboard (HTML/CSS/JS)
├── data/                       # Face images, FAISS index, models
├── scripts/                    # Utility scripts
└── requirements.txt
```

## 🔧 Tech Stack

| Component | Technology |
|:---|:---|
| Backend | FastAPI + Uvicorn |
| Face Detection | InsightFace (SCRFD) |
| Face Recognition | ArcFace (buffalo_l) |
| Vector Search | FAISS (IndexFlatIP) |
| Database | SQLite / PostgreSQL |
| Frontend | HTML5 + CSS3 + Vanilla JS |
| Real-time | WebSocket |

## 📊 Performance

- Face Detection: ~30-40ms/frame (CPU)
- Face Embedding: ~20-30ms/face (CPU) - 512 embedding vector
- FAISS Search (50 users): <1ms
- **Total pipeline: ~60-80ms/face** (10+ FPS real-time)
