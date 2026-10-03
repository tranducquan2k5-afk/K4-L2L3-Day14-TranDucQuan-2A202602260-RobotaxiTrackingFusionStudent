# Day 14 — Robotaxi: Tracking & Camera–LiDAR Fusion

Bài cá nhân **4 giờ** trên **CVAT local** của máy bạn (bản đã cài ở Day 2): hoàn thiện một track 3D dài, tự chạy QC theo thời gian, đối chiếu cuboid với ảnh camera trước để ghi discrepancy có căn cứ. Nộp bài bằng **link repo GitHub** của bạn.

| Tài liệu | Đọc khi nào |
| --- | --- |
| [Bài lab](docs/lab.md) | Đầu buổi và trong suốt bài: các bước, checkpoint, cách nộp |
| [Object và đoạn frame](docs/cases.md) | Chọn object J01 và các case ngắn |
| [Hướng dẫn bằng hình](docs/huong-dan-hinh.md) | Lần đầu mở job 3D: tạo track, fit cuboid, keyframe/outside/occluded, Save |
| [Overlay camera trên CVAT local](docs/cvat-overlay.md) | Xem cuboid chiếu lên ảnh `image_1` ngay trong job 3D |
| [Phiếu cá nhân](submission/personal-notes.txt) | Ghi frame fit, L/W/H, keyframe, phát hiện QC và discrepancy |

## Bắt đầu

1. Bấm **Use this template** để tạo repo của bạn, rồi clone về máy (Windows: PowerShell hoặc GitHub Desktop đều được). Cài thư viện Python: `python -m pip install -r requirements.txt` (macOS/Linux: `python3`).
2. Bật CVAT local đã cài ở Day 2 (`docker compose start` trong thư mục CVAT; Windows: mở Docker Desktop, start nhóm container CVAT). Mở `http://localhost:8080` và đăng nhập tài khoản trên máy bạn.
3. Lab Coach phát hai file. Đặt chúng ở thư mục gốc repo:
   - `day14-coach-data-pack.zip`: calibration và bảng frame cho overlay. **Giải nén** ở thư mục gốc repo để có `private/calib-diagnostic.json` và `private/frame-maps/`.

     ```bash
     unzip ~/Downloads/day14-coach-data-pack.zip
     ```

     Windows PowerShell: `Expand-Archive $HOME\Downloads\day14-coach-data-pack.zip -DestinationPath .` (hoặc chuột phải → Extract All, chọn thư mục repo).
   - `day14-vinfast-cvat-upload.zip` (~290 MB): point cloud và 8 ảnh camera của 66 frame. **Không giải nén**; chép nguyên file vào `private/`.

   Thư mục `private/` đã gitignore, không bao giờ được commit.
4. Tạo **hai task** từ cùng file `day14-vinfast-cvat-upload.zip`; lặp các bước dưới hai lần, tên `Day14 J01 <tên bạn>` và `Day14 practice <tên bạn>`:
   1. **Tasks** → **+** → **Create a new task**.
   2. Điền Name. Labels: **Add label** → `vehicles` → **Continue**.
   3. **Select files** → **My computer** → kéo file `day14-vinfast-cvat-upload.zip` vào. Để mặc định các mục khác.
   4. **Submit & Open**, đợi xử lý xong rồi mở job. Workspace phải là **Standard 3D**, có các ô ảnh `image_0`…`image_7` và đủ 66 frame (0–65).
5. Bật overlay để xem cuboid trên ảnh camera trước. Chạy từ thư mục gốc repo:

   | Máy | Lệnh |
   | --- | --- |
   | macOS / Linux | `python3 scripts/cvat-overlay/overlay.py up` |
   | Windows (PowerShell, CMD) | `python scripts\cvat-overlay\overlay.py up` (máy chỉ có `py` thì gõ `py` thay `python`) |

   Rồi tải lại tab CVAT bằng Ctrl+Shift+R (macOS: Cmd+Shift+R). Không cần WSL hay bash. Gặp lỗi, xem [cvat-overlay.md](docs/cvat-overlay.md).
6. Chọn object J01 theo [danh sách](docs/cases.md) và đọc [bài lab](docs/lab.md) từ đầu.

## Nộp bài

Nộp **link repo GitHub** của bạn lên VLearn. Repo chỉ thêm thư mục `submission/` đã điền:

- `submission/personal-notes.txt`: phiếu cá nhân.
- `submission/qc-j01/` và `submission/qc-practice/`: `qc_tracks.csv`, `qc_flags.csv` do `src/cvat3d_fusion.py qc` sinh từ bản export cuối của từng task (cách chạy ở mục "Nộp bài" của [bài lab](docs/lab.md)).

Hai file CSV chỉ chứa số liệu thống kê theo track (số frame, keyframe, L/W/H, drift, cờ), không chứa ảnh hay point cloud. **Không commit** file export `.zip`, thư mục export đã giải nén, ảnh chụp màn hình hay bất kỳ thứ gì trong `private/`. Repo để private thì thêm tài khoản GitHub Lab Coach báo vào Collaborators trước khi nộp link.

## Dữ liệu

Dữ liệu Robotaxi VinFast chỉ dùng cho buổi lab, giữ bảo mật và không chia sẻ ra ngoài. Repo này không chứa PCD, ảnh gốc hay annotation (ảnh trong `images/huong-dan/` là ảnh giao diện, phần ảnh camera đã làm mờ). Hai file dữ liệu Lab Coach phát nằm trong `private/` (đã gitignore). Không commit, đăng ảnh chụp màn hình hay đưa dữ liệu lên repo, VLearn, mạng xã hội hoặc dịch vụ AI bên ngoài. Không sửa calibration hay frame-map để ảnh khớp hơn. Hết buổi lab, xoá hai task trên CVAT local và thư mục `private/`.
