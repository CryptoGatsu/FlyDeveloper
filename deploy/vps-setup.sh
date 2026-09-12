#!/usr/bin/env bash
# One-shot setup of a fresh Ubuntu 24.04 droplet for The Fly Dev.
#   as root:  bash vps-setup.sh
# Creates a `fly` user, installs Python, Chrome (fly cam + site QA), fonts
# (memes), clones the repo, builds a venv, and prints the deploy key to add on
# GitHub. It does NOT start the fly: copy .env and data first with
# deploy/migrate-from-mac.sh, then `fly daemon install --live`.
set -euo pipefail

REPO="${FLY_REPO:-git@github.com:CryptoGatsu/FlyDeveloper.git}"
BRANCH="${FLY_BRANCH:-claude/focused-edison-jfqgiq}"
USER_NAME="fly"
HOME_DIR="/home/$USER_NAME"
ROOT="$HOME_DIR/FlyDeveloper"

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git rsync curl gnupg ca-certificates \
  fonts-dejavu-core fonts-liberation libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libasound2t64 libxss1

if ! command -v google-chrome >/dev/null 2>&1; then
  echo "== chrome (headless screenshots for the fly cam)"
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -q && apt-get install -y -q google-chrome-stable
fi

echo "== swap (the connectome needs headroom on small droplets)"
if ! swapon --show | grep -q swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== user $USER_NAME"
id -u "$USER_NAME" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$USER_NAME"
mkdir -p "$HOME_DIR/.ssh" && chmod 700 "$HOME_DIR/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then cp /root/.ssh/authorized_keys "$HOME_DIR/.ssh/"; fi
if [ ! -f "$HOME_DIR/.ssh/id_ed25519" ]; then
  sudo -u "$USER_NAME" ssh-keygen -t ed25519 -N "" -C "flydev-vps" -f "$HOME_DIR/.ssh/id_ed25519" >/dev/null
fi
ssh-keyscan -t ed25519 github.com >> "$HOME_DIR/.ssh/known_hosts" 2>/dev/null
chown -R "$USER_NAME:$USER_NAME" "$HOME_DIR/.ssh"

echo
echo "== add this DEPLOY KEY on GitHub with WRITE access (repo -> Settings -> Deploy keys):"
cat "$HOME_DIR/.ssh/id_ed25519.pub"
echo
read -r -p "(press enter once the key is added) " _

echo "== repo"
if [ ! -d "$ROOT/.git" ]; then
  sudo -u "$USER_NAME" git clone --branch "$BRANCH" "$REPO" "$ROOT"
fi
sudo -u "$USER_NAME" git -C "$ROOT" config user.name "The Fly Dev"
sudo -u "$USER_NAME" git -C "$ROOT" config user.email "fly@flydev.tech"

echo "== python venv"
sudo -u "$USER_NAME" python3 -m venv "$ROOT/.venv"
sudo -u "$USER_NAME" "$ROOT/.venv/bin/pip" install -q --upgrade pip
sudo -u "$USER_NAME" "$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements-fly.txt"
mkdir -p "$ROOT/data" "$ROOT/memes" && chown -R "$USER_NAME:$USER_NAME" "$ROOT"

IP="$(curl -fsS -4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo
echo "== done. Next, on your Mac inside the FlyDeveloper folder:"
echo "   bash deploy/migrate-from-mac.sh $USER_NAME@$IP"
echo "Then back here:"
echo "   sudo -iu $USER_NAME"
echo "   cd ~/FlyDeveloper && source .venv/bin/activate"
echo "   python fly.py status && python fly.py launch-status"
echo "   sudo -E \$(which python) fly.py daemon install --live"
echo "   tail -F data/fly-daemon.log"
