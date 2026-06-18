# Kế Hoạch Đưa FTA Thành Bản SaaS Cloud Dùng Thử

## Summary
## Summary the future plan to implementation
Mục tiêu là chuyển hệ thống hiện tại từ app chấm công local đơn công ty sang bản **SaaS cloud multi-company** có thể cho người dùng dùng thử. Quyết định đã khóa:

- Deploy target: **Cloud**
- Camera input: **Browser webcam qua WebSocket/getUserMedia**
- Tenant model: **Company tenant**, dữ liệu tách theo `company_id`
- Auth model: **Admin + HR**
- Liveness giai đoạn đầu: **cảnh báo cơ bản**, chưa tích hợp model anti-spoofing chuyên dụng

Trọng tâm không chỉ là deploy, mà là sửa kiến trúc camera, dữ liệu, bảo mật và vận hành để cloud chạy đúng thực tế.

## Key Changes

### 1. Multi-Tenant Data Model

- Thêm entity `Company` và gắn `company_id` vào các dữ liệu nghiệp vụ chính:
  - employees
  - departments
  - face_encodings
  - attendance_records
  - work_schedules
  - admin/users
  - system logs nếu dùng
- Tất cả API list/get/create/update/delete phải lọc theo `current_user.company_id`.
- Unique constraint cần đổi từ global sang theo công ty:
  - `employee_code` unique theo `(company_id, employee_code)`
  - department name unique theo company nếu cần
  - email user unique global hoặc theo company, chọn global cho login đơn giản.
- Migration bằng Alembic là bắt buộc; không tiếp tục `Base.metadata.create_all()` làm cơ chế schema production.

### 2. Cloud Camera Architecture

- Bỏ phụ thuộc `CameraService` đọc `CAMERA_SOURCE=0` trên backend cloud cho live monitor.
- Frontend `live_monitor.html` dùng `navigator.mediaDevices.getUserMedia()` để lấy webcam trong browser.
- Frontend gửi frame định kỳ lên backend qua WebSocket:
  - JPEG/WebP frame binary hoặc base64 ở giai đoạn đầu
  - kèm `company_id` lấy từ token phía backend, không tin client gửi tenant
- Backend WebSocket nhận frame từ browser, chạy recognition/liveness, trả về:
  - overlay metadata: bbox, name, similarity, liveness_score, status
  - attendance events nếu có
- Preview camera nên render local trong browser để mượt; backend chỉ trả metadata AI. Không gửi frame đã annotate từ backend trong bản cloud v1.

### 3. Authentication, Authorization, Security

- Bỏ default credential `admin/admin123` khỏi production flow.
- Thêm onboarding tạo company + admin đầu tiên:
  - `POST /api/auth/register-company` hoặc seed qua admin command cho pilot
- Thêm role:
  - `ADMIN`: quản lý company, user, cấu hình
  - `HR`: quản lý nhân viên, đăng ký face, xem/sửa chấm công, export report
- Bảo vệ WebSocket bằng JWT:
  - token truyền qua query param hoặc subprotocol
  - backend validate token trước khi nhận frame
- CORS không được `allow_origins=["*"]` trong production; chuyển sang env `CORS_ORIGINS`.
- JWT secret bắt buộc lấy từ env, reject startup nếu còn default secret trong production.
- Thêm rate limit cơ bản cho login và WebSocket frame ingest.

### 4. Face Recognition, Liveness, Attendance

- Face embeddings vẫn không cần retrain; đăng ký nhân viên mới tiếp tục lưu embedding vào DB/FAISS.
- FAISS index phải tách theo tenant:
  - option v1: một index in-memory per company
  - rebuild company index khi thêm/xóa face encoding
- Attendance chỉ tạo event khi:
  - employee thuộc cùng company
  - similarity vượt threshold
  - không trong cooldown
  - liveness basic không fail
- Liveness v1 giữ heuristic hiện tại nhưng cần hiển thị rõ:
  - `liveness_score`
  - `liveness_checked`
  - cảnh báo “basic anti-spoofing, không chống replay bằng điện thoại tuyệt đối”
- Không dùng kết quả overlay cũ để tạo attendance. Attendance chỉ dựa trên frame vừa chạy recognition thật.

### 5. Deployment & Operations

- Chuyển database production sang PostgreSQL.
- Thêm Dockerfile + docker-compose cho:
  - backend FastAPI
  - PostgreSQL
  - volume cho uploaded face images/snapshots nếu vẫn lưu local
- Với cloud thật, cân nhắc object storage cho ảnh:
  - S3-compatible storage
  - lưu path/url trong DB
- Thêm startup checks:
  - database reachable
  - JWT secret hợp lệ
  - model path/download ready
  - ONNX provider active
- Thêm health endpoints:
  - `/api/health`
  - `/api/health/ready`
  - `/api/health/ai`
- Logging chuyển sang structured logs, không log SQL mặc định, không log token/frame image.
- Thêm backup/restore PostgreSQL và chính sách retention ảnh.

## Implementation Phases

### Phase 1: SaaS Foundation

- Thêm company/user role model.
- Migration schema sang multi-tenant.
- Update toàn bộ API để filter theo `company_id`.
- Thêm register company hoặc seed command cho pilot.
- Đổi default admin/password flow.
- Thêm auth guard cho WebSocket.

### Phase 2: Browser Camera Cloud Flow

- Frontend dùng browser webcam local preview.
- Gửi frame lên backend WebSocket theo FPS cấu hình.
- Backend nhận frame, chạy recognition, trả metadata.
- Frontend vẽ overlay trên video/canvas.
- Giữ `CameraService` local hiện tại chỉ như legacy/local mode hoặc loại khỏi cloud path.

### Phase 3: Production Hardening

- PostgreSQL + Alembic migrations.
- Dockerfile/docker-compose.
- Env validation cho production.
- CORS origins, JWT secret, debug false.
- Health/readiness endpoints.
- Basic rate limit login/WebSocket.
- Log/error handling chuẩn hơn.

### Phase 4: Pilot UX & Admin Features

- Trang onboarding company/admin.
- Trang quản lý users Admin/HR.
- Cấu hình company:
  - work start/end
  - late threshold
  - recognition threshold
  - liveness threshold/interval
- Export report ổn định theo company/date range.
- UI hiển thị trạng thái AI provider, recognition FPS, liveness score.

## Test Plan

- Unit/API tests:
  - tenant isolation: user công ty A không đọc/sửa dữ liệu công ty B
  - employee code unique theo company
  - login/change password/role permission
  - attendance cooldown
  - face registration updates company FAISS index
- WebSocket tests:
  - reject missing/invalid token
  - reject cross-tenant employee matching
  - accept frame and return overlay metadata
  - attendance only created from valid recognition frame
- E2E pilot scenarios:
  - create company
  - create HR user
  - add employee
  - register face
  - open browser camera
  - recognize employee
  - create attendance record
  - export attendance report
- Deployment checks:
  - fresh Docker compose up
  - migration from empty DB
  - health endpoints pass
  - app starts with production env and rejects unsafe defaults

## Assumptions

- Bản dùng thử đầu tiên là cloud SaaS nhiều công ty, không phải local single-company.
- Camera sẽ chạy trong browser người dùng bằng webcam permission.
- Anti-spoofing giai đoạn đầu chỉ là cảnh báo/cản cơ bản, chưa cam kết chống ảnh điện thoại tuyệt đối.
- PostgreSQL là database production.
- Object storage cho ảnh có thể để phase sau nếu pilot nhỏ, nhưng DB production không dùng SQLite.




<!-- ngay tại ô  " Chấm công hôm nay", hãy chia ra làm 2 ô: "chấm công hôm  nay" nằm trên và ô "Thông tin nhân sự" -->