#!/usr/bin/env bash
set -euo pipefail

NAME="mattermost_newsfeeds"
APP_DIR="/opt/$NAME"
UNIT_FILE="/etc/systemd/system/$NAME.service"
ETC_DIR="/etc/$NAME"
CFG_ETC="$ETC_DIR/config.json"

echo ">>> Creating app dir at $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo mkdir -p "$ETC_DIR"

echo ">>> Copying project files"
sudo cp -r src "$APP_DIR/"
sudo cp requirements.txt "$APP_DIR/"
sudo cp README.md "$APP_DIR/"
sudo cp mattermost_newsfeeds.service "$APP_DIR/"
# Provide a config at /etc if one doesn't exist yet
if [ ! -f "$CFG_ETC" ]; then
  echo ">>> Installing default config to $CFG_ETC"
  sudo cp config.json "$CFG_ETC"
fi

echo ">>> Creating venv and installing requirements"
sudo python3 -m venv "$APP_DIR/.venv"
sudo bash -lc "$APP_DIR/.venv/bin/pip install --upgrade pip"
sudo bash -lc "$APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt"

echo '>>> Installing systemd unit'
sudo cp "$APP_DIR/mattermost_newsfeeds.service" "$UNIT_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "$NAME"
sudo systemctl restart "$NAME"
sudo systemctl status --no-pager "$NAME" || true

echo ">>> Done. Edit $CFG_ETC as needed and restart with: sudo systemctl restart $NAME"
