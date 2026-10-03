"""CVAT projection overlay: config/nginx builder and browser-vs-Python projection parity."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "scripts" / "cvat-overlay"
CALIB = ROOT / "tests" / "fixtures" / "calib-synthetic.json"
FRAME_MAPS = ROOT / "tests" / "fixtures" / "frame-maps"
PLUGIN = OVERLAY / "d14-projection-overlay.js"
CAMERA = "CAM_P_F"
# /etc/nginx/conf.d/default.conf of the cvat/ui:v2.74.1 image, unchanged
REAL_STOCK = ROOT / "tests" / "fixtures" / "cvat-ui-v2.74.1-default.conf"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load("day14_overlay_config", OVERLAY / "overlay-config.py")
fusion = load("day14_fusion_overlay", ROOT / "src" / "cvat3d_fusion.py")

STOCK = """server {
    root /usr/share/nginx/html;

    location / {
        # sub_filter is not used by the stock image
        try_files $uri /index.html;
    }

    location /assets {
        expires 1y;
    }
}
"""


def frame_map(tmp_path, *items, column="item_id"):
    path = tmp_path / "case.csv"
    path.write_text("\n".join([f"local_frame,source_frame,{column}"]
                              + [f"{k},{k},{item}" for k, item in enumerate(items)]) + "\n")
    return path


def calib_with(tmp_path, **camera_changes):
    calib = json.loads(CALIB.read_text())
    calib["cameras"][CAMERA].update(camera_changes)
    path = tmp_path / "calib.json"
    path.write_text(json.dumps(calib))
    return path


# ------------------------------------------------------------------ config


def test_config_records_calibration_provenance_and_frames(tmp_path):
    out = tmp_path / "config.json"
    assert builder.main(["config", "--calib", str(CALIB), "--frames", str(FRAME_MAPS),
                         "--out", str(out)]) == 0
    cfg = json.loads(out.read_text())
    assert cfg["calibration_version"] == {
        "file": CALIB.name, "sha256": hashlib.sha256(CALIB.read_bytes()).hexdigest()}
    assert cfg["calibration"] == json.loads(CALIB.read_text())
    assert cfg["cameras"] == {"image_1": CAMERA}
    assert len(cfg["frames"]) == 6 and cfg["frames"] == sorted(set(cfg["frames"]))
    assert out.stat().st_mode & 0o777 == 0o600


def test_config_frames_are_the_union_of_overlapping_cases(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    frame_map(a, "1700000000-099741459", "1700000000-299741459")
    frame_map(b, "1700000000-299741459", "1700000000-499741459")
    assert builder.read_frames([a, b]) == [
        "1700000000-099741459", "1700000000-299741459", "1700000000-499741459"]


@pytest.mark.parametrize("item", ["000001", "frame_0001", "1700000000-0997414", ""])
def test_config_refuses_names_that_are_not_capture_timestamps(tmp_path, item):
    with pytest.raises(builder.ConfigError, match="capture timestamp"):
        builder.read_frames([frame_map(tmp_path, "1700000000-099741459", item)])


def test_config_needs_an_item_id_column_and_a_csv(tmp_path):
    with pytest.raises(builder.ConfigError, match="no item_id column"):
        builder.read_frames([frame_map(tmp_path, "1700000000-099741459", column="name")])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(builder.ConfigError, match="no frame-map CSV"):
        builder.read_frames([empty])


@pytest.mark.parametrize("cameras, message", [
    ({"image_1": "CAM_X"}, "not in the calibration"),
    ({"front": CAMERA}, "context image key"),
    ({}, "no context image"),
])
def test_config_refuses_bad_camera_maps(tmp_path, cameras, message):
    with pytest.raises(builder.ConfigError, match=message):
        builder.build_config(CALIB, [FRAME_MAPS], cameras)


@pytest.mark.parametrize("change, message", [
    ({"dist": [0.1] * 8}, "at most five"),
    ({"image_size": [1920]}, "image_size"),
    ({"K": [[1, 0], [0, 1]]}, "K must be"),
    ({"ego2cam": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}, "ego2cam must be"),
])
def test_config_refuses_calibrations_the_browser_cannot_project(tmp_path, change, message):
    with pytest.raises(builder.ConfigError, match=message):
        builder.build_config(calib_with(tmp_path, **change), [FRAME_MAPS], {"image_1": CAMERA})


def test_config_refuses_unknown_point_cloud_frame(tmp_path):
    calib = json.loads(CALIB.read_text())
    calib["pcd_frame"] = "camera"
    path = tmp_path / "calib.json"
    path.write_text(json.dumps(calib))
    with pytest.raises(builder.ConfigError, match="pcd_frame"):
        builder.build_config(path, [FRAME_MAPS], {"image_1": CAMERA})


def test_config_cli_reports_errors_without_traceback(tmp_path, capsys):
    out = tmp_path / "config.json"
    code = builder.main(["config", "--calib", str(CALIB), "--frames", str(FRAME_MAPS),
                         "--cameras", "not json", "--out", str(out)])
    assert code == 1 and not out.exists()
    assert "--cameras is not JSON" in capsys.readouterr().err


# ------------------------------------------------------------------ nginx


def test_nginx_injects_script_into_root_location_and_appends_locations():
    conf = builder.build_nginx(STOCK, "    location /d14-overlay/ {}\n")
    root = conf.index("location / {")
    assert conf.index("sub_filter '</head>'") > root
    assert conf.index("sub_filter '</head>'") < conf.index("try_files")
    assert builder.SCRIPT_TAG in conf
    assert conf.rstrip().endswith("location /d14-overlay/ {}\n}")
    assert conf.count("server {") == 1 and conf.count("{") == conf.count("}")


def test_nginx_on_real_cvat_conf_only_adds_the_overlay():
    stock = REAL_STOCK.read_text()
    locations = builder.LOCATIONS.read_text()
    conf = builder.build_nginx(stock, locations)
    root = conf.index("    location / {\n")
    assert conf.index(builder.SCRIPT_TAG) == conf.index("sub_filter '</head>'", root) + len("sub_filter '</head>' '")
    # the overlay locations close the server block, after every stock route
    assert conf.endswith(locations + "}\n") and conf.index(locations) > conf.index("location /assets")
    # removing what was added gives the stock file back byte for byte
    inject = f"        sub_filter '</head>' '{builder.SCRIPT_TAG}';\n        sub_filter_once on;\n"
    assert conf.replace(inject, "", 1).replace("\n" + locations, "", 1) == stock
    # an already-injected config is never injected twice
    with pytest.raises(builder.ConfigError, match="unexpected shape"):
        builder.build_nginx(conf, locations)


@pytest.mark.parametrize("tail", ["", "\n# trailing comment with a } brace\n"])
def test_nginx_inserts_inside_the_server_block(tail):
    # unbalanced braces in a quoted value and in a comment do not end the server block
    stock = STOCK.replace("expires 1y;", 'add_header X "a } b"; # closing }') + tail
    conf = builder.build_nginx(stock, "    location /d14-overlay/ {}\n")
    assert conf.endswith("location /d14-overlay/ {}\n}\n" + tail)


def test_nginx_locations_file_is_balanced():
    text = builder.LOCATIONS.read_text()
    assert text.count("{") == text.count("}")
    assert "auth_request /d14-overlay-auth;" in text


@pytest.mark.parametrize("stock", [
    STOCK.replace("try_files", "sub_filter 'a' 'b';\n        try_files"),
    STOCK + "server {\n    location / {\n    }\n}\n",
    STOCK.replace("location / {", "location /app {"),
    STOCK + "map $http_upgrade $connection_upgrade {\n    default upgrade;\n}\n",
    STOCK.rstrip()[:-1],
    "location / {\n}\n" + STOCK.replace("location / {", "location /app {"),
])
def test_nginx_refuses_unexpected_shapes(stock):
    with pytest.raises(builder.ConfigError, match="unexpected shape"):
        builder.build_nginx(stock, "")


# ------------------------------------------------------------------ parity

NODE = """
const g = require(process.argv[1]);
const {calib, camera, boxes} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(boxes.map((b) => g.projectBox(b, calib, camera))));
"""


def synthetic_boxes():
    """Cars around the vehicle: in view, cut by the image border or near plane, and behind."""
    boxes = []
    for x in (-12.0, 0.5, 4.0, 9.0, 20.0, 45.0):
        for y in (-12.0, -3.0, 0.0, 3.5, 12.0):
            for yaw in (0.0, 0.6, -1.4):
                boxes.append(fusion.Box3D(len(boxes) + 1, "vehicles", (x, y, -0.8),
                                          (0.0, 0.0, yaw), (4.6, 1.9, 1.6)))
    boxes.append(fusion.Box3D(len(boxes) + 1, "vehicles", (2.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                              (12.0, 6.0, 3.0)))  # straddles the camera
    return boxes


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the browser projection")
def test_browser_projection_matches_python_renderer():
    calib = fusion.Calib.from_json(str(CALIB))
    cam = calib.cameras[CAMERA]
    boxes = synthetic_boxes()
    _, info = fusion.render_overlay(boxes, calib, CAMERA)
    payload = {"calib": json.loads(CALIB.read_text()), "camera": CAMERA, "boxes": [
        {"id": b.track_id, "label": b.label, "position": list(b.position),
         "rotation": list(b.rotation), "scale": list(b.scale)} for b in boxes]}
    js = json.loads(subprocess.run(["node", "-e", NODE, str(PLUGIN)], input=json.dumps(payload),
                                   capture_output=True, text=True, check=True).stdout)

    statuses = {rec["status"] for rec in info}
    assert statuses == {"out_of_fov", "partial", "fully_visible"}, statuses
    for box, rec, got in zip(boxes, info, js, strict=True):
        where = f"box {box.track_id} at {box.position} yaw {box.rotation[2]}"
        assert (got is None) == (rec["status"] == "out_of_fov"), where
        if got is None:
            continue
        assert got["fullyVisible"] == (rec["status"] == "fully_visible"), where
        corners = calib.lidar_to_cam(fusion.box_corners(box.position, box.rotation, box.scale), CAMERA)
        edges = [pts for i, j in fusion.EDGES
                 if (pts := fusion.edge_polyline(corners[i], corners[j], cam)) is not None]
        assert len(got["edges"]) == len(edges), where
        for want, have in zip(edges, got["edges"]):
            scale = np.maximum(1.0, np.abs(want)).max()
            assert np.abs(np.asarray(have["pts"]) - want).max() / scale < 1e-9, where
        assert np.abs(np.asarray(got["bbox"]) - np.asarray(rec["bbox2d"])).max() <= 0.051, where
        assert got["depth"] == pytest.approx(float(corners[:, 2].mean()), abs=1e-9), where
