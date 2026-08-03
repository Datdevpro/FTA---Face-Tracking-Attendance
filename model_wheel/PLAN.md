# FTA Product Release Roadmap

Mục tiêu: đưa FTA từ bản local prototype thành một sản phẩm chấm công bằng khuôn mặt có thể phát hành cho người dùng thật, có onboarding, bảo mật, vận hành, tài liệu, và khả năng mở rộng theo nhiều công ty.

## Milestone 0 - Product Definition & Release Baseline

Mục tiêu của milestone này là khóa phạm vi sản phẩm trước khi code lớn. Nếu bỏ qua bước này, dự án rất dễ trôi từ “sản phẩm” thành một đống feature rời rạc.

### Việc cần làm

- Xác định phiên bản release đầu tiên là gì:
  - `Local Business Edition`: chạy tại máy của công ty, camera local, SQLite/PostgreSQL local.
  - `Cloud SaaS Edition`: nhiều công ty, browser camera, PostgreSQL cloud.
  - Chọn một hướng chính cho v1. Khuyến nghị: nếu muốn product hóa nhanh, làm `Local Business Edition` trước; nếu mục tiêu gọi vốn/SaaS, làm `Cloud SaaS Edition`.
- Viết rõ user chính:
  - Owner/Admin công ty.
  - HR/nhân sự.
  - Nhân viên được chấm công.
- Viết rõ workflow cốt lõi:
  - Tạo công ty/tài khoản admin.
  - Thêm phòng ban.
  - Thêm nhân viên.
  - Đăng ký khuôn mặt.
  - Bật camera chấm công.
  - Xem/sửa dữ liệu chấm công.
  - Xuất báo cáo.
- Đặt acceptance criteria cho bản release:
  - Nhận diện đúng với tập 30-50 nhân viên nội bộ.
  - Camera preview tối thiểu 10-15 FPS trong điều kiện máy mục tiêu.
  - Tạo attendance record trong vòng 1-2 giây sau khi nhận diện.
  - Không cho user chưa đăng nhập truy cập API nghiệp vụ.
  - Có backup/restore database.

### Kết quả đầu ra

- Một trang `docs/product-scope.md`.
- Một checklist release v1.
- Quyết định rõ: local product hay cloud SaaS là hướng release đầu tiên.

## Milestone 1 - Clean Architecture & Configuration Foundation

Mục tiêu là làm nền kỹ thuật sạch để các milestone sau không phải vá chồng vá.

### Việc cần làm

- Chuẩn hóa config:
  - Tách config dev/production.
  - Thêm `APP_ENV=development|production`.
  - Production phải reject startup nếu còn default secret/password.
  - CORS lấy từ `CORS_ORIGINS`, không hard-code `allow_origins=["*"]`.
- Chuẩn hóa start/deploy:
  - Giữ `start-fta.ps1` và `start-fta.bat` cho dev local.
  - Thêm command production không dùng `--reload`.
  - Thêm README rõ cách chạy dev và production.
- Chuẩn hóa logging:
  - Không log SQL mặc định.
  - Không log token, ảnh, embedding.
  - Log các event quan trọng: login, camera start/stop, face registration, attendance event.
- Chuẩn hóa health check:
  - `/api/health`: app alive.
  - `/api/health/ready`: DB/model/index ready.
  - `/api/health/ai`: model provider, loaded state, FAISS status.
- Loại bỏ hoặc đánh dấu rõ các đường chạy legacy:
  - Camera backend local.
  - Browser camera cloud path nếu triển khai SaaS.

### Kết quả đầu ra

- App khởi động an toàn hơn.
- Config rõ ràng hơn.
- Có endpoint health đủ dùng cho deploy.

## Milestone 2 - Authentication, Authorization & User Management

Mục tiêu là biến auth hiện tại từ “có JWT” thành auth đủ dùng cho product.

### Việc cần làm

- Bỏ phụ thuộc production vào tài khoản mặc định `admin/admin123`.
- Thêm flow tạo admin đầu tiên:
  - Local product: setup wizard hoặc CLI command.
  - SaaS: register company + admin.
- Thêm roles:
  - `ADMIN`: quản trị hệ thống/công ty.
  - `HR`: quản lý nhân viên, chấm công, báo cáo.
  - `VIEWER` nếu cần: chỉ xem báo cáo.
- Áp phân quyền vào API:
  - Employee CRUD: Admin/HR.
  - Face registration/delete: Admin/HR.
  - Attendance edit/manual: Admin/HR.
  - Reports: Admin/HR/Viewer tùy scope.
- Bảo vệ WebSocket camera bằng JWT.
- Xử lý token:
  - Token hết hạn thì frontend redirect login.
  - Không lưu thông tin nhạy cảm ngoài token.
- Thêm change password UI nếu chưa có.
- Thêm quản lý user nếu đi theo product/SaaS.

### Kết quả đầu ra

- Không còn endpoint nghiệp vụ quan trọng bị mở.
- Có role rõ ràng.
- Swagger/Auth hoạt động đúng với JWT.

## Milestone 3 - Data Model, Database & Migration Readiness

Mục tiêu là làm dữ liệu đủ bền để phát hành. SQLite có thể dùng cho bản local nhỏ, nhưng cần migration và backup rõ ràng.

### Việc cần làm

- Chọn database production:
  - Local product nhỏ: SQLite hoặc PostgreSQL local.
  - Product nghiêm túc/SaaS: PostgreSQL.
- Bật Alembic migration thật:
  - Không dùng `Base.metadata.create_all()` như cơ chế schema production.
  - Tạo migration baseline từ schema hiện tại.
- Nếu đi SaaS:
  - Thêm `Company`.
  - Thêm `company_id` vào employees, departments, face_encodings, attendance_records, users, schedules.
  - Unique `employee_code` theo `(company_id, employee_code)`.
  - Tất cả API filter theo `current_user.company_id`.
- Thêm backup/restore:
  - SQLite: hướng dẫn copy DB an toàn khi app stopped hoặc dùng backup command.
  - PostgreSQL: script `pg_dump`/restore.
- Thêm chính sách dữ liệu:
  - Xóa nhân viên thì soft delete hay hard delete.
  - Xóa face images/embeddings khi nào.
  - Retention attendance bao lâu.

### Kết quả đầu ra

- Có migration.
- Có backup/restore.
- Dữ liệu không còn phụ thuộc vào “chạy lại init_db là xong”.

## Milestone 4 - Face Registration & Biometric Data Safety

Mục tiêu là làm phần đăng ký khuôn mặt đáng tin và an toàn hơn, vì đây là chỗ người dùng sẽ đụng nhiều và cũng là dữ liệu nhạy cảm nhất.

### Việc cần làm

- Hoàn thiện đăng ký khuôn mặt:
  - Upload ảnh.
  - Chụp ảnh trực tiếp bằng camera.
  - Hiển thị quality score.
  - Hiển thị lỗi rõ: không thấy mặt, nhiều mặt, ảnh mờ, chất lượng thấp.
- Kiểm soát số lượng face image/embedding:
  - Giới hạn mỗi nhân viên.
  - Chọn ảnh primary.
  - Cho xóa ảnh/embedding.
- Bảo vệ dữ liệu sinh trắc học:
  - Không log embedding.
  - Không expose đường dẫn file nhạy cảm quá rộng.
  - Có quyền xóa face data theo nhân viên.
  - Có thông báo/consent nếu dùng trong môi trường thật.
- Nếu đi SaaS:
  - Lưu ảnh trong object storage thay vì local disk.
  - Tách path theo company/employee.
  - Không cho tenant khác truy cập ảnh.

### Kết quả đầu ra

- Flow đăng ký face đủ tốt cho HR dùng hằng ngày.
- Có story rõ về bảo vệ dữ liệu khuôn mặt.

## Milestone 5 - Camera Runtime & Recognition Performance

Mục tiêu là làm camera mượt, ổn định và không khiến người dùng thấy app “đơ”.

### Việc cần làm

- Giữ kiến trúc tách preview và recognition:
  - Preview gửi/render mượt.
  - Recognition chạy theo interval.
  - Overlay dùng kết quả mới nhất nhưng không tạo attendance từ overlay cũ.
- Thêm config runtime:
  - `STREAM_PREVIEW_FPS`.
  - `RECOGNITION_INTERVAL_FRAMES`.
  - `RECOGNITION_MAX_STALE_MS`.
  - `MAX_DETECT_DIM`.
  - `JPEG_QUALITY`.
- Thêm metrics UI:
  - Preview ms/FPS.
  - AI recognition ms.
  - Recognition pending/running.
  - Provider: CUDA/CPU.
- Benchmark model:
  - `buffalo_l` hiện tại.
  - Thử `buffalo_s` hoặc `buffalo_sc` nếu cần mượt hơn.
  - Ghi lại accuracy/FPS tradeoff.
- Warmup model khi startup hoặc khi bật camera.
- Xử lý camera lifecycle:
  - Start nhanh.
  - Stop release camera chắc chắn.
  - Không giữ frame cũ sau khi stop.
  - Reconnect hoặc báo lỗi rõ nếu camera bận.

### Kết quả đầu ra

- Camera có cảm giác mượt trong điều kiện máy mục tiêu.
- Có số đo để tuning thay vì cảm tính.

## Milestone 6 - Anti-Spoofing & Risk Controls

Mục tiêu là nói thật và làm thật về anti-spoofing. Heuristic hiện tại không đủ chống ảnh điện thoại tuyệt đối.

### Việc cần làm

- Với bản đầu:
  - Giữ anti-spoofing basic như cảnh báo/cản cơ bản.
  - Hiển thị `liveness_score`.
  - Log `liveness_checked`.
  - Không quảng cáo là chống giả mạo tuyệt đối.
- Tăng chất lượng heuristic:
  - Kiểm tra toàn frame để phát hiện màn hình điện thoại.
  - Kiểm tra glare/moire tốt hơn.
  - Chỉ pass nếu nhiều frame liên tiếp ổn.
- Chuẩn bị hướng nâng cấp:
  - Challenge-response: chớp mắt/quay đầu.
  - Model chuyên dụng: MiniFASNet/Silent Face Anti-Spoofing.
  - Depth/IR camera nếu khách hàng yêu cầu bảo mật cao.
- Chính sách sản phẩm:
  - Nếu liveness fail thì không tạo attendance.
  - Nếu liveness uncertain thì có thể đưa vào danh sách cần HR review.

### Kết quả đầu ra

- Anti-spoofing không còn là lời hứa quá đà.
- Có cơ chế cảnh báo/risk review rõ ràng.

## Milestone 7 - Attendance, Reports & HR Workflow

Mục tiêu là biến app từ demo nhận diện thành công cụ HR dùng được.

### Việc cần làm

- Hoàn thiện logic chấm công:
  - Check-in/check-out rõ ràng.
  - Cooldown hợp lý.
  - Manual correction có audit note.
  - Late/Present/Absent/Half-day rõ.
- Cấu hình lịch làm việc:
  - Work start/end.
  - Late threshold.
  - Theo công ty hoặc chi nhánh nếu cần.
- UI cho HR:
  - Xem danh sách hôm nay.
  - Sửa record thủ công.
  - Lọc theo phòng ban/ngày/tháng.
  - Xem ảnh snapshot nếu có.
- Báo cáo:
  - Daily report.
  - Monthly report.
  - Excel export.
  - Summary theo nhân viên/phòng ban.
- Audit:
  - Ai sửa attendance.
  - Sửa lúc nào.
  - Lý do sửa.

### Kết quả đầu ra

- HR có thể dùng app như công cụ chấm công thật, không chỉ xem camera.

## Milestone 8 - Frontend Product Polish

Mục tiêu là làm UI bớt prototype và gần product hơn.

### Việc cần làm

- Sửa encoding tiếng Việt toàn bộ file/document nếu còn mojibake.
- Chuẩn hóa trạng thái loading/error/empty.
- Làm rõ các flow:
  - Login.
  - Dashboard.
  - Employees.
  - Face registration.
  - Live monitor.
  - Attendance.
  - Reports.
- Thêm validation frontend:
  - Employee code.
  - Email/phone.
  - Required fields.
  - Max 5 face images.
- Thêm trang/settings:
  - Camera config.
  - Recognition threshold.
  - Liveness threshold.
  - Work schedule.
- Làm responsive đủ dùng cho laptop/tablet.

### Kết quả đầu ra

- Người dùng mới có thể tự thao tác mà không cần bạn ngồi cạnh giải thích từng nút.

## Milestone 9 - Packaging, Deployment & Operations

Mục tiêu là đóng gói để người khác cài/chạy được, không phụ thuộc môi trường máy bạn.

### Việc cần làm

- Local product packaging:
  - Script install dependencies.
  - Script init database.
  - Script start/stop.
  - Hướng dẫn GPU CUDA hoặc CPU fallback.
  - Có folder data rõ ràng.
- Cloud/SaaS packaging:
  - Dockerfile.
  - docker-compose cho local staging.
  - Production command không `--reload`.
  - PostgreSQL service.
  - Object storage nếu dùng.
  - Env sample production.
- Monitoring:
  - Health checks.
  - Logs.
  - Error reporting.
  - Basic metrics: request count, camera sessions, recognition latency.
- Backup:
  - Database.
  - Face images.
  - FAISS index có thể rebuild từ DB, không nhất thiết backup như source of truth.
- Upgrade process:
  - Chạy migration.
  - Backup trước migration.
  - Rollback guide.

### Kết quả đầu ra

- Có thể cài ở máy khác hoặc deploy staging mà không cần đoán mò.

## Milestone 10 - QA, Pilot & Release

Mục tiêu là kiểm thử như sản phẩm thật trước khi đưa người dùng dùng thử.

### Việc cần làm

- Test tự động:
  - Auth.
  - Employee CRUD.
  - Face registration.
  - Attendance logic.
  - Reports export.
  - Tenant isolation nếu SaaS.
- Test thủ công:
  - Đăng nhập.
  - Tạo nhân viên.
  - Chụp/upload face.
  - Bật camera.
  - Nhận diện.
  - Check-in/check-out.
  - Export report.
- Test hiệu năng:
  - 10 nhân viên.
  - 50 nhân viên.
  - 100 nhân viên nếu mục tiêu mở rộng.
  - CPU mode.
  - CUDA mode.
- Test camera:
  - Camera mở/tắt nhiều lần.
  - Camera bị app khác giữ.
  - Mất camera giữa chừng.
  - Ánh sáng yếu.
  - Nhiều mặt trong frame.
- Release checklist:
  - Không dùng default secret.
  - Không dùng default password.
  - Backup OK.
  - Docs OK.
  - Known limitations documented.

### Kết quả đầu ra

- Bản release candidate.
- Release notes.
- Hướng dẫn cài đặt/sử dụng.
- Danh sách known issues.

## Ưu Tiên Gần Nhất

Nếu bắt đầu ngay từ codebase hiện tại, thứ tự nên làm là:

1. Sửa sạch encoding tài liệu và UI còn lỗi.
2. Quyết định release đầu tiên là local product hay cloud SaaS.
3. Bảo vệ WebSocket camera bằng JWT.
4. Bỏ default admin/password khỏi production.
5. Thêm Alembic migration baseline.
6. Làm health/readiness endpoints.
7. Hoàn thiện face registration bằng upload + chụp trực tiếp.
8. Benchmark camera runtime sau khi đã tách preview/recognition.
9. Viết checklist QA cho flow chấm công end-to-end.
10. Đóng gói dev/local release trước khi mở rộng SaaS.

## Ghi Chú Quan Trọng

- Face recognition hiện tại không cần retrain khi thêm nhân viên mới; hệ thống lưu embedding và cập nhật FAISS.
- Anti-spoofing hiện tại chỉ là basic heuristic, chưa đủ chống ảnh điện thoại một cách chắc chắn.
- Dữ liệu khuôn mặt là dữ liệu nhạy cảm; product release cần privacy/data retention rõ ràng.
- Nếu chọn cloud SaaS, kiến trúc camera backend-local hiện tại phải được thay bằng browser camera hoặc edge agent.
