#!/usr/bin/env bash
# Move the fly from this Mac to a Linux host prepared with deploy/vps-setup.sh.
#   on the Mac, inside FlyDeveloper:  bash deploy/migrate-from-mac.sh fly@1.2.3.4
# Stops the local daemon first (two flies must never write the same memory),
# pushes anything unpublished, then copies the private state git does not
# carry: .env, memory, health, self-repair drafts, the connectome cache (saves
# a long rebuild), meme originals and screenshots.
set -euo pipefail
DEST="${1:?usage: migrate-from-mac.sh user@host [remote-path]}"
RPATH="${2:-FlyDeveloper}"

echo "== stopping the local daemon (only one fly may run)"
python fly.py daemon uninstall || true
echo "== pushing anything the fly had not published yet"
python fly.py publish --push || true

echo "== copying private state to $DEST:$RPATH"
rsync -avz .env "$DEST:$RPATH/.env"
rsync -avz --progress --relative \
  ./data/fly_memory.json ./data/fly_memory.bak.json ./data/fly_health.json ./data/fly_connectome_cache.npz \
  ./data/self-repair ./memes ./site/browsing/shots \
  "$DEST:$RPATH/" || true

echo
echo "== copied. On the server:"
echo "   ssh $DEST"
echo "   cd $RPATH && source .venv/bin/activate"
echo "   git pull --rebase --autostash -X theirs"
echo "   python fly.py status && python fly.py launch-status"
echo "   sudo -E \$(which python) fly.py daemon install --live"
echo "   tail -F data/fly-daemon.log"
