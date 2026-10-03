#!/usr/bin/env bash
# Turn the Day 14 projection overlay on/off in the CVAT already running on this machine.
#
#   scripts/cvat-overlay/overlay.sh up       # copy plugin + private config into cvat_ui, reload nginx
#   scripts/cvat-overlay/overlay.sh down     # put cvat_ui back on its stock nginx config
#   scripts/cvat-overlay/overlay.sh status   # is the plugin injected, is the config login-gated
#
# Works on any local CVAT whose UI container is called cvat_ui (the CVAT compose default),
# wherever its compose folder lives: nothing is mounted, the files go into the running
# container and nginx reloads. Server, database and annotations are untouched.
# The overlay survives `docker compose stop/start`; a recreated cvat_ui (e.g. after
# `docker compose up -d` with a new image) comes back without it, so run `up` again.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CVAT_URL="${CVAT_URL:-http://localhost:8080}"
UI="${CVAT_UI_CONTAINER:-cvat_ui}"
CALIB="${CALIB:-$REPO/private/calib-diagnostic.json}"
FRAMES="${FRAMES:-$REPO/private/frame-maps}"
CAMERA_MAP="${CAMERA_MAP:-}" # JSON context image -> camera; default {"image_1": "CAM_P_F"}
VERIFIED_CVAT="v2.74.1"

CONF=/etc/nginx/conf.d/default.conf
STOCK=/etc/nginx/conf.d/default.conf.d14-stock # not *.conf, so nginx never loads it
WWW=/usr/share/nginx/d14-overlay
PRIVATE=/usr/share/nginx/d14-overlay-private
RECREATE="in your CVAT folder: docker compose up -d --force-recreate $UI"

die() { echo "✗ $*" >&2; exit 1; }
ui() { docker exec "$UI" "$@"; }
ui_root() { docker exec -u 0 "$UI" "$@"; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$CVAT_URL$1" || true; }

preflight() {
  command -v docker >/dev/null || die "docker not found"
  command -v python3 >/dev/null || die "python3 not found"
  docker info >/dev/null 2>&1 \
    || die "cannot reach Docker: start Docker; on Linux, if CVAT runs with sudo docker, run: sudo bash $0 $1"
  [ "$(docker inspect -f '{{.State.Running}}' "$UI" 2>/dev/null)" = "true" ] \
    || die "container $UI is not running; start CVAT first (in your CVAT folder: docker compose start)"
  # everything the overlay writes must stay inside the container: a mount at or above one of
  # its paths (the file itself, /etc/nginx/conf.d, /usr/share/nginx, ...) would write to the host
  local mount target
  while IFS= read -r mount; do
    [ -n "$mount" ] || continue
    for target in "$CONF" "$WWW" "$PRIVATE"; do
      case "$target/" in
        "${mount%/}/"*) die "$UI mounts $mount from the host, so the overlay would write host files; remove that mount from your compose files, then: $RECREATE" ;;
      esac
    done
  done < <(docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$UI")
}

# The image's own default.conf, kept once inside the container, so `up` can run again and
# `down` can restore it whatever CVAT version the container runs.
stock_conf() {
  if ! ui test -f "$STOCK"; then
    ui grep -q d14-overlay "$CONF" \
      && die "$CONF already has the overlay but its stock copy is gone; $RECREATE"
    ui_root cp -p "$CONF" "$STOCK"
  fi
  ui cat "$STOCK"
}

# nginx output is shown only on failure: the stock config already warns about a duplicate
# text/html MIME type, which is CVAT's and harmless
nginx_ok() {
  local out
  out="$(ui nginx "$@" 2>&1)" && return 0
  echo "$out" >&2
  return 1
}

reload_or_restore() {
  if ! nginx_ok -t; then
    ui_root cp -p "$STOCK" "$CONF"
    die "generated nginx config rejected; $UI keeps its stock config"
  fi
  nginx_ok -s reload || die "nginx reload failed in $UI"
}

up() {
  preflight up
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  python3 "$HERE/overlay-config.py" config --calib "$CALIB" --frames "$FRAMES" \
    ${CAMERA_MAP:+--cameras "$CAMERA_MAP"} --out "$tmp/config.json"
  stock_conf >"$tmp/stock.conf"
  python3 "$HERE/overlay-config.py" nginx --stock "$tmp/stock.conf" --out "$tmp/default.conf"

  ui_root mkdir -p "$WWW" "$PRIVATE"
  docker cp "$HERE/d14-projection-overlay.js" "$UI:$WWW/d14-projection-overlay.js"
  docker cp "$tmp/config.json" "$UI:$PRIVATE/config.json"
  docker cp "$tmp/default.conf" "$UI:$CONF"
  # nginx workers run as the image's nginx user; the calibration stays readable by it alone
  ui_root chown -R nginx:nginx "$WWW" "$PRIVATE" "$CONF"
  ui_root chmod 755 "$WWW"
  ui_root chmod 644 "$WWW/d14-projection-overlay.js" "$CONF"
  ui_root chmod 700 "$PRIVATE"
  ui_root chmod 600 "$PRIVATE/config.json"
  reload_or_restore
  sleep 1
  status
  echo "→ reload the CVAT tab (Ctrl+Shift+R / Cmd+Shift+R) to load the plugin"
}

down() {
  preflight down
  if ui test -f "$STOCK"; then
    ui_root cp -p "$STOCK" "$CONF"
    nginx_ok -t || die "stock nginx config rejected; $RECREATE"
    nginx_ok -s reload || die "nginx reload failed in $UI"
  elif ui grep -q d14-overlay "$CONF"; then
    # without the stock copy nginx would keep loading a deleted plugin
    die "$CONF has the overlay but its stock copy is gone; $RECREATE"
  fi
  ui_root rm -rf "$WWW" "$PRIVATE" "$STOCK"
  sleep 1
  status
}

status() {
  local about version page
  about="$(curl -s --max-time 5 "$CVAT_URL/api/server/about" || true)"
  version="$(python3 -c 'import json, sys
try: print(json.load(sys.stdin).get("version", "?"))
except ValueError: print("unreachable")' <<<"$about")"
  echo "CVAT at $CVAT_URL: $version"
  case "$version" in
    unreachable) return 0 ;;
    "${VERIFIED_CVAT#v}") ;;
    *) echo "  note: overlay verified on CVAT $VERIFIED_CVAT; check that boxes appear in the camera panel" ;;
  esac
  page="$(curl -s --max-time 5 "$CVAT_URL/" || true)"
  if ! grep -q 'd14-projection-overlay.js' <<<"$page"; then
    echo "overlay: off"
    return 0
  fi
  echo "overlay: on"
  echo "  plugin file: HTTP $(code /d14-overlay/d14-projection-overlay.js) (expect 200)"
  echo "  config without login: HTTP $(code /d14-overlay/private/config.json) (expect 401)"
  ui cat "$PRIVATE/config.json" 2>/dev/null | python3 -c 'import json, sys
c = json.load(sys.stdin); v = c["calibration_version"]
print("  calibration: %s sha256 %s, %d frames, cameras %s"
      % (v["file"], v["sha256"][:12], len(c["frames"]), c["cameras"]))' \
    || echo "  calibration: config missing in $UI"
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  *) die "usage: $0 up|down|status" ;;
esac
