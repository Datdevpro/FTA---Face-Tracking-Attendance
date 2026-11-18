# Phát âm thanh qua loa camera IMOU bằng go2rtc

Camera IMOU IPC-S2XEP-10M0S 10MP đã phát thành công file `voice.mp3`
qua loa tích hợp khi nhận âm thanh từ go2rtc. Cấu hình hoạt động là URL RTSP
có `unicast=true&proto=Onvif` và âm thanh đầu vào được chuyển sang `PCMA/8000`.
Người dùng đã xác nhận nghe đúng nội dung MP3 ngày 18/11/2026.

Trong lần kiểm tra lại sau khi người dùng khởi động lại camera, service backend
đã hoàn thành hai lượt phát liên tiếp từ `voice.mp3`, rồi hoàn thành một lượt
tạo lời chào tiếng Việt bằng TTS và gửi đến camera. Các lượt này đều kiểm tra
kênh loa, chuyển đổi bằng FFmpeg, gọi go2rtc, chờ thời lượng phát và dọn file
tạm thành công. Câu TTS dùng để thử là: “Xin chào. Hệ thống đã kết nối với loa camera.”

## Vai trò của từng kết nối

Luồng phát âm thanh:

```text
voice.mp3 → FFmpeg chuyển sang PCMA 8000 Hz → go2rtc → loa camera
```

go2rtc dùng ONVIF Audio Backchannel, tức kênh gửi âm thanh từ máy tính về
camera. Kết nối này tách biệt với việc FTA lấy hình từ camera để nhận diện.

| Địa chỉ | Vai trò |
| --- | --- |
| `http://localhost:1900` | FTA chạy trực tiếp bằng script khởi động mặc định |
| `http://localhost:8000` | FTA theo cấu hình Docker mặc định |
| `http://127.0.0.1:1984` | Giao diện và API go2rtc trên máy đang chạy go2rtc |
| `rtsp://127.0.0.1:8554/imou` | Luồng RTSP do go2rtc cung cấp trên máy tính |
| `rtsp://USER:PASSWORD@IP_CAMERA:554/...` | Luồng RTSP trực tiếp của camera |

`127.0.0.1` là máy đang mở trình duyệt hoặc chạy lệnh. Chỉ mở FTA sẽ không
tự chạy go2rtc hay mở cổng 1984.

## Chuẩn bị trên Windows

Máy tính và camera cần kết nối được với nhau trong mạng nội bộ.
Thử đàm thoại bằng IMOU Life để kiểm tra loa, sau đó thoát chức năng đàm thoại
trước khi gửi âm thanh từ go2rtc.

Các file thử nghiệm nằm tại:

```text
D:\datworkspace\FTA\camera_test\
    go2rtc.exe
    ffmpeg.exe
    go2rtc.yaml
    voice.mp3
```

Phiên bản đã dùng: go2rtc `1.9.15` và FFmpeg `9.0.2 essentials` trên Windows 64 bit.

- [Tải go2rtc](https://github.com/AlexxIT/go2rtc/releases/latest): chọn `go2rtc_win64.zip` trong Assets rồi giải nén.
- [Tải FFmpeg Essentials ZIP](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip): giải nén và lấy `ffmpeg.exe` trong thư mục `bin`.

## Cấu hình đã hoạt động

Nội dung mẫu của `camera_test/go2rtc.yaml`:

```yaml
api:
  listen: "127.0.0.1:1984"

rtsp:
  listen: "127.0.0.1:8554"

ffmpeg:
  bin: "D:/datworkspace/FTA/camera_test/ffmpeg.exe"

streams:
  imou:
    - "rtsp://USER:PASSWORD@IP_CAMERA:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"
```

Thay `USER`, `PASSWORD`, `IP_CAMERA` bằng thông tin camera thực tế.
Nếu mật khẩu có ký tự đặc biệt như `@`, `#`, `&`, cần mã hóa URL phần mật khẩu.
Giữ dấu ngoặc kép bao quanh URL. Tên stream `imou` phải khớp với `dst=imou`
trong lệnh gửi âm thanh.

Với camera đã thử, URL chỉ có `channel=1&subtype=0` trả về hình ảnh và âm thanh
micro, nhưng thiếu kênh nhận âm thanh vào loa. Khi bổ sung
`&unicast=true&proto=Onvif`, camera công bố thêm kênh âm thanh ngược và
codec `PCMA/8000`. Cấu hình này đã được lưu vào file và cập nhật vào phiên
go2rtc đang chạy trong lần thử thành công.

Không đưa thông tin đăng nhập thật vào tài liệu. Để giữ file cấu hình chứa
mật khẩu và các file công cụ ở máy cục bộ, thêm `/camera_test/` vào `.gitignore`
trước khi đưa mã nguồn lên Git.

## Chạy bằng PowerShell

### Khởi động go2rtc

Mở cửa sổ PowerShell thứ nhất:

```powershell
cd D:\datworkspace\FTA\camera_test
.\go2rtc.exe -config .\go2rtc.yaml
```

Giữ cửa sổ này mở. Truy cập `http://127.0.0.1:1984` trên cùng máy để xem stream
`imou`. Nếu vừa sửa YAML thủ công, nhấn `Ctrl+C` tại cửa sổ này rồi chạy lại
lệnh khởi động để nạp cấu hình mới.

### Phát file MP3

Mở PowerShell thứ hai và chạy nguyên lệnh sau trên một dòng:

```powershell
curl.exe --fail-with-body --show-error --get --request POST "http://127.0.0.1:1984/api/streams" --data-urlencode "dst=imou" --data-urlencode "src=ffmpeg:D:/datworkspace/FTA/camera_test/voice.mp3#audio=pcma/8000#input=file"
```

`#audio=pcma/8000` chọn codec đã thử thành công. `#input=file` giúp phát file
theo thời gian thực. `--data-urlencode` truyền cả các tham số có dấu `#` đến
API, tránh bị hiểu thành phần fragment của URL HTTP.

Kết quả đạt yêu cầu là loa camera phát đúng nội dung `voice.mp3`.

### Dừng phát âm thanh

```powershell
curl.exe --get --request POST "http://127.0.0.1:1984/api/streams" --data-urlencode "dst=imou" --data-urlencode "src="
```

Muốn dừng toàn bộ go2rtc, nhấn `Ctrl+C` trong cửa sổ chạy chương trình.

## Chạy bằng Git Bash

Trong Git Bash, đường dẫn ổ D có dạng `/d/...`. Khởi động go2rtc:

```bash
cd /d/datworkspace/FTA/camera_test
./go2rtc.exe -config ./go2rtc.yaml
```

Mở Git Bash thứ hai để chạy lệnh `curl.exe` một dòng ở phần PowerShell;
lệnh đó dùng được trong cả hai shell. Không dùng cú pháp đường dẫn
`/d/...` bên trong tham số `src=ffmpeg:...`, vì FFmpeg đang chạy là bản Windows;
giữ đường dẫn `D:/datworkspace/FTA/camera_test/voice.mp3` như mẫu.

## Xử lý lỗi đã gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| `Missing expression after unary operator '--'` hoặc `Unexpected token '\\'` | Đã dán lệnh Bash xuống dòng bằng `\` vào PowerShell. Dùng lệnh một dòng ở trên. |
| `can't find consumer`, HTTP 500 | go2rtc chưa thiết lập được đích nhận âm thanh phù hợp. Trong lần thử này, nguyên nhân là URL thiếu `&unicast=true&proto=Onvif`. Bổ sung tham số, nạp lại cấu hình và thử `pcma/8000`. |
| RTSP `DESCRIBE` có header yêu cầu backchannel nhận `EOF`, còn xem hình vẫn hoạt động | Camera đóng kết nối yêu cầu loa. Đóng các phiên đàm thoại khác, kiểm tra lại sau khi khởi động lại camera và go2rtc. Nếu vẫn lỗi, kênh loa chưa sẵn sàng; backend bỏ lượt chào và ghi log, không tự chuyển về loa máy tính. |
| Không mở được `127.0.0.1:1984` | Kiểm tra go2rtc còn chạy, không báo lỗi cổng và đang mở trình duyệt trên cùng máy. |
| FFmpeg hoặc file MP3 không tìm thấy | Kiểm tra đường dẫn `ffmpeg.bin` trong YAML và đường dẫn file trong `src`. File thực tế là `voice.mp3`. |
| API thành công nhưng không nghe tiếng | Kiểm tra loa và âm lượng trong IMOU Life, thoát phiên đàm thoại khác, kiểm tra MP3 có tiếng và dùng đúng codec đã xác nhận. |

Có thể xem thông tin kết nối bằng lệnh chỉ đọc:

```powershell
curl.exe "http://127.0.0.1:1984/api/streams?src=imou&video&audio"
```

Trong `producers[].medias` của kết nối RTSP, camera đã trả về cả âm thanh
`recvonly` từ micro và âm thanh `sendonly` hỗ trợ `PCMA/8000` để go2rtc gửi
về loa. Khi chia sẻ kết quả chẩn đoán, che tên đăng nhập và mật khẩu trong URL.

## Tích hợp lời chào tự động vào FTA

Backend tự đưa từng sự kiện chào trong `app/websocket/camera_stream.py` vào
`CameraAudioService` tại `app/services/camera_audio.py`. Dịch vụ tạo MP3 bằng
TTS có sẵn trong `app/api/tts.py`, chuyển thành WAV để đo chính xác thời lượng,
rồi gửi qua go2rtc dưới dạng `PCMA/8000`. Đoạn phát âm thanh máy tính trong
`frontend/live_monitor.html` được giữ dưới dạng comment; Welcome vẫn hiển thị.

TTS hiện ưu tiên VieNeu v3 Turbo chạy cục bộ, sau đó thử Edge TTS và gTTS khi
cần dự phòng. Xem [cài đặt và cấu hình VieNeu](vieneu-tts.md). Các script khởi
động Windows tự mở cả worker VieNeu và go2rtc nếu chưa chạy.

Luồng đang sử dụng:

```text
Nhận diện nhân viên → hàng đợi → TTS → FFmpeg → API go2rtc → loa camera
```

Dịch vụ chạy nền và chờ phát xong trước khi lấy lời chào tiếp theo. Hàng đợi
không nhận lặp một nhân viên đang chờ hoặc đang phát, chứa tối đa 5 lời chào
đang chờ và bỏ lời chào đã chờ quá 30 giây. Cơ chế chống lặp 8 giây của luồng
nhận diện vẫn áp dụng. File MP3 và WAV tạm được xóa sau khi phát hoặc gặp lỗi.
Lỗi âm thanh được ghi log và không dừng luồng nhận diện.
Trước khi tạo lời chào, dịch vụ kiểm tra kênh nhận `PCMA/8000` của camera;
nếu kênh này chưa sẵn sàng, dịch vụ bỏ lượt phát thay vì tạo thêm tiến trình
FFmpeg trong go2rtc. go2rtc 1.9.15 có thể giữ tiến trình nguồn FFmpeg khi việc
ghép kênh thất bại. Khi gặp lỗi này sau nhiều lần thử, đóng các phiên đàm
thoại khác và khởi động lại go2rtc; kiểm tra các tiến trình FFmpeg do lần thử
đó tạo ra nếu file tạm vẫn đang bị giữ mở.

Cấu hình mặc định phù hợp với thư mục `camera_test` trên Windows hiện tại.
Có thể đặt các biến sau trong `.env` rồi khởi động lại backend:

```dotenv
CAMERA_AUDIO_ENABLED=true
CAMERA_AUDIO_GO2RTC_URL=http://127.0.0.1:1984
CAMERA_AUDIO_STREAM=imou
CAMERA_AUDIO_FFMPEG_BIN=./camera_test/ffmpeg.exe
CAMERA_AUDIO_DIR=./camera_test/welcome_audio
CAMERA_AUDIO_GO2RTC_DIR=
CAMERA_AUDIO_QUEUE_SIZE=5
```

Khi chạy `start-fta.bat` hay
`start-fta.ps1`, script tự khởi động `camera_test/go2rtc.exe` ở chế độ nền
trước khi chạy FTA. Nếu API go2rtc đã hoạt động, script dùng lại, không mở
thêm tiến trình. Không cần mở trình duyệt hay giữ một cửa sổ go2rtc riêng.
go2rtc tiếp tục chạy nền sau khi đóng FTA để có thể dùng lại ở lần mở sau.
Script bỏ qua khởi chạy khi tắt `CAMERA_AUDIO_ENABLED` hoặc cấu hình go2rtc
trên máy khác. Nếu thiếu công cụ hoặc lỗi khởi chạy, script cảnh báo và vẫn
mở FTA; xem `camera_test/go2rtc.stdout.log` và `go2rtc.stderr.log` để chẩn đoán.
API trong YAML phải khớp `CAMERA_AUDIO_GO2RTC_URL`. Nếu chạy uvicorn thủ công
hoặc Docker thì cần tự khởi động go2rtc.

`CAMERA_AUDIO_STREAM` là đích loa
chung đã cấu hình, không tự đổi theo dropdown nguồn hình. Khi chọn webcam
hoặc camera khác, lời chào vẫn phát ở loa stream `imou`. Đặt
`CAMERA_AUDIO_ENABLED=false` để tắt âm thanh; hệ thống không tự chuyển về loa
máy tính khi camera mất kết nối.

Sau khi cập nhật mã nguồn, khởi động lại backend nếu không chạy chế độ reload,
rồi tải lại trang Camera Feed bằng `Ctrl+F5` để nạp JavaScript đã tắt phát loa
máy tính. Bật Camera Feed và nhận diện một nhân viên đã đăng ký. Log backend
cần có `Camera welcome audio enabled`, sau đó `Playing camera welcome` và
`Camera welcome playback completed` khi xử lý lời chào. Các kiểm tra phát thử
ở trên xác nhận tuyến âm thanh; việc nhận diện thật vẫn dùng sự kiện welcome
của Camera Feed.

Nếu backend hoặc go2rtc chạy trong Docker, dùng địa chỉ dịch vụ và đường dẫn
được mount phù hợp. `CAMERA_AUDIO_DIR` là đường dẫn lưu file ở backend,
`CAMERA_AUDIO_GO2RTC_DIR` là cùng thư mục đó nhìn từ go2rtc; để trống biến sau
nếu hai chương trình nhìn thấy cùng đường dẫn tuyệt đối. Trên Linux, đặt
`CAMERA_AUDIO_FFMPEG_BIN=ffmpeg`. Đường dẫn ổ D và `127.0.0.1` trong phần thử
thủ công dành cho các chương trình chạy trực tiếp trên cùng máy Windows.

## Tài liệu tham khảo

- [go2rtc Stream to camera](https://github.com/AlexxIT/go2rtc/blob/master/internal/streams/README.md#stream-to-camera)
- [go2rtc RTSP và tham số ONVIF](https://github.com/AlexxIT/go2rtc/blob/master/internal/rtsp/README.md)
- [Kết nối camera RTSP trong FTA](rtsp-camera.md)
