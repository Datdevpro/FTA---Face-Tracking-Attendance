# Hướng Dẫn Chạy FTA Bằng Docker Trên Windows

Tài liệu này giúp bạn chạy hệ thống **FTA (Face Tracking Attendance)** ngay lập tức trên máy tính Windows bằng Docker.

---

## 1. Yêu Cầu Chuẩn Bị
- Máy tính Windows 10 hoặc Windows 11 (64-bit).
- Đã cài đặt và đang bật ứng dụng **[Docker Desktop cho Windows](https://www.docker.com/products/docker-desktop/)** (biểu tượng cá voi màu xanh lá - Engine running).
- Tối thiểu 4 GB RAM (khuyến nghị 8 GB trở lên).

---

## 2. Cách Khởi Chạy (Chỉ 1 Click)

1. Mở thư mục `docker-windows`.
2. Nhấp đúp (Double-click) vào file:
   ```cmd
   run.bat
   ```
3. Script sẽ tự động:
   - Kiểm tra Docker Desktop.
   - Tự động tạo cấu hình nếu chưa có.
   - Build và khởi chạy container FTA.
   - Tự động mở trình duyệt truy cập: **[http://localhost:8000](http://localhost:8000)**

---

## 3. Thông Tin Đăng Nhập Mặc Định

| Mục | Thông tin |
| :--- | :--- |
| **Trang chủ / Dashboard** | [http://localhost:8000](http://localhost:8000) |
| **Tài liệu API (Swagger UI)** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Tài khoản** | `admin` |
| **Mật khẩu** | `admin123` |

---

## 4. Cách Dừng Hệ Thống

Khi không sử dụng nữa, chỉ cần nhấp đúp vào:
```cmd
stop.bat
```
*Lưu ý: Mọi dữ liệu nhân viên, chấm công và hình ảnh đều được lưu an toàn tại thư mục `data/` trên máy tính của bạn, không bị mất khi tắt Docker.*

---

## 5. Hướng Dẫn Về Camera Khi Chạy Docker Trên Windows

Docker trên Windows chạy trong môi trường Linux ảo hóa và không tự động nhìn thấy webcam Windows dưới tên `/dev/video0`. Cấu hình mặc định vì vậy dùng trình duyệt để mở webcam và gửi frame vào backend qua WebSocket.

### Cách 1: Dùng Webcam Qua Trình Duyệt (Khuyến nghị)
Giữ cấu hình sau trong `docker-windows/.env`:
```env
CAMERA_SOURCE=browser
```

Mở [http://localhost:8000/static/live_monitor.html](http://localhost:8000/static/live_monitor.html), nhấn **Bắt đầu** và chọn **Allow/Cho phép** khi trình duyệt hỏi quyền camera. Khi nhấn **Dừng**, ứng dụng sẽ đóng camera và tắt đèn webcam.

> Camera trình duyệt hoạt động trên `localhost` hoặc HTTPS. Nếu truy cập từ một máy khác bằng địa chỉ IP qua HTTP, trình duyệt có thể chặn camera; hãy cấu hình HTTPS hoặc dùng RTSP/IP camera.

### Cách 2: Dùng Camera Điện Thoại
1. Cài ứng dụng **DroidCam** hoặc **IP Webcam** (miễn phí trên Android/iOS).
2. Kết nối điện thoại cùng mạng Wifi với máy tính.
3. Mở ứng dụng, bạn sẽ thấy đường dẫn IP (ví dụ: `http://192.168.1.50:8080/video`).
4. Mở file `.env` trong thư mục `docker-windows/`, sửa dòng:
   ```env
   CAMERA_SOURCE=http://192.168.1.50:8080/video
   ```
5. Chạy lại `run.bat` là camera điện thoại sẽ truyền hình ảnh vào hệ thống!

### Cách 3: Dùng IP Camera / RTSP (Camera an ninh văn phòng)
Nếu bạn có IP Camera trong mạng LAN:
```env
CAMERA_SOURCE=rtsp://username:password@192.168.1.100:554/stream1
```

### Cách 4: Dùng USB Webcam Qua USBIPD (Nâng cao)
Nếu muốn container nhận diện trực tiếp webcam cắm cổng USB của máy tính Windows:
1. Cài đặt `usbipd-win` trên Windows (từ [github.com/dorssel/usbipd-win](https://github.com/dorssel/usbipd-win)).
2. Mở PowerShell quyền Administrator:
   ```powershell
   usbipd list
   usbipd bind --busid <bus-id-cua-camera>
   usbipd attach --wsl --busid <bus-id-cua-camera>
   ```
3. Giữ `CAMERA_SOURCE=0` trong `.env`.

### Cách 5: Đăng Ký Nhân Viên Bằng Tải Ảnh
Bạn có thể vào mục **Nhân viên** trên giao diện Web [http://localhost:8000](http://localhost:8000) và tải trực tiếp ảnh chân dung của nhân viên từ máy tính lên để đăng ký khuôn mặt mà không cần mở camera trực tiếp.

---

## 6. Xem Log & Khắc Phục Lỗi
Nếu muốn theo dõi log trực tiếp của container:
```cmd
docker logs -f fta-app-windows
```

Thời gian chấm công mặc định dùng múi giờ Việt Nam trong `.env`:
```env
TZ=Asia/Ho_Chi_Minh
```
Nếu triển khai tại quốc gia khác, hãy đổi thành tên múi giờ IANA phù hợp trước khi tạo dữ liệu chấm công.
