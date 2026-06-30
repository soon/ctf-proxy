#!/usr/bin/env bash
# Secure JupyterLab setup (port 8933, SSH allowed, firewall restricted)

set -euo pipefail

USER_NAME="jupyter"
PORT=8933
SSH_PORT=22
ROOT_KEYS="/root/.ssh/authorized_keys"
HOME_DIR="/home/${USER_NAME}"
APP_DIR="${HOME_DIR}/jupyterlab"
VENV_DIR="${APP_DIR}/venv"
CONFIG_DIR="${HOME_DIR}/.jupyter"
CONFIG_FILE="${CONFIG_DIR}/jupyter_server_config.py"
SERVICE_FILE="/etc/systemd/system/jupyterlab.service"
PASSWORD_FILE="/root/jupyterlab-password.txt"

# --- Preconditions ---
if [[ $EUID -ne 0 ]]; then
  echo "Run as root."; exit 1
fi
if [[ ! -s "$ROOT_KEYS" ]]; then
  echo "Root has no authorized_keys. Add SSH key first."; exit 1
fi

# --- Cleanup old install ---
systemctl stop jupyterlab 2>/dev/null || true
systemctl disable jupyterlab 2>/dev/null || true
rm -f "$SERVICE_FILE"
rm -rf "$APP_DIR" "$CONFIG_DIR"

# --- OS packages ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends python3 python3-venv curl openssl sudo ufw

# --- User + SSH keys ---
id "$USER_NAME" &>/dev/null || useradd -m -s /bin/bash "$USER_NAME"
install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.ssh"
install -m 600 -o "$USER_NAME" -g "$USER_NAME" "$ROOT_KEYS" "$HOME_DIR/.ssh/authorized_keys"

# --- uv install ---
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ln -sf /root/.local/bin/uv /usr/local/bin/uv
fi

# --- Environment + Jupyter install ---
install -d -o "$USER_NAME" -g "$USER_NAME" "$APP_DIR"
uv venv "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" jupyterlab==4.* jupyter_server==2.* jupyterlab-git
chown -R "$USER_NAME":"$USER_NAME" "$APP_DIR"

# --- Generate password and hash ---
PASSWORD=$(openssl rand -base64 24)
export JUPYTER_PASS="$PASSWORD"
HASH="$("$VENV_DIR"/bin/python - <<'PY'
import os
from jupyter_server.auth import passwd
pw = os.environ.get("JUPYTER_PASS", "").strip()
if not pw:
    raise SystemExit("Empty password env")
print(passwd(pw), end="")
PY
)"
unset JUPYTER_PASS

# --- Config file ---
install -d -o "$USER_NAME" -g "$USER_NAME" "$CONFIG_DIR"
cat > "$CONFIG_FILE" <<EOF
c = get_config()
c.ServerApp.ip = "0.0.0.0"
c.ServerApp.port = ${PORT}
c.ServerApp.open_browser = False
c.ServerApp.allow_remote_access = True
c.ServerApp.token = ""
c.ServerApp.password = u"${HASH}"
c.ServerApp.shutdown_no_activity_timeout = 3600
EOF
chown -R "$USER_NAME":"$USER_NAME" "$CONFIG_DIR"

# --- Save plaintext password ---
(umask 177 && echo "$PASSWORD" > "$PASSWORD_FILE")

# --- systemd unit ---
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=JupyterLab (secure, exposed on port ${PORT})
After=network.target

[Service]
User=${USER_NAME}
Group=${USER_NAME}
WorkingDirectory=${HOME_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=${VENV_DIR}/bin/jupyter lab --config=${CONFIG_FILE}
Restart=on-failure
RestartSec=5
ProtectSystem=full
ProtectHome=false
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jupyterlab
systemctl start jupyterlab

# --- Firewall (UFW) ---
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp comment 'Allow SSH'
ufw allow ${PORT}/tcp comment 'Allow JupyterLab'
ufw --force enable

# --- Output summary ---
IP="$(hostname -I | awk '{print $1}')"
echo
echo "==== JUPYTER SETUP COMPLETE ===="
echo "User:       ${USER_NAME}"
echo "Port:       ${PORT}"
echo "Password:   ${PASSWORD}"
echo "Saved copy: ${PASSWORD_FILE}"
echo "Firewall:   only ports ${SSH_PORT} and ${PORT} open"
echo
echo "Access URL:"
echo "  http://${IP}:${PORT}"
echo "================================"
