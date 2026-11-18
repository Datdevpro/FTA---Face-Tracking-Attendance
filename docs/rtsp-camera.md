# Camera RTSP cho giám sát và chấm công

## Chọn camera trên Camera Feed

Dropdown bên trái nút **Bắt đầu** có ba lựa chọn: **Webcam** (nguồn USB `0`
trên máy chạy backend), **Cam IMOU xoay** và **Cam IMOU cứng**.
Nhập hai URL tương ứng trong `.env` ở thư mục gốc:

```dotenv
CAMERA_IMOU_ROTATE_RTSP="rtsp://username:password@IP_CAM_XOAY:554/stream1"
CAMERA_IMOU_FIXED_RTSP="rtsp://username:password@IP_CAM_CUNG:554/stream1"
```

Thay toàn bộ URL mẫu bằng URL thực tế của từng camera, bao gồm đường dẫn stream.
Khởi động lại backend, tải lại trang giám sát, chọn nguồn rồi nhấn **Bắt đầu**.
Để đổi nguồn đang chạy, nhấn **Dừng**, chọn nguồn khác rồi nhấn **Bắt đầu**.
Nguồn IMOU chưa có URL sẽ hiển thị thông báo yêu cầu cấu hình.
Mỗi lần chỉ mở một phiên Camera Feed để tránh thay đổi nguồn của phiên khác.

Dropdown dùng hai biến mới trên; `CAMERA_SOURCE` được giữ lại cho client cũ
không truyền lựa chọn camera. Không cần thay đổi luồng đăng ký khuôn mặt.

## Cấu hình nguồn cho client cũ

Khi chạy trực tiếp, cấu hình trong `.env` ở thư mục gốc dự án:

```dotenv
# Nguồn cũ: bỏ comment dòng này và comment URL RTSP để dùng lại USB.
# CAMERA_SOURCE=0
CAMERA_SOURCE="rtsp://username:password@192.168.1.100:554/stream1"
RTSP_OPEN_TIMEOUT_MS=5000
RTSP_READ_TIMEOUT_MS=5000
```

Thay URL mẫu bằng URL camera thực tế. Khởi động lại backend bằng
`start-fta.bat` hoặc `start-fta.ps1`, sau đó mở trang giám sát và bắt đầu camera.

Nếu dùng Docker, đặt các biến tương tự trong `docker-windows/.env` hoặc
`docker-ubuntu/.env`, rồi tạo lại container để nhận cấu hình mới.

## Cách xử lý

- `app/config.py`: đọc nguồn camera và thời gian chờ mở/đọc RTSP (mili giây,
  giá trị dương; mặc định 5000).
- `app/main.py`: truyền cấu hình vào `CameraService`.
- `app/services/camera_service.py`: mở RTSP bằng FFmpeg, giải phóng kết nối cũ
  trước khi kết nối lại, đọc liên tục để cập nhật khung hình mới nhất.
- `STREAM_PREVIEW_FPS` điều chỉnh tốc độ gửi hình về trình duyệt;
  `RECOGNITION_INTERVAL_FRAMES` điều chỉnh tần suất nhận diện.

Với RTSP, độ phân giải và FPS nguồn do camera quyết định. `CAMERA_WIDTH`,
`CAMERA_HEIGHT`, `CAMERA_FPS` vẫn dành cho cấu hình/giới hạn camera USB;
không dùng các biến này để thay đổi thông số luồng RTSP. Muốn giảm độ phân giải
nguồn, chọn luồng phụ hoặc cấu hình trực tiếp trên camera.

Đoạn mở camera và điều tiết FPS cũ được giữ dưới dạng comment trong
`camera_service.py` để dễ khôi phục. Nhánh USB và chế độ `browser` vẫn hoạt động.
Chức năng đăng ký khuôn mặt tiếp tục dùng webcam trình duyệt.

## Phát lời chào qua loa camera

Camera IMOU IPC-S2XEP-10M0S đã phát thành công file MP3 qua go2rtc bằng kênh
âm thanh ngược ONVIF. Xem [hướng dẫn phát âm thanh qua loa camera](camera-audio-go2rtc.md)
để cấu hình URL, chạy lệnh PowerShell và xử lý lỗi `can't find consumer`.
