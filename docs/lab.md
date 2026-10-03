---
day: "D14"
title: "Lab 14 — Robotaxi B: giữ track 3D qua thời gian và đối chiếu Camera–LiDAR"
description: "Hoàn thiện một track 3D 66 frame trên CVAT local, tự chạy QC temporal, đối chiếu overlay camera và làm thêm case ngắn theo tốc độ."
outcomes:
  - "Giữ identity, class và kích thước của một vật rắn qua sequence; đặt thêm keyframe khi cần."
  - "Tự chạy QC temporal trên bản export và xử lý từng cờ bằng evidence trước/sau."
  - "Phân biệt bất nhất do annotation, FOV, occlusion, sparse points và nghi lỗi calibration; ghi hành động có căn cứ."
prerequisites:
  - "Đã fit cuboid bằng Top → Side → Front trong Lab 13."
  - "CVAT local từ Day 2 chạy được trên máy; có Python 3."
  - "Nhận hai file dữ liệu từ Lab Coach đầu buổi (xem README)."
requiredTools:
  - "CVAT local (v2.74.1) với overlay camera của repo này."
  - "Python 3 để chạy `src/cvat3d_fusion.py qc`; repo K4-L23-Day14-Calibration cho phần baseline (làm thêm)."
commonErrors:
  - "Box co theo frame thưa → quay lại kích thước đã xác lập ở frame có đủ evidence."
  - "Chỉ xem keyframe → kiểm thêm toàn bộ frame nội suy của track."
  - "Overlay lệch nhiều object → kiểm cặp dữ liệu và phép chiếu trước khi sửa cuboid."
  - "Commit nhầm file export hoặc `private/` → chỉ commit `submission/`."
requiresSubmission: true
workMode: "individual"
---

# Lab 14 — Robotaxi B: giữ track 3D qua thời gian và đối chiếu Camera–LiDAR

**Thời lượng:** 4 giờ thực hành. **Hình thức:** cá nhân, trên CVAT local của máy bạn. **Nộp bài:** link repo GitHub lên VLearn; repo chỉ chứa phiếu cá nhân và CSV QC trong `submission/`, không chứa dữ liệu (mục [Nộp bài](#nộp-bài)).

Bạn tiếp tục từ cuboid của Lab 13 đến một object đi qua nhiều frame. Nhiệm vụ lõi: **hoàn thiện một track 3D dài, rồi chứng minh quyết định giữ, sửa hoặc báo lại bằng QC và hình ảnh**. Phần bắt buộc là B01 (khởi động), track lõi J01 và bằng chứng của nó; sau đó làm thêm các case ngắn trong [danh sách](cases.md) theo tốc độ. Không ai phải làm hết.

Sequence thực hành là mẫu VinFast `3D_Lidar_sample_data`: **66 frame liên tiếp (0–65), mỗi frame có 8 ảnh camera**, nằm trong `day14-vinfast-cvat-upload.zip`. Bạn tạo hai task từ file này theo README: `Day14 J01 <tên>` và `Day14 practice <tên>`. Số frame trong CVAT trùng số frame trong [danh sách object](cases.md).

Lab Coach có mặt trong lớp để phát dữ liệu và hỗ trợ khi bạn kẹt. Không bước nào phải chờ Coach: bạn tự bật overlay, tự export, tự chạy QC.

| Phút | Việc làm | Xong khi |
|---|---|---|
| 0–20 | Bật CVAT local, giải nén gói dữ liệu, tạo hai task, bật overlay (README). Coach demo 10 phút theo [hướng dẫn bằng hình](huong-dan-hinh.md). | Mở được job 3D của cả hai task, thấy cuboid trên `image_1` khi vẽ thử |
| 20–35 | **Khởi động B01** trong task practice (frame 16–21). | B01 đã Save |
| 35–110 | **Track lõi J01** trong task J01, object theo chữ số cuối mã học viên. Mốc con: phút 55 có L/W/H tham chiếu; phút 85 có keyframe đầu, cuối và chỗ đổi hướng; phút 110 đã bấm `F` qua đủ 66 frame. | J01 đã Save |
| 110–125 | **QC lần đầu cho J01:** export, chạy QC, ghi cờ của track J01 vào phiếu. | Có `submission/qc-j01/` lần đầu và quyết định ban đầu cho từng cờ |
| 125–165 | **Case ngắn** trong task practice theo thứ tự bảng. Khoảng 8–10 phút/case. | Thường được 4–6 case, đã Save |
| 165–190 | **Dừng mở case mới.** Đối chiếu overlay của J01: một ca bình thường, một ca khó. | Hai dòng discrepancy trong phiếu |
| 190–210 | Đổi màn hình với bạn cùng cặp, xem đoạn rủi ro của nhau; quyết định sửa hay giữ. | Ít nhất một quyết định có evidence |
| 210–230 | Rework J01 và case bị góp ý; Save, tải lại trang để kiểm. | Bản cuối đã Save |
| 230–240 | Export lần cuối cả hai task, chạy QC, commit `submission/`, push, nộp link. | Link repo đã nộp trên VLearn |

Khi trễ mốc:

- **J01 chưa xong ở phút 110:** Save, làm tiếp J01 tới phút 130 và bỏ bớt case ngắn. Phút 130 vẫn chưa xong thì Save, ghi frame cuối đã kiểm vào phiếu rồi chuyển sang QC.
- **Một case ngắn quá 15 phút:** Save, ghi chỗ kẹt vào phiếu, sang case kế tiếp.
- **Kẹt một thao tác quá 5 phút:** giơ tay gọi Coach, đừng ngồi đoán.

Tự chạy repo calibration (mục "Chạy phép chiếu mẫu") là phần làm thêm cho người xong sớm.

## Chuẩn bị đúng object

**Đầu ra:** bạn biết object nào mình chịu trách nhiệm, task nào dùng cho việc gì.

1. Làm xong các bước "Bắt đầu" trong README: hai task 66 frame, workspace Standard 3D, overlay báo `overlay: on`.
2. Mở [danh sách object](cases.md). Chọn J01-a/b/c/d theo chữ số cuối mã học viên. Trong task J01, nhảy tới frame neo, tìm xe trong vùng ROI trên `image_1`, rồi tìm cụm điểm tương ứng trong perspective view.
3. Mở `submission/personal-notes.txt`, ghi object J01 và frame neo. Bài yêu cầu một track trong task J01, không gán nhãn toàn cảnh.

Chưa quen workspace 3D thì mở [hướng dẫn bằng hình](huong-dan-hinh.md): tạo Track, fit trên Top/Side/Front, keyframe/outside/occluded và Save.

**Checkpoint:** tìm được object J01 ở frame neo và thấy cuboid thử chiếu lên `image_1`. Không thấy overlay thì xem [cvat-overlay.md](cvat-overlay.md) trước khi làm tiếp.

## Làm B01, J01 rồi case ngắn

**Đầu ra:** track lõi hoàn chỉnh với evidence, cộng các case ngắn theo tốc độ, chất lượng từng case giữ nguyên chuẩn.

Chuẩn bắt buộc là **J01 và evidence của nó**: frame fit đa view, L/W/H có lý do, keyframe, quét nội suy, self-QC, đối chiếu một ca bình thường và một ca khó, quyết định sau review. Số case ngắn phản ánh lượng thực hành; nó không thay bằng chứng về J01.

1. **B01 trong task practice.** Case khởi động 6 frame theo mục "Làm một track từ đầu đến cuối" của hướng dẫn bằng hình. Bắt đầu track ở frame 16, bật `outside` ở frame 22.
2. **J01 trong task J01.** Chọn frame fit, hoàn thiện track trên toàn đoạn object có mặt trong 66 frame. Save thường xuyên.
3. **Case ngắn trong task practice**, theo thứ tự bảng, bỏ qua B01. Mỗi case là một track mới chỉ trên khoảng frame ghi trong bảng; bật `outside` ngay sau frame cuối. Ghi case → track ID vào phiếu. B01–B03 là cùng chiếc xe với một số object J01; vì thế chúng nằm ở task riêng.
4. **Self-check trước khi sang case kế.** Đúng object/class, geometry, keyframe/nội suy, ca khó. Save, tải lại trang kiểm.
5. **Dừng mở case mới ở phút 165.** Ghi case đã xong và case đang dở vào phiếu.

**Checkpoint:** chỉ ra được J01, case đang làm và một quyết định có evidence.

## Chạy phép chiếu mẫu và đọc giới hạn của calibration (làm thêm)

**Đầu ra:** một ảnh LiDAR chiếu lên camera từ dữ liệu mẫu của [repo calibration Day 14](https://github.com/VinUni-AI20k/K4-L23-Day14-Calibration/tree/main), và ghi chú về phạm vi mà ảnh này kiểm chứng. Repo có một PCD và một ảnh camera trước; chúng chính là frame 0 và `image_1.jpg` của sequence lớp.

### Tại sao chạy ví dụ trước khi sửa track?

Khi overlay không khớp, có thể cuboid đặt sai, nhưng cũng có thể bạn đang đọc sai phép biến đổi hoặc ghép nhầm file. Chạy ví dụ có sẵn giúp kiểm môi trường và hiểu hình chiếu trông như thế nào trước khi dùng ảnh để nhận xét annotation. Ví dụ này chỉ có point cloud và ảnh camera. Nó chưa chứng minh track của bạn đúng, vì không có annotation 3D hay box YOLO kèm trong `data/sample/`.

Một điểm trong LiDAR được lưu bằng mét. Điểm tương ứng trên ảnh được lưu bằng pixel. Muốn đặt chúng vào cùng một phép đối chiếu, script phải đưa điểm từ LiDAR sang ego, rồi từ ego sang camera. Khi điểm đã ở hệ camera, phép chiếu dùng chiều sâu Z và đặc tính ống kính để tính vị trí trên ảnh. Vì phép chiếu chia cho Z, vật ở xa chiếm ít pixel hơn dù kích thước thật của vật không thay đổi.

### Intrinsic và extrinsic quyết định điều gì?

Trong repo này, **intrinsic** nằm ở `data/calib/Intrinsics.txt`: kích thước ảnh, ma trận camera K và hệ số méo. **Extrinsic** nằm ở `data/calib/Extrinsics.txt`: các ma trận 4×4 đưa tọa độ giữa các hệ. Hai file có đuôi `.txt` nhưng nội dung là JSON. Bạn đọc các thông số đã được cấp; bài không yêu cầu tự đo calibration.

Điểm dễ nhầm là các ma trận trong cùng file extrinsic không dùng chung một chiều. README quy định `LIDAR_*` là sensor → ego, còn `CAM_*` là ego → camera. Chuỗi của script là `T_ego2cam × T_lidar2ego`. Không nghịch đảo thêm ma trận camera chỉ vì thấy công thức khác trên mạng. Với dữ liệu khác, phải đọc lại manifest thay vì mang quy ước này sang mặc định.

### Tôi cần quan sát gì trên ảnh baseline?

1. Clone repo calibration, cài dependency rồi chạy test. Test kiểm các hàm trên dữ liệu nhỏ; nó không xác nhận calibration của toàn bộ sequence thật.

   ```bash
   python -m pip install -r requirements.txt
   python -m pytest -q
   ```

2. Chạy ví dụ gốc với camera `CAM_P_F` và LiDAR `LIDAR_TOP`:

   ```bash
   python src/lidar_to_image_projection.py \
     --pcd data/sample/point_cloud.pcd \
     --image data/sample/front.jpg \
     --extrinsics data/calib/Extrinsics.txt \
     --intrinsics data/calib/Intrinsics.txt \
     --lidar LIDAR_TOP --camera CAM_P_F \
     --out output/front_projection.jpg
   ```

3. Mở `output/front_projection.jpg`. Tìm mặt đường, cạnh tòa nhà và một vùng có xe. Ghi một vùng bạn thấy hợp lý và một vùng cần kiểm thêm; không dùng số điểm được chiếu như thước đo annotation đúng.
4. Đọc mục 7 của README và ghi vào provenance khoản hiệu chỉnh tịnh tiến mà script đang cộng vào `CAM_P_F` (giá trị ghi trong README). Đây là hiệu chỉnh tác giả fit trên một ảnh; bạn không sửa giá trị để làm bài mình đẹp hơn và không sao chép sang calibration demo.

### Có ảnh kết quả là đã kiểm calibration xong chưa?

Chưa. Ảnh baseline cho biết các đầu vào mẫu có thể được đọc và chiếu trong môi trường của bạn. Chấm màu xuất hiện trên mặt đường hoặc xe là evidence cần quan sát, nhưng một ảnh đẹp chưa đủ để xác nhận nguồn gốc tọa độ, đồng bộ cảm biến hoặc độ đúng trên frame khác. README cũng nêu rõ mức bù đó chưa được chứng minh từ bản vẽ lắp đặt và chỉ được fit cho camera trước.

**Checkpoint:** phân biệt được “script chạy được” với “calibration đã được kiểm cho sequence của tôi”. Ảnh mẫu của repo không quyết định kích thước track.

## Hoàn thiện một track từ frame có đủ evidence

**Đầu ra:** một track có kích thước tham chiếu, keyframe có lý do và đã kiểm trên toàn bộ đoạn.

### Vì sao không fit từ frame xa nhất?

Ở frame xa, point cloud có thể chỉ giữ lại một phần bề mặt xe. Nếu bạn co cuboid theo vài điểm đó, nhãn đang mô tả phần nhìn thấy thay vì kích thước vật rắn. Khi xe đến gần, box lại lớn lên. Mỗi frame có thể trông vừa cụm điểm, nhưng cả sequence sẽ dạy một quan hệ sai: xe thay đổi kích thước theo khoảng cách.

Bạn chọn frame đủ evidence để xác lập L/W/H, sau đó kiểm lại kích thước ấy trên các frame khác. “Frame dày” là frame giúp nhìn ranh giới object rõ; không phải cứ frame cuối hoặc gần nhất thì được dùng. Một cụm dày nhưng dính hai object cũng có thể gây fit sai. Trình tự Top → Side → Front của Lab 13 vẫn giúp kiểm footprint, chiều cao, đáy và bề ngang trước khi chốt.

Các số 4,19 × 2,04 × 1,82 m trong slide thuộc ví dụ track 94. Bạn không gõ bộ số ấy cho mọi xe. Ghi kích thước được xác lập từ object thực của mình, tên frame tham chiếu và lý do chọn frame. Nếu sau đó thấy frame tham chiếu fit sai, sửa kích thước nhất quán trên các mốc có liên quan và ghi rework; không giữ một kích thước sai chỉ để cột drift bằng 0.

### Track và keyframe khác shape rời thế nào?

**Track** nối nhiều trạng thái của cùng một object bằng identity. **Keyframe** là mốc bạn đặt hoặc chỉnh; tool nội suy trạng thái giữa các mốc. **Shape** rời mô tả một frame và không tự bảo đảm cùng identity ở frame kế tiếp. Vì thế, nhiều box cùng label không đủ chứng minh chúng là một track.

Ở đoạn giữa hai keyframe, kiểm tâm, heading và L/W/H trên các frame nội suy. Hai mốc khác kích thước có thể tạo đoạn box co giãn; đừng giả định tool giữ kích thước thay mình. Cách làm của lab là xác lập một kích thước đáng tin, rồi ưu tiên dịch tâm và xoay heading ở các mốc tiếp theo. Khi object rẽ, thêm mốc để quỹ đạo nội suy theo được cụm điểm. Không xóa hàng loạt keyframe chỉ để giảm cảnh báo: các mốc ấy có thể đang giữ đúng đường đi hoặc thời điểm che khuất.


Theo guideline Robotaxi, `occluded` ghi trạng thái bị che; `outside` đánh dấu object đã ra khỏi phạm vi track. Một lần tạm ít điểm hoặc bị che chưa tự động là Exit. Khi không chắc có cùng object, ghi ca đó vào phiếu là "chưa đủ evidence" thay vì cố nối hai vật khác nhau.

### Tôi sẽ thao tác theo thứ tự nào?

1. **Ghi quyết định ban đầu.** Ghi frame định dùng để fit và lý do vào phiếu trước khi hỏi bạn khác.
2. **Xác lập cuboid tham chiếu.** Chọn frame đủ điểm, dùng Top → Side → Front, kiểm label `vehicles`, tạo bằng `Draw new cuboid → Track`. Ghi L/W/H, heading và frame tham chiếu vào phiếu.
3. **Mở rộng track qua thời gian.** Dịch tâm và xoay heading theo evidence. Đặt thêm keyframe tại chỗ đổi hướng, Enter/Exit hoặc nơi nội suy lệch; xem overlay trên `image_1` để kiểm đầu–đuôi.
4. **Kiểm đoạn thưa hoặc bị che.** Giữ kích thước tham chiếu khi evidence hỗ trợ cùng vật rắn. Không tạo ID mới chỉ vì tạm mất điểm; không nối hai object khi identity chưa chắc.
5. **Save.** Duyệt hết đoạn, gồm frame nội suy, rồi Save.

**Checkpoint:** track đã Save, frame tham chiếu truy vết được, đã xem mọi frame trong phạm vi track kể cả frame nội suy. Đoạn identity còn mơ hồ được ghi lại trong phiếu.

## Self-QC temporal và review trước khi rework

**Đầu ra:** QC trước/sau do chính bạn chạy, cách xử lý từng cờ của track mình và một nhận xét review.

### Script chỉ ra lỗi hay chỉ ra nơi cần nhìn?

Script `cvat3d_fusion.py qc` đọc annotation export và thống kê theo track. Nó hữu ích để tìm kích thước thay đổi, góc nhảy hoặc tâm box dịch nhiều. Tuy nhiên, script không nhìn object trong ảnh và không biết toàn bộ ý nghĩa của chuyển động. Hai xe gần nhau có thể kích hoạt cờ `id_switch_risk` dù ID vẫn đúng. Một object đi vào giữa sequence có thể bị báo `fragmentation_suspect` dù đó là một lần Enter hợp lệ.

Các mặc định như drift trên 5%, đổi heading trên 25° giữa hai bản ghi hoặc khoảng cách hai tâm dưới 2,5 m là **heuristic của toolkit**. Chúng giúp bạn chọn ca xem lại; đây không phải ngưỡng đạt của học viên hoặc mức lỗi nghiệp vụ. Nếu kích thước thay đổi ít hơn 5%, script có thể im lặng trong khi quy tắc vật rắn của bài vẫn cần được kiểm. Ngược lại, nhiều cảnh báo không tự động có nghĩa là nhiều nhãn sai.

Đặc biệt, QC chỉ kiểm các item có trong file JSON, không tự tạo frame nội suy bị thiếu. Nếu export chỉ chứa keyframe, kết quả không thể chứng minh frame ở giữa đã đúng. Khoảng dịch tâm và đổi góc cũng cần đọc cùng khoảng cách frame: hai bản ghi cách nhiều frame không tương đương hai frame liên tiếp. Vì thế bạn phải giữ phạm vi export và đối chiếu số frame được kiểm.

### Năm nhóm lỗi temporal xuất hiện ra sao?

Trong lab, bạn xem identity trước/sau các ca xe sát nhau để tìm **ID switch**; xem lần kết thúc và bắt đầu để tìm **fragmentation**; so L/W/H để tìm **dimension drift**; kiểm hướng đầu xe để tìm **orientation drift hoặc flip**; và xem box ở frame ít điểm để tìm **co box hoặc nhảy box do sparsity**. Script hỗ trợ một số dấu hiệu, còn quyết định cuối cần sequence và guideline.

Một track không có cờ vẫn cần xem bằng mắt. Chẳng hạn, hai track có thể đổi object mà tâm box không nhảy quá xa. Sparsity cũng không có một cờ riêng tự chứng minh “đã xử lý đúng”. Review phải quay lại frame thực, chứ không dừng ở việc đọc CSV. Bạn giữ nhận xét ban đầu trước khi nhận phản hồi để thấy mình đã thay đổi quyết định ở đâu.

### Tôi export và chạy QC thế nào?

1. Save trong job. Ở trang task (**Tasks** → task của bạn), bấm **Actions** → **Export task dataset**. Format **Datumaro 3D 1.0**, **bỏ tick Save images**, đặt tên rồi **OK**. Tải file `.zip` về khi CVAT báo xong.
2. Giải nén vào `outputs/` trong repo (đã gitignore), ví dụ `outputs/j01/` cho task J01 và `outputs/practice/` cho task practice. Mỗi lần export mới thì xoá thư mục cũ rồi giải nén lại.
3. Chạy QC từ thư mục gốc repo (Windows: `python` thay `python3`):

   ```bash
   python3 src/cvat3d_fusion.py qc --annotations outputs/j01 --out submission/qc-j01
   python3 src/cvat3d_fusion.py qc --annotations outputs/practice --out submission/qc-practice
   ```

   Mỗi thư mục có `qc_tracks.csv` (một dòng/track: số frame, keyframe, L/W/H, drift, bước nhảy heading/tâm, khoảng cách) và `qc_flags.csv` (một dòng/cờ: loại cờ, track, frame).
4. Tìm dòng của track J01 trong `qc_tracks.csv`. Kiểm `n_frames` khớp đoạn bạn đã làm, `L_drift`/`W_drift`/`H_drift` gần 0. Với mỗi cờ trong `qc_flags.csv`, mở đúng frame trong CVAT, xem frame trước/sau, ghi vào phiếu: sửa, giữ vì hợp lệ, hay chưa đủ evidence.
5. Đổi màn hình với bạn cùng cặp, nhờ xem một đoạn rủi ro. Ghi nhận xét của bạn ấy và lý do bạn đồng ý/không đồng ý.
6. Sửa ca đã xác minh, Save, export lại và chạy lại QC. Bản cuối trong `submission/` là QC của lần export cuối.

Trong task practice, `fragmentation_suspect` ở đầu/cuối case là do cách cắt case; ghi một dòng xác nhận trong phiếu là đủ.

### Nếu cờ vẫn còn thì có nộp được không?

Được, nếu mỗi cờ có cách xử lý truy vết được: đã sửa, giải thích là tình huống hợp lệ, hoặc ghi chưa đủ evidence. Không sửa ngưỡng hay code QC để cờ biến mất. `qc_flags.csv` trống vẫn cần giải thích đoạn khó bạn đã tự xem.

**Checkpoint:** lần theo được một cờ của J01 từ CSV đến frame thực trong CVAT, và ghi được quyết định.

## Đối chiếu Camera–LiDAR và ghi discrepancy có căn cứ

**Đầu ra:** quan sát overlay trên ảnh thật cho track J01, với quyết định sửa, giữ hoặc báo lại cho các ca đã xem.

### Tôi có đang xem ảnh đúng frame không?

Overlay chỉ vẽ trên `image_1` khi tên point cloud của frame khớp bảng frame trong `private/frame-maps`; frame không khớp thì không vẽ. Góc dưới trái ghi bản calibration đang dùng. Nếu cả cảnh lệch đột ngột ở một frame, kiểm task có frame step 1 và đủ 66 frame trước khi nghĩ tới annotation.

### Tôi dùng calibration nào cho sequence thật?

Overlay **không** dùng nguyên chuỗi baseline của repo calibration. PCD mẫu đã được tịnh tiến về gốc ego nhưng chưa xoay, nên profile chỉ giữ phần xoay yaw của `LIDAR_TOP`, bỏ tịnh tiến của nó và bỏ khoản bù của script; `CAM_P_F` dùng ego → camera gốc của repo. Chuỗi này đã được kiểm trên 66 frame bằng ba cách độc lập (ICP giữa các PCD, khớp cạnh LiDAR–ảnh, so cuboid chiếu với box phát hiện): lệch còn khoảng 2 px trên ảnh camera trước. Script baseline của repo vẫn cộng khoản bù đó; đó là khác biệt giữa hai công cụ, không sửa số để ảnh khớp.

Chỉ đọc overlay trên camera trước 1920 × 1536. Các ảnh camera khác giúp nhận diện vật, không có cuboid chiếu.

### Tôi phân loại một chỗ không khớp bằng cách nào?

Ảnh hỗ trợ nhận class, số object và đầu–đuôi xe. Kích thước, tâm và fit hình học vẫn dựa trên point cloud cùng evidence của track. Khi camera không thấy xe, chưa thể kết luận xe không tồn tại: nó có thể ngoài FOV hoặc bị che riêng ở sensor đó. Khi camera thấy rõ nhưng cloud thưa, giữ kích thước đã xác lập nếu identity được hỗ trợ; không suy khoảng cách và cuboid mới chỉ từ pixel.

Lệch cùng chiều trên nhiều object và nhiều frame là dấu hiệu cần điều tra pipeline, gồm calibration hoặc ghép dữ liệu. Đó chưa phải phép đo tự chứng minh calibration sai. Một box lệch riêng có thể là annotation, nhưng vẫn cần kiểm object, heading và cặp file. Bạn ghi điều quan sát được trước, giả thuyết sau; dùng `chưa đủ evidence` khi chưa phân biệt được các nguyên nhân.

1. **Chọn hai frame của J01:** một frame dày (ca bình thường) và một frame khó (thưa, xa, bị che hoặc rìa ảnh).
2. **Quan sát overlay.** Cuboid chiếu có bao đúng xe trên ảnh không, đầu–đuôi có khớp không. Overlay dùng trạng thái nội suy của chính CVAT, nên dời box là ảnh cập nhật ngay.
3. **Ghi discrepancy trước khi sửa.** Trong phiếu: frame, quan sát 2D, quan sát 3D, nguyên nhân nghi ngờ (annotation / FOV / occlusion / sparse / nghi calibration / chưa đủ evidence), hành động.
4. **Hành động có căn cứ.** Lỗi annotation thì sửa trong job 3D và Save. Ca FOV, che khuất hoặc thưa điểm thì ghi lý do giữ nhãn. Nghi lỗi hệ thống (nhiều xe lệch cùng chiều) thì báo Coach kèm frame; không kéo cuboid khỏi point cloud hay sửa calibration để che lệch.

**Checkpoint:** người khác lần được từ ghi chú của bạn đến đúng frame và cuboid cho một ca bình thường và một ca khó.

## Nộp bài

**Đầu ra:** link repo GitHub trên VLearn; repo chứa `submission/` đã điền, không chứa dữ liệu.

1. Kiểm lại J01 trong CVAT: đúng object/label, L/W/H có căn cứ, heading hợp lý, đã xem toàn bộ frame. Save, tải lại trang kiểm.
2. Export lần cuối cả hai task và chạy lại QC như mục Self-QC, để `submission/qc-j01/` và `submission/qc-practice/` là bản cuối.
3. Hoàn thiện `submission/personal-notes.txt`.
4. Kiểm chỉ commit `submission/`:

   ```bash
   git status
   git add submission
   git commit -m "Day 14 submission"
   git push
   ```

   `git status` không được liệt kê `private/`, `outputs/`, file `.zip` hay ảnh. Thấy chúng thì dừng lại hỏi Coach.
5. Mở repo trên GitHub, kiểm có `submission/` và CSV. Dán link repo lên VLearn. Repo private thì thêm tài khoản GitHub Coach báo vào Collaborators.
6. Hết buổi: xoá hai task trên CVAT local, thư mục `outputs/` và `private/`.

**Checkpoint cuối:** link đã nộp, repo trên GitHub có phiếu và CSV QC, không có dữ liệu VinFast.
