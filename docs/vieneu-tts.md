# VieNeu v3 Turbo trong FTA

FTA ưu tiên VieNeu-TTS v3 Turbo để tạo lời chào tại máy. Nếu worker đang nạp
model, bận hoặc gặp lỗi, FTA thử Edge TTS, sau đó gTTS. Edge TTS và gTTS được
giữ nguyên. API `/api/tts/welcome` vẫn trả MP3 và loa camera vẫn dùng go2rtc.

Mục Nhân viên hiện có [cấu hình câu chào và tạo sẵn âm thanh](employee-greetings.md).
Những lời chào này dùng file đã lưu khi nhận diện để giảm thời gian chờ;
giọng riêng của từng nhân viên được ưu tiên so với giọng mặc định `.env`.

## Môi trường riêng

`venv` chạy FTA và nhận diện khuôn mặt. `.venv-vieneu` chạy VieNeu 3.8.4,
ONNX Runtime CPU và các thư viện của nó. Tách môi trường giúp giữ nguyên
NumPy, ONNX Runtime GPU và FastAPI của FTA. Không cài `requirements-vieneu.txt`
vào `venv` hiện tại.

Trên Windows, chạy `setup-vieneu.bat` một lần để tạo môi trường và cài thư viện.
Sau đó chạy `start-fta.bat` hoặc `start-fta.ps1` như bình thường.
Script tự chạy worker nền, dùng lại nếu đã chạy, và vẫn mở FTA nếu VieNeu lỗi.
Worker có thể tiếp tục chạy sau khi đóng FTA.

## Model và tài nguyên

- Model: `pnnbao-ump/VieNeu-TTS-v3-Turbo`, backend ONNX, CPU, FP32.
- Model được nạp một lần trong worker và dùng lại cho các câu chào.
- Mặc định dùng 2 luồng CPU để dành tài nguyên cho nhận diện.
- Lần đầu cần Internet tải model và codec. Cache mặc định ở
  `data/models/vieneu-cache`; giữ cache để các lần sau dùng lại.
- Khi chưa sẵn sàng, worker trả 503 ngay để FTA chuyển sang Edge TTS.
- Khi đang tạo một câu, worker trả 429 cho yêu cầu đồng thời khác.

## Cấu hình

Thêm hoặc đổi trong `.env`, rồi khởi động lại FTA:

```dotenv
TTS_PROVIDER=vieneu
VIENEU_URL=http://127.0.0.1:1985
VIENEU_VOICE=Mai Anh
VIENEU_THREADS=2
VIENEU_TIMEOUT_SECONDS=20
```

Đặt `TTS_PROVIDER=edge` để dùng lại Edge TTS trực tiếp. Các trường `voice` và
`rate` của API TTS cũ vẫn dành cho Edge TTS; giọng VieNeu lấy từ `VIENEU_VOICE`.
VieNeu hiện không áp dụng thông số tốc độ `-8%` của Edge.

Worker chỉ nghe ở `127.0.0.1`, cổng mặc định 1985. `/health` trả tên service,
model, `ready` và loại lỗi nếu nạp model thất bại. `/speech` nhận text và voice,
trả MP3 sau khi VieNeu sinh WAV và FFmpeg chuyển định dạng. Không ghi file
âm thanh trung gian trên đĩa tại bước này; pipeline camera vẫn dùng thư mục
âm thanh tạm như trước.

Worker dùng FFmpeg tại `CAMERA_AUDIO_FFMPEG_BIN`. Log được nối vào
`data/logs/vieneu.stdout.log` và `vieneu.stderr.log`; chưa có xoay vòng tự động.
Log FTA ghi rõ provider đã dùng: VieNeu v3 Turbo, Edge TTS hoặc gTTS.

## Chẩn đoán

```powershell
Invoke-RestMethod http://127.0.0.1:1985/health
Get-Content data/logs/vieneu.stderr.log -Tail 30
```

`ready=true` nghĩa là model đã nạp và tạo câu làm nóng thành công. Nếu
`ready=false` và `error` khác null, xem log, xử lý lỗi rồi khởi động lại riêng
worker. Đổi giọng hoặc số luồng CPU cũng cần khởi động lại worker đang chạy.

Nếu chạy uvicorn thủ công, gọi `python -m scripts.start_vieneu` bằng Python
của FTA trước. Cấu hình Docker cần worker riêng hoặc dịch vụ VieNeu ở địa chỉ
FTA truy cập được; không dùng nguyên đường dẫn Windows bên trong container.

## Kết quả kiểm tra

Kiểm tra thực tế ngày 18/11/2026: worker nạp model thành công, tạo MP3 cho
câu “Xin chào. Chúc bạn một ngày tốt lành.” trong khoảng 1,36 giây ở một lượt
đo với 2 luồng CPU. Luồng VieNeu → FFmpeg → go2rtc hoàn tất và dọn file tạm.
Đây là thời gian tạo MP3 của câu thử, không phải độ trễ từ nhận diện đến khi
loa bắt đầu phát, và chưa phải benchmark trung bình nhiều lượt.

## Nguồn

- [SDK và hướng dẫn](https://github.com/pnnbao97/VieNeu-TTS)
- [Model v3 Turbo và giấy phép Apache 2.0](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo)
