<div align="center">
  <img src="frontend/icon2.png" width="128" alt="FTA Logo">

  <h1>FTA</h1>

  <h3>Face Tracking Attendance System</h3>

  <p><em>Chấm công thông minh, nhận diện nhanh, vận hành trực quan.</em></p>

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

## Giới thiệu

**FTA** là hệ thống chấm công nhân sự bằng nhận diện khuôn mặt dành cho doanh
nghiệp nhỏ và vừa. Hệ thống kết hợp InsightFace, ArcFace và FAISS để phát hiện,
nhận diện và đối chiếu khuôn mặt theo thời gian thực mà không cần huấn luyện lại
mô hình khi có nhân viên mới.

FTA cung cấp giao diện quản trị trên trình duyệt, camera trực tiếp qua WebSocket,
chống giả mạo, quản lý nhân viên, theo dõi chấm công và xuất báo cáo.

<a id="tinh-nang"></a>

## Tính năng

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

## Cài đặt

### Yêu cầu

- Windows 10 hoặc Windows 11 64-bit.
- Python 3.11 64-bit.
- RAM tối thiểu 4 GB, khuyến nghị 8 GB trở lên.
- Webcam USB hoặc IP Camera sử dụng RTSP.
- Kết nối Internet trong lần cài đầu để tải dependency và model `buffalo_l`.

### Cài đặt tự động

Sau khi clone project, double-click:

```text
setup-fta.bat
```

Script sẽ tự động tạo `venv`, tạo `.env`, sinh JWT secret, cài dependency, khởi
tạo SQLite và chuẩn bị model nhận diện. Cấu hình ban đầu sử dụng CPU để chạy
được trên máy không có NVIDIA CUDA.

Khi setup hoàn tất, double-click:

```text
start-fta.bat
```

Sau đó truy cập [http://localhost:8000](http://localhost:8000).

### Cài đặt thủ công

```powershell
git clone https://github.com/Datdevpro/FTA---Face-Tracking-Attendance.git FTA
cd FTA

py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1

Copy-Item .env.example .env
pip install --upgrade pip setuptools wheel
pip install .\model_wheel\insightface-0.7.3-cp311-cp311-win_amd64.whl
pip install -r requirements.txt

python -m scripts.init_db
.\start-fta.ps1
```

### Truy cập

| Dịch vụ | Địa chỉ |
|:---|:---|
| Dashboard | [http://localhost:8000](http://localhost:8000) |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/api/health](http://localhost:8000/api/health) |

Tài khoản mặc định: `admin` / `admin123`. Hãy đổi mật khẩu trước khi đưa hệ
thống cho người dùng thật.

<a id="cau-hinh"></a>

## Cấu hình

Cấu hình runtime nằm trong file `.env`. File này không được commit lên Git;
`.env.example` là cấu hình mẫu dành cho môi trường mới.

Chọn thiết bị inference:

```env
FACE_ONNX_PROVIDER=cpu
ANTI_SPOOFING_PROVIDER=cpu
```

Các giá trị được hỗ trợ là `cpu`, `cuda` và `auto`. Sau khi thay đổi provider,
cần khởi động lại backend. Provider thực tế có thể kiểm tra tại endpoint
`/api/health`.

Các thiết lập thường dùng:

```env
CAMERA_SOURCE=0
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
CAMERA_FPS=30
RECOGNITION_INTERVAL_FRAMES=5
FACE_RECOGNITION_THRESHOLD=0.4
ANTI_SPOOFING_THRESHOLD=0.5
```

<a id="kien-truc"></a>

## Kiến trúc

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

## Công nghệ

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

## Hiệu năng tham khảo

Hiệu năng phụ thuộc vào CPU/GPU, camera, kích thước detection và tần suất nhận
diện. Cấu hình mặc định ưu tiên khả năng chạy ổn định trên máy phổ thông:

- Detection size: `320 x 320`.
- Camera output: `640 x 480`.
- Recognition interval: mỗi `5` frame.
- FAISS search với quy mô khoảng 50 nhân viên: dưới `1 ms` trong điều kiện local.

## Ghi chú triển khai

SQLite phù hợp cho chạy thử trên một máy. Trước khi triển khai production, cần
đổi secret mặc định, tắt debug, cấu hình HTTPS, backup dữ liệu và cân nhắc chuyển
sang PostgreSQL. Hướng dẫn PostgreSQL nằm tại
[`docs/postgresql-setup.md`](docs/postgresql-setup.md).
