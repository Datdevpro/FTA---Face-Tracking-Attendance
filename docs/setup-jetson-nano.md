# Cài và chạy FTA trực tiếp trên Jetson Nano ARM64

Quy trình này chạy bằng Python virtualenv trên Jetson, không dùng Docker. Script sử dụng Python 3.10, ONNX Runtime CPU và file `.env` ở thư mục gốc của source.

## Cài đặt

Chép toàn bộ source lên Jetson, kể cả `.env.example`. Không cần chép virtualenv từ Windows. Mở terminal tại thư mục FTA và chạy bằng tài khoản thường:

```bash
bash setup-fta-jetson.sh
```

Script sẽ yêu cầu mật khẩu sudo khi cài gói hệ thống. Không thêm `sudo` trước lệnh setup. Để cài xong và khởi động ngay trong terminal:

```bash
bash setup-fta-jetson.sh --start
```

Script thực hiện:

1. Kiểm tra Linux ARM64, hệ điều hành Debian/Ubuntu và glibc từ 2.27.
2. Cài compiler, thư viện cần để build Python và công cụ camera.
3. Dùng Python 3.10 có sẵn nếu phù hợp; nếu thiếu, tải source Python 3.10.21 từ Python.org và build riêng trong `.jetson-python/`. Python hệ thống của JetPack được giữ nguyên.
4. Tạo `.venv-jetson/`, cài `requirements-jetson.txt`, build InsightFace và kiểm tra import.
5. Tạo `.env` nếu chưa có. Nếu thay đổi cấu hình có sẵn, lưu bản sao `.env.before-jetson-*`; đặt hai provider về CPU, tắt DEBUG và thay JWT secret mẫu. Giữ camera, database, dữ liệu và các thiết lập khác.
6. Kiểm tra kết nối database, khởi tạo bảng/dữ liệu mặc định nếu thiếu, tải và kiểm tra model nhận diện.

Lần đầu cần Internet và có thể mất nhiều thời gian để build Python/InsightFace. Mặc định dùng một luồng build để hạn chế RAM; có thể đặt `FTA_BUILD_JOBS=2` nếu máy đủ bộ nhớ. Nếu bị OOM, đóng ứng dụng nặng và cấu hình swap theo hệ điều hành rồi chạy lại. Script không tự thay đổi swap hoặc phân vùng.

## Khởi động và dừng

```bash
bash start-fta-jetson.sh
```

Giữ terminal mở trong lúc sử dụng. Nhấn Ctrl+C để dừng; chạy lại cùng lệnh để khởi động. Script không tạo dịch vụ tự chạy lúc boot.

Mở `http://IP_JETSON:1900` từ máy cùng mạng. Xem IP bằng `hostname -I`. Nếu đổi `PORT` trong `.env`, dùng cổng tương ứng. Tài khoản mặc định khi database mới là `admin` / `admin123`; đổi mật khẩu qua API `/api/auth/change-password` trong `/docs` sau khi đăng nhập.

Launcher dùng một Uvicorn worker, tắt reload, ép provider CPU và đặt múi giờ UTC+7 cho tiến trình. Có thể chọn múi giờ khác bằng biến `FTA_TIMEZONE`; ví dụ `FTA_TIMEZONE=UTC bash start-fta-jetson.sh`. Đồng hồ host vẫn cần chính xác. POSIX `UTC-7` nghĩa là UTC+07:00.

## Camera và cấu hình

Sửa `.env` ở gốc repository, rồi dừng và khởi động lại ứng dụng. Không dùng file env trong `docker-ubuntu/` cho cách chạy này.

```dotenv
HOST=0.0.0.0
PORT=1900
DATABASE_URL=sqlite:///./data/fta.db
CAMERA_SOURCE=0
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
CAMERA_FPS=15
STREAM_PREVIEW_FPS=10
RECOGNITION_INTERVAL_FRAMES=8
RECOGNITION_MAX_STALE_MS=1500
FACE_MODEL_NAME=buffalo_l
FACE_ONNX_PROVIDER=cpu
```

Các thông số tốc độ trên là điểm khởi đầu cho Nano; script giữ lại thông số camera đang có. FPS cấu hình không phải tốc độ nhận diện cam kết.

Với USB, chạy `v4l2-ctl --list-devices` để chọn thiết bị. `CAMERA_SOURCE=0` tương ứng camera index 0; nếu camera khác, đổi index hoặc dùng đường dẫn `/dev/videoN`. Nếu thiếu quyền thiết bị, thêm tài khoản vào nhóm video:

```bash
sudo usermod -aG video "$USER"
```

Đăng xuất và đăng nhập lại để quyền có hiệu lực. Không chạy toàn bộ ứng dụng bằng root chỉ để mở webcam.

Với RTSP, đặt `CAMERA_SOURCE` thành URL thực tế. Camera CSI ribbon cần đường capture/driver tương ứng; bản OpenCV pip này không bảo đảm hỗ trợ Argus/GStreamer. Với `CAMERA_SOURCE=browser`, trình duyệt cần quyền webcam và secure context khi truy cập từ máy khác.

## Kiểm tra hoạt động

Trong terminal thứ hai, sau khi server báo khởi động xong:

```bash
curl -fsS http://127.0.0.1:1900/api/health
curl -fsS -X POST http://127.0.0.1:1900/api/camera/start
sleep 3
curl -fsS http://127.0.0.1:1900/api/camera/status
```

Health cần có `face_model_loaded=true` và `face_provider_active=CPUExecutionProvider`. HTTP 200 hoặc `status=healthy` chưa bảo đảm model tải thành công. Camera chưa bật có thể báo `camera_connected=false`.

Tạo nhân viên, đăng ký ảnh khuôn mặt, thử nhận diện và kiểm tra giờ chấm công trong báo cáo. Chưa có kiểm chứng chạy đầy đủ hoặc benchmark trên kit vật lý cho bộ cài này.

## Dữ liệu và xử lý lỗi

Giữ lại `data/` và `.env` khi cập nhật source. Dừng ứng dụng trước khi sao lưu SQLite:

```bash
mkdir -p backups
tar -czf "backups/fta-data-$(date +%Y%m%d-%H%M%S).tar.gz" data
```

Lưu bản sao `.env` ở nơi riêng tư vì chứa thông tin truy cập. Với PostgreSQL có sẵn, script giữ URL và cài driver; cần backup database bằng công cụ PostgreSQL riêng. Script không cài PostgreSQL server.

Model InsightFace nằm ở `data/models/models/buffalo_l/` với cấu hình mặc định. Giữ model khi cần chạy offline; giọng đọc edge-tts/gTTS vẫn cần Internet.

| Lỗi | Cách xử lý |
| --- | --- |
| Python thiếu SSL khi build | Kiểm tra `libssl-dev` từ repository đúng phiên bản OS, cần OpenSSL 1.1.1 trở lên |
| Không có wheel phù hợp | Kiểm tra ARM64, Python 3.10, glibc >= 2.27 và truy cập PyPI; dùng `requirements-jetson.txt` |
| `.venv-jetson` không hợp lệ | Đổi tên thư mục đó để giữ bản cũ rồi chạy setup lại |
| `bad interpreter` hoặc ký tự `\r` | Chuyển script sang LF bằng `sed -i 's/\r$//' setup-fta-jetson.sh start-fta-jetson.sh` |
| Database kết nối lỗi | Kiểm tra URL trong `.env`, dịch vụ DB và quyền ghi thư mục dữ liệu |
| Model tải lỗi | Kiểm tra mạng, dung lượng trống và đường dẫn model; xem lỗi trong terminal |
| Cổng đang sử dụng | Dừng tiến trình FTA cũ hoặc đổi `PORT`; không chạy hai bản cùng dùng camera/database |
| Chạy chậm hoặc thiếu RAM | Đóng ứng dụng nặng, giảm preview FPS, tăng khoảng cách nhận diện và đo lại độ trễ |

Không cài `requirements.txt` gốc vào virtualenv này vì nó chứa ONNX Runtime GPU cho nền CUDA khác. GPU trên Nano cần bộ runtime riêng được kiểm chứng; đây là cấu hình CPU.

## Cơ sở tương thích

- [Python 3.10.21](https://www.python.org/downloads/release/python-31021/): bản Python dùng khi cần build riêng.
- [ONNX Runtime 1.22.0](https://pypi.org/project/onnxruntime/1.22.0/): có wheel CPython 3.10 ARM64 cho glibc 2.27.
- [FAISS CPU 1.11.0.post1](https://pypi.org/project/faiss-cpu/1.11.0.post1/): chọn bản post1 vì có wheel ARM64 glibc 2.27.

Không nâng cấp glibc hoặc thay Python hệ thống để ép cài gói. Bộ cài kiểm tra import và tải model ngay trên Jetson để phát hiện lỗi binary/driver thực tế.
