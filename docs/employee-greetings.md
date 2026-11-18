# Câu chào và âm thanh trong mục Nhân viên

Mục Nhân viên cho phép nhập câu chào và chọn giọng VieNeu cho từng người.
Khi lưu, backend tạo sẵn MP3 để nghe thử và WAV 8 kHz để phát qua camera.
Khi nhận diện, hệ thống đọc file có sẵn, bỏ bước TTS và chuyển đổi MP3 sang
WAV ở mỗi lượt. Model VieNeu không cần chạy để phát một file đã sẵn sàng.

## Cách sử dụng

1. Mở Nhân viên, chọn thêm mới hoặc sửa một nhân viên.
2. Nhập câu chào, ví dụ `Xin chào {tên_nhân_viên}. Chúc bạn một ngày tốt lành.`
   Có thể dùng `{name}` thay cho `{tên_nhân_viên}` hoặc nhập câu cố định.
3. Chọn giọng đọc. Lựa chọn mặc định lấy giọng đang cấu hình trong `.env`
   tại thời điểm lưu; sau khi lưu, giọng được giữ riêng cho nhân viên.
4. Nhấn Lưu. Thông tin nhân viên được lưu ngay, còn âm thanh được tạo nền.
5. Đợi trạng thái Âm thanh đã sẵn sàng. Nhấn Nghe thử câu đã lưu để nghe
   trên thiết bị mở trang. Khi camera nhận diện, file được phát ở loa camera.

Sau khi sửa text hoặc giọng, cần nhấn Lưu để áp dụng. Các nút nghe thử và
tạo lại thao tác trên nội dung đã lưu. Tạo lại âm thanh đã lưu yêu cầu TTS
sinh lại file, dùng khi cần thử lại hoặc chưa hài lòng với lần sinh trước.

Câu chào sau khi thay tên phải có từ 1 đến 300 ký tự. Đổi tên, câu chào
hoặc giọng sẽ đổi khóa âm thanh và tạo file tương ứng. Sửa các thông tin
khác, như phòng ban, không tạo lại nếu file hiện tại vẫn còn.

## Trạng thái và khởi động

- Đang chờ: đã lưu, đang đợi lượt tạo file.
- Đang tạo: VieNeu đang sinh âm thanh.
- Sẵn sàng: đã có đủ MP3 và WAV.
- Lỗi: dữ liệu nhân viên vẫn được lưu; kiểm tra VieNeu rồi chọn tạo lại.

Việc sinh file được xếp lần lượt để tránh nhiều yêu cầu tranh CPU. Khi khởi
động FTA, backend đợi VieNeu sẵn sàng rồi chuẩn bị file còn thiếu cho các
nhân viên đang hoạt động. Tác vụ này không chặn startup và có thể mất thời
gian nếu có nhiều nhân viên. Nếu VieNeu không sẵn sàng trong thời gian chờ,
có thể lưu hoặc tạo lại từ mục Nhân viên sau đó.

Nhận diện chỉ phát câu chào đã sẵn sàng; khi đang tạo hoặc lỗi, giao diện
Welcome vẫn cập nhật nhưng chưa có âm thanh. API TTS chung vẫn giữ cơ chế
dự phòng Edge TTS/gTTS. Sinh file theo giọng riêng trong mục Nhân viên dùng
VieNeu để bảo đảm đúng giọng đã chọn.

Thông tin tên và câu chào được đọc mới từ database khi nhận diện, và được
kiểm tra lại lúc lấy lượt phát từ hàng đợi, tránh dùng cache tên cũ. File đang
phát tại thời điểm chỉnh sửa có thể tiếp tục đến hết câu.

## Dữ liệu lưu trữ

Thiết lập được lưu trong bảng mới `employee_greetings`; bảng nhân viên và dữ
liệu hiện có được giữ nguyên. Bảng mới được tạo tự động lúc khởi động FTA
hoặc chạy `scripts.init_db`.

File nằm trong `data/employee_greetings`, tên là khóa băm của nội dung đã thay
tên, giọng và phiên bản model. MP3/WAV ở đây được giữ để tái sử dụng, khác với
file tạm trong `camera_test/welcome_audio`. Thư mục đã được bỏ qua trong Git.
Chưa tự xóa phiên bản file cũ sau khi đổi câu chào hoặc giọng.

```dotenv
EMPLOYEE_GREETING_DIR=./data/employee_greetings
EMPLOYEE_GREETING_GO2RTC_DIR=
```

Để trống biến sau nếu go2rtc đọc được cùng đường dẫn tuyệt đối. Nếu chạy
Docker hoặc máy riêng, mount chung thư mục và đặt biến sau thành đường dẫn
thư mục âm thanh cố định nhìn từ go2rtc. Cấu hình này tách biệt với đường dẫn
file tạm `CAMERA_AUDIO_GO2RTC_DIR`.

## Kiểm tra

Bộ kiểm thử kiểm tra lưu/đổi tên nhân viên, đổi giọng, giữ file khi sửa thông
tin không liên quan, giới hạn text, trạng thái lỗi và phát cache không gọi TTS.
Lần thử thực tế ngày 18/11/2026: file đã lưu được go2rtc chấp nhận sau khoảng
0,319 giây tính từ lúc gọi service phát, không gọi TTS. Đây không phải thời
gian đo từ nhận diện đến khi loa bắt đầu phát và không gồm thời gian chờ
một lời chào khác trong hàng đợi.
