# Overlay cuboid trên camera của CVAT local

Bật một plugin trong CVAT local đang chạy trên máy: khi mở job 3D của bản ghi VinFast, panel camera `image_1` (`CAM_P_F`) hiện cuboid chiếu theo calibration ngay trong job, cập nhật theo từng lần chỉnh track (kể cả trước khi Save). Không cần export, chạy Python hay tạo task review riêng. Đây là công cụ đối chiếu khi làm bài; bằng chứng nộp là phiếu cá nhân và CSV QC (xem [bài lab](lab.md#nộp-bài)).

## Cần có

- CVAT local đã cài ở Day 2 (v2.74.1) đang chạy, container giao diện tên `cvat_ui` (tên mặc định của compose CVAT). Thư mục compose nằm ở đâu cũng được.
- Docker (Docker Desktop trên Windows/macOS) và Python 3 (chỉ thư viện chuẩn, không cần `pip install`).
- Clone repo này. Lệnh dưới chạy từ thư mục gốc repo.
- Gói dữ liệu Lab Coach phát (`day14-coach-data-pack.zip`): giải nén ở thư mục gốc repo để có `private/calib-diagnostic.json` và `private/frame-maps/`. Thiếu gói này `up` báo lỗi không tìm thấy calibration.

## Windows

Chạy thẳng trong **PowerShell** hoặc **CMD**, không cần WSL hay Git Bash.

1. Mở Docker Desktop, đợi CVAT chạy (mở được `http://localhost:8080`).
2. Mở PowerShell, kiểm tra:

   ```powershell
   docker ps --format "{{.Names}}" | findstr cvat_ui
   python --version
   ```

   Dòng đầu phải in `cvat_ui`. `python` báo không có thì thử `py --version`; vẫn không có thì cài Python 3 từ python.org (tick **Add python.exe to PATH**) hoặc `winget install Python.Python.3.12`, rồi mở lại PowerShell.
3. Vào thư mục repo, giải nén gói dữ liệu, bật overlay:

   ```powershell
   cd <thư mục repo>
   Expand-Archive $HOME\Downloads\day14-coach-data-pack.zip -DestinationPath .
   python scripts\cvat-overlay\overlay.py up
   ```

4. Tải lại tab CVAT bằng Ctrl+Shift+R.

Máy đã có Ubuntu (WSL) thì cũng có thể chạy bản bash trong Ubuntu như macOS/Linux; hai bản làm cùng một việc.

Lỗi hay gặp trên Windows:

| Thông báo | Cách xử lý |
| --- | --- |
| `python` mở Microsoft Store hoặc báo không có | Dùng `py`, hoặc cài Python 3 như bước 2. |
| `docker not found` / `cannot reach Docker` | Docker Desktop chưa chạy; mở và đợi trạng thái Running. |
| `container cvat_ui is not running` | CVAT chưa bật: trong Docker Desktop start nhóm container CVAT. |
| Lỗi không tìm thấy `private\calib-diagnostic.json` | Chưa giải nén gói dữ liệu ở thư mục gốc repo (phải có thư mục `private` cạnh `README.md`). |

## Bật, kiểm, tắt

```bash
python3 scripts/cvat-overlay/overlay.py up
```

Bản bash cũ vẫn dùng được: `bash scripts/cvat-overlay/overlay.sh up` (cùng `up`/`down`/`status`). Trên Linux, nếu máy phải gõ `sudo docker ...` mới chạy được CVAT, thêm `sudo` trước lệnh trên. Sau đó tải lại tab CVAT bằng Ctrl+Shift+R (macOS: Cmd+Shift+R). `up` in trạng thái cuối; kết quả đúng:

```text
CVAT at http://localhost:8080: 2.74.1
overlay: on
  plugin file: HTTP 200 (expect 200)
  config without login: HTTP 401 (expect 401)
  calibration: calib-diagnostic.json sha256 <12 ký tự>, <N> frames, cameras {'image_1': 'CAM_P_F'}
```

`overlay.py status` in lại các dòng này; `overlay.py down` đưa `cvat_ui` về cấu hình nginx gốc và xoá file plugin. Chạy `up` nhiều lần không sao. Script không mount gì và không build lại image: nó chép plugin, config và `default.conf` sinh từ chính bản gốc của container vào `cvat_ui` đang chạy, chạy `nginx -t` rồi mới reload; nếu nginx từ chối, container giữ cấu hình gốc. Server, database và annotation không bị đụng.

Overlay còn sau `docker compose stop`/`start`. Nếu `cvat_ui` bị tạo lại (ví dụ `docker compose down` rồi `up -d`, hoặc đổi image), plugin mất; chạy lại `up`.

Script dừng, không ghi gì, khi `cvat_ui` mount từ máy host vào `/etc/nginx/conf.d`, `/usr/share/nginx` hoặc chính `default.conf` (ghi vào đó là sửa file trên host), và khi config đang có overlay nhưng bản gốc giữ trong container đã mất. Cả hai trường hợp đều in lệnh cần chạy: bỏ mount khỏi compose, hoặc tạo lại container bằng `docker compose up -d --force-recreate cvat_ui` trong thư mục CVAT.

Biến môi trường để đổi mặc định: `CVAT_URL` (mặc định `http://localhost:8080`), `CVAT_UI_CONTAINER`, `CALIB` (mặc định `private/calib-diagnostic.json`), `FRAMES` (mặc định `private/frame-maps`; cả hai do Lab Coach phát), `CAMERA_MAP` (JSON, mặc định `{"image_1": "CAM_P_F"}`).

## Trong job sẽ thấy gì

- Chỉ frame có point cloud thuộc bản ghi đã calibrate mới được vẽ. Plugin so tên file point cloud của frame (mốc thời gian chụp `\d{10}-\d{9}`) với các `item_id` trong `private/frame-maps`, không dựa vào task id, nên task mới của từng học viên vẫn được nhận.
- Chỉ `image_1` có cuboid; các camera khác giữ ảnh gốc. Góc dưới trái ghi `calib <file> <8 ký tự sha256>` để biết đang dùng bản calibration nào.
- Box dùng state đã nội suy của chính CVAT cho frame đang xem; ẩn object thì cuboid biến mất, dời box thì cuboid đổi theo.
- Ảnh camera khác kích thước ghi trong calibration (`image_size`, bản hiện tại 1920 × 1536): không vẽ box, hiện dòng đỏ `overlay off: image WxH != calib 1920x1536`.
- Task tạo với frame step khác 1 (`frame_filter`, ví dụ `step=2`): không vẽ. CVAT v2.74.1 trả context image theo số frame dữ liệu thay vì số frame của job, nên ảnh camera không cùng thời điểm với point cloud. Console trình duyệt ghi `[d14-overlay] job N skipped: frame_filter step=2`. Tạo task với step 1.
- Job ground truth (`included_frames`) và job mà tài khoản không có quyền đọc: không vẽ.

Cuboid chiếu là công cụ đối chiếu, không phải ground truth. Calibration là profile chẩn đoán với giới hạn ghi trong [bài lab](lab.md#tôi-dùng-calibration-nào-cho-sequence-thật); lệch box trên ảnh cần đọc theo chuỗi frame → identity → geometry → calibration.

## Phạm vi dữ liệu

Config calibration chỉ trả cho phiên CVAT đã đăng nhập (`auth_request` tới `/api/users/self`; chưa đăng nhập nhận 401), nhưng mọi tài khoản đăng nhập được vào CVAT đó đều đọc được nó. Trên máy học viên, người dùng duy nhất là chính học viên. Không cài lên CVAT dùng chung cho nhiều lớp khi chưa giới hạn config theo quyền task.

## Kiểm thử

`python -m pytest -q tests/test_cvat_overlay.py` kiểm bộ sinh config/nginx và so phép chiếu của plugin với renderer Python trên các box trong khung hình, cắt mép ảnh, cắt near plane và nằm sau camera. Phần so phép chiếu cần `node`; thiếu `node` thì test đó bị skip.
