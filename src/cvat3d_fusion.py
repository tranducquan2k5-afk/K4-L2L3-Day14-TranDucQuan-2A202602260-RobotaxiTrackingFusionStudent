"""
cvat3d_fusion.py — chieu cuboid 3D tu CVAT len anh camera + QC track theo thoi gian.

Lab 14 (Robotaxi B - Across Time & Sensors). Luong lab hien tai chieu 3D -> 2D
offline bang profile calibration rieng, roi dua anh overlay vao task review 2D.

Phu thuoc: numpy, pillow.  (Khong can OpenCV.)

Quy uoc du lieu
---------------
* Cuboid CVAT 3D = 16 so:  [x, y, z, rx, ry, rz, L, W, H, 0 x 7]
    - x,y,z : tam box, trong frame cua file .pcd (o rig nay la LIDAR_TOP), Z huong len
    - rx,ry,rz : Euler RADIAN, thu tu three.js 'XYZ'  =>  R = Rx(rx) @ Ry(ry) @ Rz(rz)
    - L,W,H : kich thuoc doc truc X, Y, Z cua box  (Length/Width/Height trong sidebar CVAT)
* Datumaro 3D export: annotation type "cuboid_3d" voi position / rotation / scale
  va attributes {track_id, keyframe, outside}.
* calib.json:
    {
      "lidar":   {"sensor2ego": [[4x4]]},
      "cameras": {"CAM_P_F": {"K": [[3x3]], "dist": [k1,k2,p1,p2,k3],
                              "ego2cam": [[4x4]], "image_size": [W, H]}}
    }
  LIDAR dung sensor->ego; CAMERA dung ego->camera (nhan thang, KHONG lay nghich dao),
  dung nhu slide 22 va 30 cua bai giang.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import struct
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np

NEAR_Z = 0.1  # m, mat phang near; diem co Z <= NEAR_Z khong the chieu
EDGE_STEPS = 16  # so doan con moi canh cuboid: meo ong kinh be canh thang thanh duong cong
FRAME_MAP_COLUMNS = ("cvat_frame", "item_id", "pcd_path", "image_path", "camera",
                     "timestamp_relation")


def sha256(path: str | Path) -> str:
    """Hash a file, or a deterministic directory tree of exported JSON files."""
    path = Path(path)
    digest = hashlib.sha256()
    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    if not files:
        raise ValueError("No annotation JSON files")
    for file in files:
        if path.is_dir():
            digest.update(file.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 1. Hinh hoc cuboid
# --------------------------------------------------------------------------- #
def euler_xyz_to_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """R = Rx @ Ry @ Rz  (three.js Euler order 'XYZ' — dung dung cua CVAT canvas3d)."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


# thu tu 8 goc: 0-3 = mat duoi (z-), 4-7 = mat tren (z+); 0,1,5,4 = mat TRUOC (x+)
_UNIT = np.array(
    [
        [+0.5, -0.5, -0.5], [+0.5, +0.5, -0.5], [-0.5, +0.5, -0.5], [-0.5, -0.5, -0.5],
        [+0.5, -0.5, +0.5], [+0.5, +0.5, +0.5], [-0.5, +0.5, +0.5], [-0.5, -0.5, +0.5],
    ]
)
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0),
         (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7)]
FRONT_FACE = [(0, 1), (1, 5), (5, 4), (4, 0)]


def box_corners(position, rotation, scale) -> np.ndarray:
    """8 goc cuboid trong frame LiDAR. -> (8, 3)"""
    R = euler_xyz_to_matrix(*rotation)
    return (_UNIT * np.asarray(scale, float)) @ R.T + np.asarray(position, float)


def transform(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Ap ma tran 4x4 homogeneous len (N,3)."""
    p = np.asarray(points, float).reshape(-1, 3)
    return p @ T[:3, :3].T + T[:3, 3]


# --------------------------------------------------------------------------- #
# 2. Calibration + phep chieu
# --------------------------------------------------------------------------- #
@dataclass
class CameraCalib:
    name: str
    K: np.ndarray
    dist: np.ndarray
    ego2cam: np.ndarray
    image_size: tuple[int, int]

    @property
    def fx(self): return float(self.K[0, 0])

    @property
    def fy(self): return float(self.K[1, 1])

    @property
    def cx(self): return float(self.K[0, 2])

    @property
    def cy(self): return float(self.K[1, 2])

    def hfov_deg(self) -> float:
        return math.degrees(2 * math.atan(self.image_size[0] / (2 * self.fx)))

    @cached_property
    def max_r2(self) -> float:
        """Gioi han (X/Z)^2 + (Y/Z)^2 ma mo hinh meo con dung, xem radial_fold_r2.

        Tinh mot lan roi cache: khong sua `dist` sau khi tao camera (muon calib khac thi
        tao CameraCalib moi)."""
        return radial_fold_r2(self.dist)


def radial_fold_r2(dist) -> float:
    """r^2 lon nhat (toa do chuan hoa, chua meo) ma meo radial con don dieu.

    Da thuc r_d = r (1 + k1 r^2 + k2 r^4 + k3 r^6) chi fit trong FOV cua anh. Qua diem
    dao chieu, r_d giam lai: diem nam ngoai FOV bi "gap" nguoc vao giua anh. Diem co
    r^2 vuot gioi han nay coi nhu khong chieu duoc, giong diem sau camera.
    Tim nghiem duong nho nhat cua dr_d/dr = 1 + 3k1 s + 5k2 s^2 + 7k3 s^3 (s = r^2);
    inf neu khong co. Chi dung phep +-*/ va sqrt de ban JS cho cung ket qua.
    """
    d = [float(v) for v in list(dist)[:5]] + [0.0] * 5
    c = [1.0, 3.0 * d[0], 5.0 * d[1], 7.0 * d[4]]
    deg = max(i for i in range(4) if c[i] != 0.0)
    if deg == 0:
        return math.inf

    def g(s):
        return c[0] + s * (c[1] + s * (c[2] + s * c[3]))

    # moi nghiem thuc deu <= can Cauchy; diem cuc tri cua g chia [0, can] thanh cac
    # khoang don dieu, moi khoang co toi da mot nghiem
    bound = 1.0 + max(abs(c[i]) for i in range(deg)) / abs(c[deg])
    crit = []
    qa, qb, qc = 3.0 * c[3], 2.0 * c[2], c[1]
    if qa != 0.0:
        disc = qb * qb - 4.0 * qa * qc
        if disc >= 0.0:
            sq = math.sqrt(disc)
            crit = [(-qb - sq) / (2.0 * qa), (-qb + sq) / (2.0 * qa)]
    elif qb != 0.0:
        crit = [-qc / qb]
    knots = sorted([0.0, bound] + [s for s in crit if 0.0 < s < bound])
    for lo, hi in zip(knots, knots[1:]):
        if g(hi) > 0.0:
            continue  # g(0) = 1 > 0 va g don dieu tren khoang: chua co nghiem
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if mid <= lo or mid >= hi:
                break
            if g(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        return lo
    return math.inf


@dataclass
class Calib:
    sensor2ego: np.ndarray
    cameras: dict[str, CameraCalib]
    pcd_frame: str = "lidar"   # "lidar" = .pcd o frame LIDAR_TOP | "ego" = .pcd da o frame xe

    @staticmethod
    def from_json(path: str) -> "Calib":
        """pcd_frame (tuy chon, mac dinh "lidar"):

        * "lidar": file .pcd lay LIDAR_TOP lam goc  ->  nhan sensor2ego roi moi sang camera
          (dung voi Ngay 14, slide 23).
        * "ego": file .pcd da o frame xe, mat duong ~ z = 0  ->  BO QUA sensor2ego
          (dung voi pipeline pre-label Ngay 13, slide 44). Dat sai cho nay thi moi box lech
          dung bang chieu cao lap LiDAR — xem muc "doi chieu Ngay 13 / Ngay 14".
        """
        with open(path) as f:
            raw = json.load(f)
        s2e = np.asarray(raw["lidar"]["sensor2ego"], float)
        frame = str(raw.get("pcd_frame", "lidar")).lower()
        if frame not in ("lidar", "ego"):
            raise ValueError(f'pcd_frame phai la "lidar" hoac "ego", nhan duoc {frame!r}')
        cams = {}
        for name, c in raw["cameras"].items():
            cams[name] = CameraCalib(
                name=name,
                K=np.asarray(c["K"], float),
                dist=np.asarray(c.get("dist", [0, 0, 0, 0, 0]), float),
                ego2cam=np.asarray(c["ego2cam"], float),
                image_size=tuple(int(v) for v in c.get("image_size", (1920, 1080))),
            )
        return Calib(sensor2ego=s2e, cameras=cams, pcd_frame=frame)

    def to_ego(self, points: np.ndarray) -> np.ndarray:
        """Dua toa do trong file .pcd ve frame xe (ego)."""
        return np.asarray(points, float).reshape(-1, 3) if self.pcd_frame == "ego" \
            else transform(points, self.sensor2ego)

    def lidar_to_cam(self, points: np.ndarray, camera: str) -> np.ndarray:
        """.pcd -> ego -> camera (3 buoc cua slide 30, buoc 3 la chieu)."""
        return transform(self.to_ego(points), self.cameras[camera].ego2cam)


def _distort_to_pixel(xn: np.ndarray, yn: np.ndarray, cam: CameraCalib) -> np.ndarray:
    d = np.zeros(5)
    d[: min(5, len(cam.dist))] = cam.dist[:5]
    k1, k2, p1, p2, k3 = d
    r2 = xn * xn + yn * yn
    radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    xd = xn * radial + 2 * p1 * xn * yn + p2 * (r2 + 2 * xn * xn)
    yd = yn * radial + p1 * (r2 + 2 * yn * yn) + 2 * p2 * xn * yn
    return np.stack([cam.fx * xd + cam.cx, cam.fy * yd + cam.cy], axis=1)


def project(points_cam: np.ndarray, cam: CameraCalib) -> tuple[np.ndarray, np.ndarray]:
    """Pinhole + meo Brown-Conrady. -> (uv (N,2), valid (N,) bool).

    valid: Z > NEAR_Z va nam trong vung mo hinh meo con dung (cam.max_r2). uv cua diem
    khong valid la vo nghia, khong duoc ve.
    """
    p = np.asarray(points_cam, float).reshape(-1, 3)
    front = p[:, 2] > NEAR_Z
    z = np.where(front, p[:, 2], 1.0)
    xn, yn = p[:, 0] / z, p[:, 1] / z
    valid = front & (xn * xn + yn * yn <= cam.max_r2)
    return _distort_to_pixel(xn, yn, cam), valid


def clip_edge_view(a, b, max_r2: float = math.inf) -> tuple[float, float] | None:
    """Doan [t0, t1] cua canh a + t (b - a) nam trong vung chieu duoc.

    Vung chieu duoc: Z > NEAR_Z va X^2 + Y^2 <= max_r2 Z^2 (non cua mo hinh meo). Vung
    nay loi nen giao voi mot canh thang chi la mot doan. None neu canh nam ngoai.
    """
    ax, ay, az = (float(v) for v in a)
    bx, by, bz = (float(v) for v in b)
    if az <= NEAR_Z and bz <= NEAR_Z:
        return None
    t0, t1 = 0.0, 1.0
    if az <= NEAR_Z or bz <= NEAR_Z:
        t = (NEAR_Z - az) / (bz - az)
        if az > NEAR_Z:
            t1 = t
        else:
            t0 = t
    if math.isinf(max_r2):
        return t0, t1
    # q(t) = X^2 + Y^2 - max_r2 Z^2 <= 0 tren canh
    dx, dy, dz = bx - ax, by - ay, bz - az
    qa = dx * dx + dy * dy - max_r2 * dz * dz
    qb = 2.0 * (ax * dx + ay * dy - max_r2 * az * dz)
    qc = ax * ax + ay * ay - max_r2 * az * az
    roots = []
    if qa != 0.0:
        disc = qb * qb - 4.0 * qa * qc
        if disc > 0.0:
            sq = math.sqrt(disc)
            h = -0.5 * (qb + sq) if qb >= 0.0 else -0.5 * (qb - sq)
            roots = [h / qa, qc / h]
    elif qb != 0.0:
        roots = [-qc / qb]
    knots = sorted([t0, t1] + [r for r in roots if t0 < r < t1])
    inside = [(lo, hi) for lo, hi in zip(knots, knots[1:])
              if (qa * (0.5 * (lo + hi)) + qb) * (0.5 * (lo + hi)) + qc <= 0.0]
    if not inside or inside[-1][1] <= inside[0][0]:
        return None
    return inside[0][0], inside[-1][1]


def edge_polyline(a, b, cam: CameraCalib) -> np.ndarray | None:
    """Phan chieu duoc cua canh a-b (frame camera) -> (EDGE_STEPS + 1, 2) diem anh."""
    span = clip_edge_view(a, b, cam.max_r2)
    if span is None:
        return None
    t0, t1 = span
    a, b = np.asarray(a, float), np.asarray(b, float)
    ts = np.array([t0 + (t1 - t0) * k / EDGE_STEPS for k in range(EDGE_STEPS + 1)])
    p = a + ts[:, None] * (b - a)
    # diem cat nam tren bien vung chieu duoc; khong qua project() de sai so lam tron
    # o Z = NEAR_Z khong bien no thanh "sau camera"
    return _distort_to_pixel(p[:, 0] / p[:, 2], p[:, 1] / p[:, 2], cam)


# --------------------------------------------------------------------------- #
# 3. Doc export Datumaro 3D cua CVAT
# --------------------------------------------------------------------------- #
@dataclass
class Box3D:
    track_id: int | None
    label: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    scale: tuple[float, float, float]   # (L, W, H)
    keyframe: bool = False
    outside: bool = False
    attributes: dict = field(default_factory=dict)

    @property
    def yaw(self) -> float:
        return self.rotation[2]

    @property
    def range_m(self) -> float:
        x, y, z = self.position
        return math.sqrt(x * x + y * y + z * z)


@dataclass
class Frame:
    index: int
    item_id: str
    boxes: list[Box3D]


def _frame_index(item: dict) -> int:
    for key in ("frame", "frame_index"):
        v = (item.get("attr") or {}).get(key, (item.get("attributes") or {}).get(key))
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 1_000_000:
            return v
    raise ValueError("Datumaro item has no trusted local frame; provide --frame-map")


def load_frame_map(path: str | Path) -> list[dict]:
    """Read the private runtime map; locator-only maps cannot drive overlays."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FRAME_MAP_COLUMNS:
            raise ValueError("Runtime frame-map needs cvat_frame,item_id,pcd_path,image_path,camera,timestamp_relation; create a private full map from docs/templates/frame-map.csv")
        rows = list(reader)
    if not rows:
        raise ValueError("frame-map has no rows")
    seen_pair, by_item, by_frame, by_image = set(), {}, {}, {}
    for row in rows:
        if None in row or any(not row.get(key, "").strip() for key in FRAME_MAP_COLUMNS):
            raise ValueError("frame-map has missing fields")
        frame_text = row["cvat_frame"]
        if not frame_text.isdecimal() or int(frame_text) >= 1_000_000:
            raise ValueError("frame-map cvat_frame must be a local frame index")
        frame = int(frame_text)
        item_id = row["item_id"]
        pair = (frame, row["camera"])
        if pair in seen_pair:
            raise ValueError("duplicate (cvat_frame,camera) in frame-map")
        seen_pair.add(pair)
        pcd = (path.parent / row["pcd_path"]).resolve()
        image = (path.parent / row["image_path"]).resolve()
        if by_item.get(item_id, frame) != frame or by_frame.get(frame, item_id) != item_id:
            raise ValueError("frame-map item_id and cvat_frame must be one-to-one")
        by_item[item_id], by_frame[frame] = frame, item_id
        row["cvat_frame"] = frame
        row["pcd_path"] = str(pcd)
        row["image_path"] = str(image)
        if image in by_image and by_image[image] != pair:
            raise ValueError("ambiguous image reused for different frame/camera")
        by_image[image] = pair
    pcd_by_frame = {}
    for row in rows:
        frame, pcd = row["cvat_frame"], row["pcd_path"]
        if frame in pcd_by_frame and pcd_by_frame[frame] != pcd:
            raise ValueError("frame-map PCD differs across camera rows")
        pcd_by_frame[frame] = pcd
    return rows


def load_datumaro3d(path: str, frame_map: str | None = None) -> list[Frame]:
    """Doc Datumaro 3D (file .json, hoac thu muc/zip da giai nen co annotations/*.json)."""
    files: list[str] = []
    if os.path.isdir(path):
        for root, _dirs, names in os.walk(path):
            files += [os.path.join(root, n) for n in names
                      if n.endswith(".json") and "annotations" in root.replace("\\", "/")]
        if not files:
            for root, _dirs, names in os.walk(path):
                files += [os.path.join(root, n) for n in names if n.endswith(".json")]
    else:
        files = [path]
    if not files:
        raise FileNotFoundError(f"khong thay file annotation json trong {path}")

    map_rows = load_frame_map(frame_map) if frame_map else []
    frame_by_item = {row["item_id"]: row["cvat_frame"] for row in map_rows}
    label_names: list[str] = []
    frames: list[Frame] = []
    seen_items, seen_frames = set(), set()
    for fp in sorted(files):
        with open(fp) as f:
            data = json.load(f)
        if not isinstance(data, dict) or any(key in data for key in ("tracks", "shapes", "tags")):
            raise ValueError("Native CVAT JSON unsupported; Export Datumaro 3D 1.0")
        cats = (data.get("categories") or {}).get("label", {}).get("labels", [])
        items = data.get("items")
        if not cats or not isinstance(items, list) or not items:
            raise ValueError("Expected Datumaro 3D 1.0 JSON with categories and nonempty items")
        label_names = [c["name"] for c in cats]
        for item in items:
            item_id = str(item["id"])
            if item_id in seen_items:
                raise ValueError("duplicate Datumaro item_id")
            seen_items.add(item_id)
            if frame_map:
                if item_id not in frame_by_item:
                    raise ValueError(f"Datumaro item_id absent from frame-map: {item_id}")
                index = frame_by_item[item_id]
                explicit = (item.get("attr") or {}).get("frame", (item.get("attributes") or {}).get("frame"))
                if explicit is not None and explicit != index:
                    raise ValueError("Datumaro local frame differs from frame-map")
            else:
                index = _frame_index(item)
            if index in seen_frames:
                raise ValueError("duplicate local frame index in Datumaro export")
            seen_frames.add(index)
            boxes = []
            for ann in item.get("annotations", []):
                if ann.get("type") != "cuboid_3d":
                    continue
                attrs = dict(ann.get("attributes") or {})
                lbl = ann.get("label_id")
                boxes.append(
                    Box3D(
                        track_id=attrs.pop("track_id", ann.get("id")),
                        label=label_names[lbl] if isinstance(lbl, int) and lbl < len(label_names)
                        else str(lbl),
                        position=tuple(ann["position"]),
                        rotation=tuple(ann["rotation"]),
                        scale=tuple(ann["scale"]),
                        keyframe=bool(attrs.pop("keyframe", False)),
                        outside=bool(attrs.pop("outside", False)),
                        attributes=attrs,
                    )
                )
            frames.append(Frame(index=index, item_id=item_id,
                                boxes=boxes))
    frames.sort(key=lambda fr: fr.index)
    return frames


# --------------------------------------------------------------------------- #
# 4. Doc .pcd toi gian (ascii + binary, lay x y z)
# --------------------------------------------------------------------------- #
def read_pcd_xyz(path: str, max_points: int = 400_000) -> np.ndarray:
    with open(path, "rb") as f:
        header, line = {}, b""
        while True:
            line = f.readline()
            if not line:
                raise ValueError("PCD header khong hop le")
            txt = line.decode("ascii", "replace").strip()
            if txt.startswith("#") or not txt:
                continue
            key, _, val = txt.partition(" ")
            header[key.upper()] = val
            if key.upper() == "DATA":
                break
        fields = header["FIELDS"].split()
        sizes = [int(v) for v in header["SIZE"].split()]
        types = header["TYPE"].split()
        counts = [int(v) for v in header.get("COUNT", " ".join("1" * len(fields))).split()]
        n = int(header["POINTS"]) if "POINTS" in header else int(header["WIDTH"]) * int(header["HEIGHT"])
        fmt = header["DATA"].strip().lower()

        if fmt == "ascii":
            rows = []
            idx = [fields.index(a) for a in ("x", "y", "z")]
            for ln in f:
                parts = ln.split()
                if len(parts) < 3:
                    continue
                rows.append([float(parts[i]) for i in idx])
                if len(rows) >= max_points:
                    break
            return np.asarray(rows, float)

        if fmt != "binary":
            raise ValueError(f"DATA {fmt} chua ho tro (hay dung ascii hoac binary)")
        np_t = {("F", 4): "f4", ("F", 8): "f8", ("U", 1): "u1", ("U", 2): "u2",
                ("U", 4): "u4", ("I", 1): "i1", ("I", 2): "i2", ("I", 4): "i4"}
        dtype = np.dtype([(fn, np_t[(t, s)], c) if c > 1 else (fn, np_t[(t, s)])
                          for fn, s, t, c in zip(fields, sizes, types, counts)])
        buf = f.read(dtype.itemsize * n)
        arr = np.frombuffer(buf, dtype=dtype, count=len(buf) // dtype.itemsize)
        pts = np.stack([arr["x"], arr["y"], arr["z"]], axis=1).astype(float)
        pts = pts[np.isfinite(pts).all(axis=1)]
        if len(pts) > max_points:
            pts = pts[:: max(1, len(pts) // max_points)]
        return pts


# --------------------------------------------------------------------------- #
# 5. Ve overlay
# --------------------------------------------------------------------------- #
def _color_for(track_id) -> tuple[int, int, int]:
    h = (int(track_id) * 2654435761) % 360 if track_id is not None else 0
    c, x = 255, int(255 * (1 - abs((h / 60) % 2 - 1)))
    table = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)]
    return table[int(h // 60) % 6]


def render_overlay(
    boxes: list[Box3D],
    calib: Calib,
    camera: str,
    image_path: str | None = None,
    points: np.ndarray | None = None,
    point_stride: int = 3,
    calib_points: Calib | None = None,
    strict_media: bool = False,
):
    """Tra ve (PIL.Image, list[dict] thong tin moi box).

    calib_points: chi dung cho demo loi calibration — ve point cloud bang calib DUNG
    (dong vai 'anh thuc') va ve cuboid bang calib `calib` (co the sai), de thay
    dau hieu 'moi vat lech cung mot phia' nhu slide 27.
    """
    from PIL import Image, ImageDraw

    cam = calib.cameras[camera]
    W, H = cam.image_size
    if strict_media and (not image_path or not os.path.isfile(image_path)):
        raise ValueError("camera image missing")
    if image_path and os.path.exists(image_path):
        img = Image.open(image_path).convert("RGB")
        if img.size != (W, H):
            if strict_media:
                raise ValueError("camera image size differs from calibration")
            img = img.resize((W, H))
    else:
        img = Image.new("RGB", (W, H), (26, 28, 32))
    draw = ImageDraw.Draw(img, "RGBA")

    # 5a. point cloud to theo do sau (nhu slide 26 cua bai giang)
    if points is not None and len(points):
        pc = (calib_points or calib).lidar_to_cam(points[::point_stride], camera)
        uv, ok = project(pc, cam)
        inside = ok & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
        uvi, zi = uv[inside], pc[inside, 2]
        if len(uvi):
            t = np.clip(zi / 60.0, 0, 1)
            for (u, v), tt in zip(uvi.astype(int), t):
                col = (int(255 * (1 - tt)), int(90 + 110 * (1 - abs(tt - 0.5) * 2)), int(255 * tt))
                draw.point((u, v), fill=col)

    # 5b. cuboid
    info = []
    for b in boxes:
        if b.outside:
            continue
        corners_cam = calib.lidar_to_cam(box_corners(b.position, b.rotation, b.scale), camera)
        uv, ok = project(corners_cam, cam)
        n_front = int((corners_cam[:, 2] > NEAR_Z).sum())
        in_img = int((ok & (uv[:, 0] >= 0) & (uv[:, 0] < W)
                      & (uv[:, 1] >= 0) & (uv[:, 1] < H)).sum())
        status = "out_of_fov" if in_img == 0 else (
            "fully_visible" if in_img == 8 else "partial")
        rec = {
            "track_id": b.track_id, "label": b.label, "status": status,
            "corners_in_front": n_front, "corners_in_image": in_img,
            "range_m": round(b.range_m, 2), "depth_cam_m": round(float(corners_cam[:, 2].mean()), 2),
            "L": b.scale[0], "W": b.scale[1], "H": b.scale[2],
            "yaw_deg": round(math.degrees(b.yaw), 2), "keyframe": b.keyframe,
        }
        if status == "out_of_fov":
            rec.update(bbox2d=None)
            info.append(rec)
            continue

        col = _color_for(b.track_id)
        drawn = [uv[ok]]
        for i, j in EDGES:
            pts = edge_polyline(corners_cam[i], corners_cam[j], cam)
            if pts is None:
                continue
            width = 3 if (i, j) in FRONT_FACE or (j, i) in FRONT_FACE else 2
            draw.line([tuple(p) for p in pts], fill=col + (255,), width=width, joint="curve")
            drawn.append(pts)
        # mat truoc to mo de thay heading; vung chieu duoc loi nen 4 goc hop le thi
        # ca mat hop le
        ring = [edge_polyline(corners_cam[i], corners_cam[j], cam) for i, j in FRONT_FACE]
        if ok[[0, 1, 5, 4]].all() and all(r is not None for r in ring):
            draw.polygon([tuple(p) for p in np.concatenate([r[:-1] for r in ring])],
                         fill=col + (60,))

        # bbox theo phan da ve (gom ca doan bi cat), khong chi theo cac goc
        pts = np.concatenate(drawn)
        u0, v0 = float(np.clip(pts[:, 0].min(), 0, W - 1)), float(np.clip(pts[:, 1].min(), 0, H - 1))
        u1, v1 = float(np.clip(pts[:, 0].max(), 0, W - 1)), float(np.clip(pts[:, 1].max(), 0, H - 1))
        rec["bbox2d"] = [round(u0, 1), round(v0, 1), round(u1, 1), round(v1, 1)]
        draw.text((u0 + 3, max(0, v0 - 14)),
                  f"#{b.track_id} {b.label} {rec['depth_cam_m']:.0f}m", fill=col + (255,))
        info.append(rec)
    return img, info


# --------------------------------------------------------------------------- #
# 6. QC track theo thoi gian (5 loi cua bai giang)
# --------------------------------------------------------------------------- #
def qc_tracks(frames: list[Frame], dim_tol: float = 0.05, yaw_step_deg: float = 25.0,
              jump_m: float = 3.0, close_m: float = 2.5):
    by_track: dict = {}
    for fr in frames:
        for b in fr.boxes:
            if b.outside:
                continue
            by_track.setdefault(b.track_id, []).append((fr.index, b))
    all_idx = [fr.index for fr in frames]
    f_min, f_max = (min(all_idx), max(all_idx)) if all_idx else (0, 0)

    summary, flags = [], []
    for tid, seq in sorted(by_track.items(), key=lambda kv: (kv[0] is None, kv[0])):
        seq.sort(key=lambda t: t[0])
        idx = [i for i, _ in seq]
        L = np.array([b.scale[0] for _, b in seq])
        Wd = np.array([b.scale[1] for _, b in seq])
        Hd = np.array([b.scale[2] for _, b in seq])
        pos = np.array([b.position for _, b in seq])
        yaw = np.degrees(np.unwrap([b.yaw for _, b in seq]))
        rng = np.array([b.range_m for _, b in seq])
        n_kf = sum(1 for _, b in seq if b.keyframe)

        def drift(a):
            return float((a.max() - a.min()) / max(a.max(), 1e-6))

        dL, dW, dH = drift(L), drift(Wd), drift(Hd)
        dyaw = np.abs(np.diff(yaw)) if len(yaw) > 1 else np.array([0.0])
        step = np.linalg.norm(np.diff(pos, axis=0), axis=1) if len(pos) > 1 else np.array([0.0])
        gaps = [(a, b) for a, b in zip(idx, idx[1:]) if b - a > 1]

        summary.append({
            "track_id": tid, "label": seq[0][1].label, "n_frames": len(seq), "n_keyframes": n_kf,
            "frame_first": idx[0], "frame_last": idx[-1],
            "L_med": round(float(np.median(L)), 3), "L_min": round(float(L.min()), 3),
            "L_max": round(float(L.max()), 3), "L_drift": round(dL, 4),
            "W_drift": round(dW, 4), "H_drift": round(dH, 4),
            "yaw_step_max_deg": round(float(dyaw.max()), 2),
            "pos_step_max_m": round(float(step.max()), 2),
            "range_min_m": round(float(rng.min()), 1), "range_max_m": round(float(rng.max()), 1),
            "n_gaps": len(gaps),
        })

        def add(kind, frame, detail):
            flags.append({"track_id": tid, "frame": frame, "error": kind, "detail": detail})

        for name, d, arr in (("L", dL, L), ("W", dW, Wd), ("H", dH, Hd)):
            if d > dim_tol:
                add("dimension_drift", idx[int(np.argmax(arr))],
                    f"{name}: {arr.min():.2f}..{arr.max():.2f} m ({d*100:.1f}% > {dim_tol*100:.0f}%)")
        for k, dy in enumerate(dyaw):
            if dy > 150:
                add("orientation_flip", idx[k + 1], f"yaw nhay {dy:.0f}deg (~180)")
            elif dy > yaw_step_deg:
                add("orientation_drift", idx[k + 1], f"yaw doi {dy:.0f}deg trong 1 frame")
        for k, s in enumerate(step):
            if s > jump_m:
                add("position_jump", idx[k + 1], f"tam box nhay {s:.1f} m (dau hieu ID switch)")
        if idx[0] > f_min and rng[0] < 60:
            add("fragmentation_suspect", idx[0],
                f"ID xuat hien giua sequence o {rng[0]:.0f} m (khong phai frame dau)")
        if idx[-1] < f_max and rng[-1] < 60:
            add("fragmentation_suspect", idx[-1],
                f"ID ket thuc giua sequence o {rng[-1]:.0f} m")
        for a, b in gaps:
            add("track_gap", a, f"missing frame {a+1}..{b-1}; review image/PCD evidence and the class guideline before deciding visibility")
        if len(seq) > 3 and n_kf and n_kf / len(seq) > 0.9:
            add("no_interpolation", idx[0],
                f"{n_kf}/{len(seq)} frame la keyframe — co the dang ve tay tung frame")

    # ID switch risk: hai track lai gan nhau
    for fr in frames:
        live = [b for b in fr.boxes if not b.outside]
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                d = float(np.linalg.norm(np.subtract(live[i].position, live[j].position)))
                if d < close_m:
                    flags.append({
                        "track_id": f"{live[i].track_id}+{live[j].track_id}", "frame": fr.index,
                        "error": "id_switch_risk",
                        "detail": f"hai track cach nhau {d:.1f} m — kiem tra ID truoc/sau doan nay",
                    })
    return summary, flags


def write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        open(path, "w").close()
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------- #
# 7. Kiem tra calibration bang 1 diem da biet (slide 32)
# --------------------------------------------------------------------------- #
def verify_point(calib: Calib, camera: str, p_lidar, expect_ego=None, expect_cam=None,
                 expect_uv=None, tol=0.15) -> dict:
    p = np.asarray(p_lidar, float).reshape(1, 3)
    ego = calib.to_ego(p)[0]
    camp = transform(ego.reshape(1, 3), calib.cameras[camera].ego2cam)[0]
    uv, ok = project(camp.reshape(1, 3), calib.cameras[camera])
    out = {"lidar": p[0].tolist(), "ego": ego.round(3).tolist(),
           "cam": camp.round(3).tolist(), "uv": uv[0].round(1).tolist(),
           "in_front": bool(camp[2] > NEAR_Z), "projectable": bool(ok[0])}
    for key, exp in (("ego", expect_ego), ("cam", expect_cam), ("uv", expect_uv)):
        if exp is not None:
            err = float(np.abs(np.asarray(out[key]) - np.asarray(exp, float)).max())
            out[f"{key}_err_max"] = round(err, 3)
            out[f"{key}_ok"] = err <= (tol if key != "uv" else max(2.0, tol * 100))
    return out


# --------------------------------------------------------------------------- #
# 8. CLI
# --------------------------------------------------------------------------- #
def _cmd_overlay(a):
    calib = Calib.from_json(a.calib)
    if a.camera not in calib.cameras:
        raise ValueError("camera absent from calibration")
    frames = load_datumaro3d(a.annotations, a.frame_map)
    map_rows = load_frame_map(a.frame_map)
    selected = {row["cvat_frame"]: row for row in map_rows if row["camera"] == a.camera}
    requested = [fr for fr in frames if a.frames is None or fr.index in a.frames]
    if a.frames is not None and set(a.frames) != {fr.index for fr in requested}:
        raise ValueError("requested frame absent from Datumaro export")
    if not requested:
        raise ValueError("no frames selected for overlay")
    from PIL import Image
    for fr in requested:
        row = selected.get(fr.index)
        if row is None or row["item_id"] != fr.item_id:
            raise ValueError("camera frame/item_id missing or mismatched in frame-map")
        if not Path(row["image_path"]).is_file():
            raise ValueError(f"camera image missing for local frame {fr.index}")
        if not Path(row["pcd_path"]).is_file():
            raise ValueError(f"PCD missing for local frame {fr.index}")
        with Image.open(row["image_path"]) as source:
            if source.size != calib.cameras[a.camera].image_size:
                raise ValueError(f"camera image size differs from calibration at local frame {fr.index}")
            source.verify()
    os.makedirs(a.out, exist_ok=True)
    rows = []
    manifest_frames = []
    for fr in requested:
        row = selected[fr.index]
        pts = read_pcd_xyz(row["pcd_path"])
        img, info = render_overlay(fr.boxes, calib, a.camera, row["image_path"], pts,
                                   strict_media=True)
        filename = f"overlay_{fr.index:05d}.jpg"
        output = Path(a.out) / filename
        img.save(output, quality=88)
        manifest_frames.append({"frame": fr.index, "item_id": fr.item_id,
                                "filename": filename, "sha256": sha256(output)})
        for r in info:
            rows.append({"frame": fr.index, **r})
    write_csv([{k: ("" if v is None else v) for k, v in r.items()} for r in rows],
              os.path.join(a.out, "projection.csv"))
    manifest = {"camera": a.camera, "frames": manifest_frames,
                "inputs": {"annotations_sha256": sha256(a.annotations),
                           "calibration_sha256": sha256(a.calib),
                           "frame_map_sha256": sha256(a.frame_map)}}
    with (Path(a.out) / "overlay-manifest.json").open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"{len(requested)} overlay frames, {len(rows)} projected boxes")


def _cmd_qc(a):
    frames = load_datumaro3d(a.annotations, a.frame_map)
    summary, flags = qc_tracks(frames, a.dim_tol, a.yaw_step, a.jump, a.close)
    os.makedirs(a.out, exist_ok=True)
    write_csv(summary, os.path.join(a.out, "qc_tracks.csv"))
    write_csv(flags, os.path.join(a.out, "qc_flags.csv"))
    n_err = {}
    for f in flags:
        n_err[f["error"]] = n_err.get(f["error"], 0) + 1
    print(f"{len(frames)} frame, {len(summary)} track")
    for k in sorted(n_err):
        print(f"  {k:22s} {n_err[k]}")
    if not flags:
        print("  khong co co canh bao nao")


def _cmd_verify(a):
    calib = Calib.from_json(a.calib)
    r = verify_point(calib, a.camera, a.point, a.ego, a.cam, a.uv)
    print(json.dumps(r, indent=2))
    cam = calib.cameras[a.camera]
    print(f"\n{a.camera}: fx={cam.fx:.1f} fy={cam.fy:.1f} cx={cam.cx:.1f} cy={cam.cy:.1f} "
          f"HFOV={cam.hfov_deg():.1f}deg image={cam.image_size}")
    print(f'pcd_frame="{calib.pcd_frame}"'
          + ("  (nhan sensor2ego cua LIDAR_TOP)" if calib.pcd_frame == "lidar"
             else "  (BO QUA sensor2ego — .pcd da o frame xe)"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("overlay", help="chieu cuboid len anh camera")
    o.add_argument("--annotations", required=True, help="Datumaro 3D json / thu muc da giai nen")
    o.add_argument("--calib", required=True)
    o.add_argument("--camera", required=True)
    o.add_argument("--frame-map", required=True, help="private runtime map, full schema")
    o.add_argument("--out", default="overlay_out")
    o.add_argument("--frames", type=int, nargs="*", help="chi lam mot vai frame")
    o.set_defaults(func=_cmd_overlay)

    q = sub.add_parser("qc", help="QC track theo thoi gian")
    q.add_argument("--annotations", required=True)
    q.add_argument("--frame-map", help="private runtime map for timestamp item IDs")
    q.add_argument("--out", default="qc_out")
    q.add_argument("--dim-tol", type=float, default=0.05, dest="dim_tol")
    q.add_argument("--yaw-step", type=float, default=25.0, dest="yaw_step")
    q.add_argument("--jump", type=float, default=3.0)
    q.add_argument("--close", type=float, default=2.5)
    q.set_defaults(func=_cmd_qc)

    v = sub.add_parser("verify", help="kiem tra calib bang 1 diem da biet")
    v.add_argument("--calib", required=True)
    v.add_argument("--camera", required=True)
    v.add_argument("--point", type=float, nargs=3, required=True)
    v.add_argument("--ego", type=float, nargs=3)
    v.add_argument("--cam", type=float, nargs=3)
    v.add_argument("--uv", type=float, nargs=2)
    v.set_defaults(func=_cmd_verify)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
