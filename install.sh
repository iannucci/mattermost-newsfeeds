#!/usr/bin/env bash
set -euo pipefail

NAME="mattermost-newsfeeds"
APP_DIR="/opt/$NAME"
UNIT_FILE="/etc/systemd/system/$NAME.service"
ETC_DIR="/etc/$NAME"
CFG_ETC="$ETC_DIR/config.json"

# Stop any running version of $NAME
if systemctl is-active --quiet "$NAME.service"; then
  sudo systemctl stop $NAME
fi

echo "Creating app dir at $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo mkdir -p "$ETC_DIR"

echo ">>> Copying project files"
sudo cp -r src "$APP_DIR/"
sudo cp requirements.txt "$APP_DIR/"
sudo cp README.md "$APP_DIR/"
sudo cp mattermost-newsfeeds.service "$APP_DIR/"
# Provide a config at /etc if one doesn't exist yet
if [ ! -f "$CFG_ETC" ]; then
  echo "Installing default config to $CFG_ETC"
  sudo cp config-example.json "$CFG_ETC"
fi

echo "Creating venv and installing requirements"
sudo python3 -m venv "$APP_DIR/.venv"
sudo bash -lc "$APP_DIR/.venv/bin/pip install --upgrade pip"
sudo bash -lc "$APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt"

echo 'Installing service file'
sudo cp "$APP_DIR/mattermost-newsfeeds.service" "$UNIT_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "$NAME"
sudo systemctl restart "$NAME"
sudo systemctl status --no-pager "$NAME" || true

echo "Installation is complete"
echo "Edit $CFG_ETC if necessary and restart via: sudo systemctl restart $NAME"
