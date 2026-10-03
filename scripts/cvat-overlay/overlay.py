#!/usr/bin/env python3
"""Turn the Day 14 projection overlay on/off in the local CVAT, without bash.

Same behaviour as overlay.sh, for machines that only have Python and Docker
(Windows PowerShell/CMD without WSL, or any OS):

    python scripts/cvat-overlay/overlay.py up       # copy plugin + private config into cvat_ui
    python scripts/cvat-overlay/overlay.py down     # restore the stock nginx config
    python scripts/cvat-overlay/overlay.py status

Environment overrides: CVAT_URL, CVAT_UI_CONTAINER, CALIB, FRAMES, CAMERA_MAP.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CVAT_URL = os.environ.get("CVAT_URL", "http://localhost:8080")
UI = os.environ.get("CVAT_UI_CONTAINER", "cvat_ui")
CALIB = os.environ.get("CALIB", str(REPO / "private" / "calib-diagnostic.json"))
FRAMES = os.environ.get("FRAMES", str(REPO / "private" / "frame-maps"))
CAMERA_MAP = os.environ.get("CAMERA_MAP", "")
VERIFIED_CVAT = "2.74.1"

CONF = "/etc/nginx/conf.d/default.conf"
STOCK = "/etc/nginx/conf.d/default.conf.d14-stock"  # not *.conf, so nginx never loads it
WWW = "/usr/share/nginx/d14-overlay"
PRIVATE = "/usr/share/nginx/d14-overlay-private"
RECREATE = f"in your CVAT folder: docker compose up -d --force-recreate {UI}"


def die(msg):
    print(f"x {msg}", file=sys.stderr)
    sys.exit(1)


def run(*args, check=False):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=check)


def ui(*args):
    return run("docker", "exec", UI, *args)


def ui_root(*args):
    res = run("docker", "exec", "-u", "0", UI, *args)
    if res.returncode:
        die(f"{' '.join(args)} failed in {UI}: {res.stderr.strip()}")
    return res


def http(path):
    """Return (status code, body) or (None, '') when CVAT cannot be reached."""
    try:
        with urllib.request.urlopen(CVAT_URL + path, timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError):
        return None, ""


def preflight():
    if not shutil.which("docker"):
        die("docker not found: install/start Docker Desktop")
    if run("docker", "info").returncode:
        die("cannot reach Docker: start Docker Desktop and wait until it says running")
    state = run("docker", "inspect", "-f", "{{.State.Running}}", UI)
    if state.stdout.strip() != "true":
        die(f"container {UI} is not running; start CVAT first (in your CVAT folder: docker compose start)")
    # everything the overlay writes must stay inside the container
    mounts = run("docker", "inspect", "-f", "{{range .Mounts}}{{println .Destination}}{{end}}", UI).stdout
    for mount in filter(None, (m.strip() for m in mounts.splitlines())):
        for target in (CONF, WWW, PRIVATE):
            if (target + "/").startswith(mount.rstrip("/") + "/"):
                die(f"{UI} mounts {mount} from the host, so the overlay would write host files; "
                    f"remove that mount from your compose files, then: {RECREATE}")


def stock_conf():
    """The image's own default.conf, kept once inside the container."""
    if ui("test", "-f", STOCK).returncode:
        if ui("grep", "-q", "d14-overlay", CONF).returncode == 0:
            die(f"{CONF} already has the overlay but its stock copy is gone; {RECREATE}")
        ui_root("cp", "-p", CONF, STOCK)
    return ui("cat", STOCK).stdout


def nginx_ok(*args):
    res = ui("nginx", *args)
    if res.returncode:
        print(res.stdout + res.stderr, file=sys.stderr)
    return res.returncode == 0


def config_tool(*args):
    res = subprocess.run([sys.executable, str(HERE / "overlay-config.py"), *args])
    if res.returncode:
        sys.exit(res.returncode)


def up():
    preflight()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cams = ["--cameras", CAMERA_MAP] if CAMERA_MAP else []
        config_tool("config", "--calib", CALIB, "--frames", FRAMES, *cams, "--out", str(tmp / "config.json"))
        (tmp / "stock.conf").write_text(stock_conf(), encoding="utf-8", newline="\n")
        config_tool("nginx", "--stock", str(tmp / "stock.conf"), "--out", str(tmp / "default.conf"))

        ui_root("mkdir", "-p", WWW, PRIVATE)
        for src, dst in ((HERE / "d14-projection-overlay.js", f"{WWW}/d14-projection-overlay.js"),
                         (tmp / "config.json", f"{PRIVATE}/config.json"),
                         (tmp / "default.conf", CONF)):
            res = run("docker", "cp", str(src), f"{UI}:{dst}")
            if res.returncode:
                die(f"docker cp {src.name} failed: {res.stderr.strip()}")
    # nginx workers run as the image's nginx user; the calibration stays readable by it alone
    ui_root("chown", "-R", "nginx:nginx", WWW, PRIVATE, CONF)
    ui_root("chmod", "755", WWW)
    ui_root("chmod", "644", f"{WWW}/d14-projection-overlay.js", CONF)
    ui_root("chmod", "700", PRIVATE)
    ui_root("chmod", "600", f"{PRIVATE}/config.json")
    if not nginx_ok("-t"):
        ui_root("cp", "-p", STOCK, CONF)
        die(f"generated nginx config rejected; {UI} keeps its stock config")
    if not nginx_ok("-s", "reload"):
        die(f"nginx reload failed in {UI}")
    time.sleep(1)
    status()
    print("-> reload the CVAT tab (Ctrl+Shift+R / Cmd+Shift+R) to load the plugin")


def down():
    preflight()
    if ui("test", "-f", STOCK).returncode == 0:
        ui_root("cp", "-p", STOCK, CONF)
        if not nginx_ok("-t"):
            die(f"stock nginx config rejected; {RECREATE}")
        if not nginx_ok("-s", "reload"):
            die(f"nginx reload failed in {UI}")
    elif ui("grep", "-q", "d14-overlay", CONF).returncode == 0:
        die(f"{CONF} has the overlay but its stock copy is gone; {RECREATE}")
    ui_root("rm", "-rf", WWW, PRIVATE, STOCK)
    time.sleep(1)
    status()


def status():
    code, about = http("/api/server/about")
    try:
        version = json.loads(about).get("version", "?")
    except ValueError:
        version = "unreachable"
    print(f"CVAT at {CVAT_URL}: {version}")
    if version == "unreachable":
        return
    if version != VERIFIED_CVAT:
        print(f"  note: overlay verified on CVAT v{VERIFIED_CVAT}; check that boxes appear in the camera panel")
    _, page = http("/")
    if "d14-projection-overlay.js" not in page:
        print("overlay: off")
        return
    print("overlay: on")
    print(f"  plugin file: HTTP {http('/d14-overlay/d14-projection-overlay.js')[0]} (expect 200)")
    print(f"  config without login: HTTP {http('/d14-overlay/private/config.json')[0]} (expect 401)")
    try:
        c = json.loads(ui("cat", f"{PRIVATE}/config.json").stdout)
        v = c["calibration_version"]
        print(f"  calibration: {v['file']} sha256 {v['sha256'][:12]}, {len(c['frames'])} frames, cameras {c['cameras']}")
    except (ValueError, KeyError):
        print(f"  calibration: config missing in {UI}")


if __name__ == "__main__":
    actions = {"up": up, "down": down, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        die(f"usage: python {sys.argv[0]} up|down|status")
    actions[sys.argv[1]]()
