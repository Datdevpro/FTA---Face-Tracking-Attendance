<div align="center">
  <img src="frontend/icon2.png" width="128" alt="FTA Logo">

  <h1>FTA - Face Tracking Attendance System</h1>

  <h3>Fast and Accuracy face tracking system </h3>

  <!-- <p><em>Chấm công thông minh, nhận diện nhanh, vận hành trực quan.</em></p> -->

  <p>
    <img src="https://img.shields.io/badge/release-v1.0.0-2563eb?style=flat-square" alt="Release">
    <img src="https://img.shields.io/badge/Python-3.11-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.11">
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/InsightFace-0.7.3-f97316?style=flat-square" alt="InsightFace">
    <img src="https://img.shields.io/badge/inference-CPU%20%7C%20GPU-7c3aed?style=flat-square" alt="CPU or GPU inference">
  </p>

  <p>
    <a href="#gioi-thieu">Giới thiệu</a> ·
    <a href="#tinh-nang">Tính năng</a> ·
    <a href="#cai-dat">Cài đặt</a> ·
    <a href="#cau-hinh">Cấu hình</a> ·
    <a href="#kien-truc">Kiến trúc</a> ·
    <a href="#cong-nghe">Công nghệ</a>
  </p>
</div>

---

<a id="gioi-thieu"></a>

## About

**FTA** là hệ thống chấm công nhân sự bằng nhận diện khuôn mặt dành cho doanh
nghiệp nhỏ và vừa. Hệ thống sử dụng các mô hình AI tiên tiến để nhận diện faceID của nhân viên một cách nhanh chóng và tiện lợi

FTA cung cấp giao diện quản trị trên trình duyệt, camera trực tiếp qua WebSocket, 
khả năng chống giả mạo, quản lý nhân viên, theo dõi chấm công và xuất báo cáo.

<a id="tinh-nang"></a>

## Functionality

- **Nhận diện khuôn mặt real-time** bằng InsightFace SCRFD và ArcFace.
- **Không cần retrain** khi thêm dữ liệu nhân viên; embedding mới được đưa vào FAISS.
- **Chống giả mạo khuôn mặt** bằng model anti-spoofing ONNX.
- **Chấm công tự động** theo khung giờ check-in và check-out của doanh nghiệp.
- **Camera trực tiếp** với bounding box và kết quả nhận diện qua WebSocket.
- **Welcome screen và lời chào** khi nhận diện được nhân viên.
- **Quản lý nhân viên** gồm hồ sơ, phòng ban và đăng ký khuôn mặt.
- **Báo cáo chấm công** và xuất dữ liệu Excel.
- **JWT authentication** và tài liệu API tương tác bằng Swagger UI.
- **Inference tùy chọn** bằng CPU hoặc NVIDIA GPU.

<a id="cai-dat"></a>

## Getting-started

### Prerequisites

- Windows 10 hoặc Windows 11 64-bit.
- Python 3.11 64-bit.
- RAM tối thiểu 4 GB, khuyến nghị 8 GB trở lên.
- Webcam USB hoặc IP Camera sử dụng RTSP.
- Kết nối Internet trong lần cài đầu để tải dependency và model `buffalo_l`.

### One line setup

```text
https://github.com/Datdevpro/FTA---Face-Tracking-Attendance.git
setup-fta.bat
```

Script sẽ tự động tạo `venv`, tạo `.env`, sinh JWT secret, cài dependency, khởi
tạo SQLite và chuẩn bị model nhận diện. Cấu hình ban đầu sử dụng CPU để chạy
được trên máy không có NVIDIA CUDA.

Khi setup hoàn tất, run file:

```text
start-fta.bat
```

Sau đó truy cập [http://localhost:8000](http://localhost:8000).

### By-hand Installation

```powershell
git clone https://github.com/Datdevpro/FTA---Face-Tracking-Attendance.git FTA
cd FTA

py -3.11 -m venv name_of_venv
.\venv\Scripts\Activate.ps1

Copy-Item .env.example .env
pip install --upgrade pip setuptools wheel
pip install .\model_wheel\insightface-0.7.3-cp311-cp311-win_amd64.whl
pip install -r requirements.txt

python -m scripts.init_db
.\start-fta.ps1
```

### API Services

| Dịch vụ | Địa chỉ |
|:---|:---|
| Dashboard | [http://localhost:8000](http://localhost:8000) |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/api/health](http://localhost:8000/api/health) |

Tài khoản mặc định: `admin` / `admin123`. Hãy đổi mật khẩu trước khi đưa hệ
thống cho người dùng thật.

<a id="cau-hinh"></a>

## Configurations

Change configurations in .env file with

```env
## if you wanna inference using cpu
FACE_ONNX_PROVIDER=cpu
ANTI_SPOOFING_PROVIDER=cpu
## if you wanna inference using gpu
FACE_ONNX_PROVIDER=gpu
ANTI_SPOOFING_PROVIDER=gpu
```


<a id="kien-truc"></a>

## Codebase structures

```text
FTA/
├── app/
│   ├── api/                    # REST API routes
│   ├── core/                   # Database, security, dependencies
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # AI engine and business logic
│   ├── websocket/              # Real-time camera stream
│   ├── config.py               # Environment configuration
│   └── main.py                 # FastAPI entry point
├── frontend/                   # HTML, CSS, JavaScript and assets
├── data/                       # Local database, models and generated data
├── docs/                       # Technical documentation
├── model_wheel/                # InsightFace wheel for Python 3.11 Windows
├── scripts/                    # Setup and maintenance scripts
├── tests/                      # Automated tests
├── setup-fta.bat               # One-click initial setup
└── start-fta.bat               # Application launcher
```

<a id="cong-nghe"></a>

## Technology

| Thành phần | Công nghệ |
|:---|:---|
| Backend | FastAPI, Uvicorn, Pydantic |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Real-time | WebSocket |
| Face Detection | InsightFace SCRFD |
| Face Recognition | ArcFace `buffalo_l`, embedding 512 chiều |
| Vector Search | FAISS `IndexFlatIP` |
| Anti-spoofing | ONNX Runtime |
| Database | SQLite cho local, PostgreSQL-ready |
| Authentication | OAuth2 Password Flow, JWT |

## Note for future dev

SQLite phù hợp cho chạy thử trên một máy. Trước khi triển khai production, cần
đổi secret mặc định, tắt debug, cấu hình HTTPS, backup dữ liệu và cân nhắc chuyển
sang PostgreSQL. Hướng dẫn PostgreSQL nằm tại
[`docs/postgresql-setup.md`](docs/postgresql-setup.md).
