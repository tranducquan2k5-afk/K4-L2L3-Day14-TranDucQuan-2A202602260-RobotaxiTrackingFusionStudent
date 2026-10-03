# Danh sách object và đoạn frame

Cả bài dùng một sequence 66 frame (frame 0–65) trong file `day14-vinfast-cvat-upload.zip`. Bạn tạo **hai task** từ cùng file này (README bước 4):

- Task **`Day14 J01 <tên>`**: track lõi, một object, toàn bộ 66 frame.
- Task **`Day14 practice <tên>`**: các case ngắn, mỗi case một track mới trên đúng khoảng frame ghi trong bảng.

Hai task tách nhau vì một số case ngắn là cùng chiếc xe với J01. Số frame trong CVAT trùng số frame trong bảng.

Cách tìm object: nhảy tới **frame neo**, nhìn ô `image_1` (camera trước, 1920 × 1536). Object nằm trong vùng **ROI** `[x1, y1, x2, y2]` tính bằng pixel từ góc trên trái ảnh. ROI là vị trí ước lượng từ phép chiếu; nếu vùng đó có hai xe, chọn xe có tâm gần tâm ROI nhất và ghi lại lựa chọn vào phiếu. Sau đó tìm cụm điểm tương ứng trong perspective view; bật overlay giúp đối chiếu nhanh.

## J01 — track lõi (bắt buộc)

Chọn object theo **chữ số cuối của mã học viên**, để các bạn ngồi cạnh nhau làm object khác nhau.

| Chữ số cuối | Object | Frame neo | ROI trên `image_1` |
| --- | --- | --- | --- |
| 0, 4, 8 | J01-a | 23 | [1531, 839, 1896, 1041] |
| 1, 5, 9 | J01-b | 38 | [1613, 863, 1902, 1022] |
| 2, 6 | J01-c | 48 | [1615, 840, 1910, 1017] |
| 3, 7 | J01-d | 65 | [1469, 833, 1826, 1071] |

Track phủ toàn đoạn object có mặt trong 66 frame, không chỉ quanh frame neo.

## Case ngắn (làm thêm theo thứ tự)

Làm B01 trước để quen thao tác, sau J01 đi tiếp theo thứ tự bảng. Chỉ track trong khoảng frame ghi ở cột "Frame": bắt đầu track ở frame đầu, bật `outside` ngay sau frame cuối nếu object vẫn còn trong cảnh.

| Case | Mức | Frame | Frame neo | ROI trên `image_1` | Luyện gì |
| --- | --- | --- | --- | --- | --- |
| B01 | cơ bản | 16–21 | 21 | [1408, 847, 1730, 1023] | Fit đa view, giữ L/W/H |
| B02 | cơ bản | 28–33 | 33 | [1425, 849, 1630, 962] | Dịch tâm và kiểm nội suy |
| B03 | cơ bản | 36–41 | 41 | [1415, 847, 1590, 961] | Giữ dimension khi range thay đổi |
| B04 | cơ bản | 28–33 | 33 | [74, 858, 224, 948] | Phân biệt keyframe với frame nội suy |
| B05 | cơ bản | 52–57 | 57 | [1432, 827, 1657, 944] | Track ngắn trong cụm xe |
| B06 | cơ bản | 55–60 | 60 | [1405, 840, 1649, 940] | Tự kiểm geometry và heading |
| M01 | trung gian | 2–9 | 7 | [1605, 869, 1919, 1025] | Phân biệt FOV camera và sự tồn tại 3D |
| M02 | trung gian | 6–13 | 10 | [0, 827, 160, 964] | Chọn keyframe khi tâm/heading đổi |
| M03 | trung gian | 42–49 | 49 | [543, 849, 613, 889] | Evidence xa và điểm thưa |
| M04 | trung gian | 48–55 | 54 | [1098, 837, 1156, 876] | Giữ kích thước khi object xa |
| M05 | trung gian | 30–37 | 37 | [1315, 835, 1465, 898] | Kiểm kích thước theo nhiều frame |
| M06 | trung gian | 30–37 | 37 | [1158, 844, 1361, 919] | Identity và heading qua đoạn |
| M07 | trung gian | 54–61 | 61 | [1577, 844, 1903, 979] | Đối chiếu ảnh trong cụm xe |
| H01 | chẩn đoán | 6–15 | 15 | [0, 831, 76, 904] | Identity ở đoạn thiếu bản ghi |
| H02 | chẩn đoán | 5–14 | 14 | [31, 837, 118, 890] | Phân biệt che/thưa và fragmentation |
| H03 | chẩn đoán | 25–34 | 32 | [536, 844, 601, 886] | Kiểm gap mà không đoán lại identity |
| H04 | chẩn đoán | 45–54 | 54 | [519, 840, 589, 883] | Giữ hoặc kết thúc track theo evidence |
| H05 | chẩn đoán | 48–57 | 57 | [1042, 832, 1125, 885] | Dimension và giới hạn ảnh ở xa |
| H06 | chẩn đoán | 36–45 | 45 | [701, 836, 766, 896] | Motion, heading và nhu cầu thêm keyframe |

Phần lớn người làm được B01 và 4–6 case sau J01; không ai phải làm hết. Ghi vào phiếu: case nào ứng với track ID nào trong task practice.

Trong task practice, QC sẽ báo `fragmentation_suspect` ở đầu/cuối gần như mọi case vì track bắt đầu giữa sequence. Đó là do cách cắt case, không phải lỗi; chỉ cần ghi một dòng xác nhận trong phiếu.
