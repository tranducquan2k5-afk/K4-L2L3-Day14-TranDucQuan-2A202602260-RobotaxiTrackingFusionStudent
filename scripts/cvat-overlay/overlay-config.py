#!/usr/bin/env python3
"""Build the two files overlay.sh copies into the local cvat_ui container.

    overlay-config.py config --calib private/calib-diagnostic.json --frames private/frame-maps --out config.json
    overlay-config.py nginx --stock stock.conf --out default.conf

config: the calibration, a version for it (file name + sha256), the capture timestamps of the
recording it belongs to (the plugin draws only on those point clouds) and which context image
shows which calibrated camera.
nginx: the cvat_ui image's own default.conf plus the plugin <script> tag and the overlay
locations, so the overlay follows whatever CVAT version the learner runs.

Standard library only: it runs before the lab's Python requirements are installed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
LOCATIONS = HERE / "nginx-locations.conf"
SCRIPT_TAG = '<script defer src="/d14-overlay/d14-projection-overlay.js"></script></head>'
DEFAULT_CAMERAS = {"image_1": "CAM_P_F"}
# point-cloud file names of the recording are capture timestamps (seconds-nanoseconds); a
# generic name such as 000001 could belong to any dataset and must never bind the calibration
ITEM_ID = re.compile(r"\d{10}-\d{9}")
CONTEXT_IMAGE = re.compile(r"image_\d+")


class ConfigError(ValueError):
    pass


def csv_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("*.csv")) if path.is_dir() else [path])
    if not files:
        raise ConfigError(f"no frame-map CSV under {', '.join(map(str, paths))}")
    return files


def read_frames(paths: list[Path]) -> list[str]:
    """Union of the item_id column of every frame map (cases overlap, so repeats are fine)."""
    frames: set[str] = set()
    for path in csv_files(paths):
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if "item_id" not in (reader.fieldnames or []):
                raise ConfigError(f"{path}: no item_id column")
            for line, row in enumerate(reader, start=2):
                item = (row["item_id"] or "").strip()
                if not ITEM_ID.fullmatch(item):
                    raise ConfigError(f"{path}:{line}: item_id must be a capture timestamp like "
                                      f"1700000000-099741459, got {item!r}")
                frames.add(item)
    if not frames:
        raise ConfigError("frame maps list no item_id")
    return sorted(frames)


def matrix(value, rows: int, cols: tuple[int, ...], what: str) -> None:
    ok = (isinstance(value, list) and len(value) in (rows,) + ((4,) if rows == 3 and 4 in cols else ())
          and all(isinstance(r, list) and len(r) in cols
                  and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r)
                  for r in value))
    if not ok:
        raise ConfigError(f"{what} must be a numeric {rows}x{'/'.join(map(str, cols))} matrix")


def check_calibration(calib: dict, cameras: dict[str, str]) -> None:
    """Only what the browser projection reads; cvat3d_fusion.Calib.from_json has the same shape."""
    frame = str(calib.get("pcd_frame", "lidar")).lower()
    if frame not in ("lidar", "ego"):
        raise ConfigError(f'pcd_frame must be "lidar" or "ego", got {frame!r}')
    if frame == "lidar":
        matrix((calib.get("lidar") or {}).get("sensor2ego"), 3, (4,), "lidar.sensor2ego")
    known = calib.get("cameras") or {}
    for key, name in cameras.items():
        if not CONTEXT_IMAGE.fullmatch(key):
            raise ConfigError(f"context image key must look like image_1, got {key!r}")
        cam = known.get(name)
        if cam is None:
            raise ConfigError(f"camera {name!r} (for {key}) is not in the calibration")
        matrix(cam.get("K"), 3, (3,), f"{name}.K")
        matrix(cam.get("ego2cam"), 3, (4,), f"{name}.ego2cam")
        size = cam.get("image_size")
        if not (isinstance(size, list) and len(size) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in size)):
            raise ConfigError(f"{name}.image_size must be [width, height] in pixels")
        dist = cam.get("dist", [])
        if not isinstance(dist, list) or len(dist) > 5 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in dist):
            # the projection is pinhole + five Brown-Conrady terms; fisheye or 8-term
            # profiles would be drawn silently wrong
            raise ConfigError(f"{name}.dist must hold at most five numbers (k1 k2 p1 p2 k3)")


def build_config(calib_path: Path, frame_paths: list[Path], cameras: dict[str, str]) -> dict:
    raw = calib_path.read_bytes()
    try:
        calib = json.loads(raw)
    except ValueError as e:
        raise ConfigError(f"{calib_path}: not JSON ({e})") from None
    if not isinstance(calib, dict):
        raise ConfigError(f"{calib_path}: expected a JSON object")
    if not cameras:
        raise ConfigError("no context image is mapped to a camera")
    check_calibration(calib, cameras)
    return {
        "calibration_version": {"file": calib_path.name, "sha256": hashlib.sha256(raw).hexdigest()},
        "frames": read_frames(frame_paths),
        "cameras": cameras,
        "calibration": calib,
    }


def block_end(conf: str, open_brace: int) -> int | None:
    """Index of the brace closing the block opened at `open_brace`; skips comments and quotes."""
    depth, i = 0, open_brace
    while i < len(conf):
        c = conf[i]
        if c == "#" and (i == 0 or conf[i - 1] in " \t\n;{}"):
            i = conf.find("\n", i)
            if i < 0:
                return None
        elif c in "\"'":
            i += 1
            while i < len(conf) and conf[i] != c:
                i += 2 if conf[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def build_nginx(stock: str, locations: str) -> str:
    """Insert the script tag into `location /` and the overlay locations at the end of the server."""
    roots = list(re.finditer(r"^([ \t]*)location / \{[ \t]*\n", stock, re.M))
    servers = list(re.finditer(r"^[ \t]*server[ \t]*\{", stock, re.M))
    end = block_end(stock, servers[0].end() - 1) if len(servers) == 1 else None
    # anything but comments after the server block (another block, a directive) is a shape this
    # was not written for: refuse instead of guessing where the locations belong
    if (len(roots) != 1 or end is None or not servers[0].end() < roots[0].start() < end
            or not re.fullmatch(r"(\s|#[^\n]*)*", stock[end + 1:])
            or re.search(r"^[ \t]*sub_filter\b", stock, re.M)):
        raise ConfigError("the cvat_ui nginx config has an unexpected shape; overlay not installed")
    indent = roots[0].group(1) + "    "
    inject = f"{indent}sub_filter '</head>' '{SCRIPT_TAG}';\n{indent}sub_filter_once on;\n"
    return (stock[:roots[0].end()] + inject + stock[roots[0].end():end].rstrip(" \t")
            + "\n" + locations + stock[end:])


def write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("--calib", type=Path, required=True)
    c.add_argument("--frames", type=Path, nargs="+", required=True,
                   help="frame-map CSV files or directories of them (item_id column)")
    c.add_argument("--cameras", default=json.dumps(DEFAULT_CAMERAS),
                   help='JSON: context image -> calibrated camera, default %(default)s')
    c.add_argument("--out", type=Path, required=True)
    n = sub.add_parser("nginx")
    n.add_argument("--stock", type=Path, required=True)
    n.add_argument("--out", type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        if a.cmd == "config":
            try:
                cameras = json.loads(a.cameras)
            except ValueError:
                raise ConfigError(f"--cameras is not JSON: {a.cameras!r}") from None
            if not isinstance(cameras, dict) or not all(isinstance(v, str) for v in cameras.values()):
                raise ConfigError('--cameras must map context images to camera names, e.g. {"image_1": "CAM_P_F"}')
            cfg = build_config(a.calib, a.frames, cameras)
            write_private(a.out, json.dumps(cfg))
            v = cfg["calibration_version"]
            print(f"config: {len(cfg['frames'])} frames, cameras {cfg['cameras']}, "
                  f"calibration {v['file']} sha256 {v['sha256'][:12]}")
        else:
            a.out.write_text(build_nginx(a.stock.read_text(), LOCATIONS.read_text()))
    except (ConfigError, OSError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
