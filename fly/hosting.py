"""Put a meme somewhere a token's on-chain `logo` field can point to.

Pons stores the logo as a string of at most 512 bytes, so the image must
live at a URL. Supported hosts:

* **pinata** (IPFS): uploads through Pinata's v3 Files API
  (`https://uploads.pinata.cloud/v3/files`, `network=public`) and falls back
  to the legacy `pinFileToIPFS` endpoint. The logo URL is
  `<PINATA_GATEWAY>/<cid>`; use your dedicated `*.mypinata.cloud` gateway
  for reliable serving.
* **github**: commits the PNG to a repository and returns the raw URL.
* **none**: the fly can plan launches but never send them.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

from .config import HostingConfig

PINATA_V3_UPLOAD = "https://uploads.pinata.cloud/v3/files"
PINATA_LEGACY_UPLOAD = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_TEST_AUTH = "https://api.pinata.cloud/data/testAuthentication"


class HostingError(RuntimeError):
    pass


def host_image(path: Path, cfg: HostingConfig, name: str | None = None) -> str | None:
    if cfg.provider == "none":
        return None
    if cfg.provider == "pinata":
        return _pinata(path, cfg, name)
    if cfg.provider == "github":
        return _github(path, cfg, name)
    raise HostingError(f"unknown image host provider: {cfg.provider}")


def check_host(cfg: HostingConfig) -> str:
    """Cheap credential check; returns a human-readable status line."""
    if cfg.provider == "none":
        return "none: launches will stay dry runs (set FLY_IMAGE_HOST=pinata)"
    if cfg.provider == "pinata":
        if not cfg.pinata_jwt:
            return "pinata: PINATA_JWT is not set"
        import requests

        try:
            r = requests.get(PINATA_TEST_AUTH, headers={"Authorization": f"Bearer {cfg.pinata_jwt}"}, timeout=20)
        except Exception as exc:
            return f"pinata: unreachable ({exc})"
        if r.status_code == 200:
            return f"pinata: authenticated, gateway {cfg.pinata_gateway}"
        return f"pinata: auth failed ({r.status_code} {r.text[:120]})"
    if cfg.provider == "github":
        if not (cfg.github_token and cfg.github_repo):
            return "github: FLY_GITHUB_TOKEN and FLY_GITHUB_REPO are required"
        return f"github: {cfg.github_repo}@{cfg.github_branch}/{cfg.github_dir}"
    return f"unknown provider {cfg.provider}"


def verify_url(url: str, attempts: int = 5, wait_sec: float = 3.0) -> bool:
    """Fetch the hosted image a few times; IPFS gateways can lag briefly."""
    import requests

    for i in range(attempts):
        try:
            r = requests.get(url, timeout=30, stream=True)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return True
        except Exception:
            pass
        if i < attempts - 1:
            time.sleep(wait_sec)
    return False


def _pinata(path: Path, cfg: HostingConfig, name: str | None) -> str:
    import requests

    if not cfg.pinata_jwt:
        raise HostingError("PINATA_JWT is not set")
    headers = {"Authorization": f"Bearer {cfg.pinata_jwt}"}
    filename = name or path.name
    cid = ""
    errors = []
    # v3 Files API (current)
    try:
        with path.open("rb") as fh:
            r = requests.post(
                PINATA_V3_UPLOAD, headers=headers, timeout=120,
                files={"file": (filename, fh, "image/png")},
                data={"network": "public", "name": filename},
            )
        if r.status_code < 300:
            body = r.json()
            cid = (body.get("data") or {}).get("cid") or body.get("cid") or ""
        else:
            errors.append(f"v3 {r.status_code} {r.text[:160]}")
    except Exception as exc:
        errors.append(f"v3 {exc}")
    # legacy pinning API (fallback)
    if not cid:
        try:
            with path.open("rb") as fh:
                r = requests.post(
                    PINATA_LEGACY_UPLOAD, headers=headers, timeout=120,
                    files={"file": (filename, fh, "image/png")},
                )
            if r.status_code < 300:
                cid = r.json().get("IpfsHash", "")
            else:
                errors.append(f"legacy {r.status_code} {r.text[:160]}")
        except Exception as exc:
            errors.append(f"legacy {exc}")
    if not cid:
        raise HostingError("pinata upload failed: " + "; ".join(errors))
    return f"{cfg.pinata_gateway.rstrip('/')}/{cid}"


def _github(path: Path, cfg: HostingConfig, name: str | None) -> str:
    import requests

    if not (cfg.github_token and cfg.github_repo):
        raise HostingError("FLY_GITHUB_TOKEN and FLY_GITHUB_REPO are required for github hosting")
    filename = name or path.name
    api = f"https://api.github.com/repos/{cfg.github_repo}/contents/{cfg.github_dir.strip('/')}/{filename}"
    payload = {
        "message": f"fly meme: {filename}",
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
        "branch": cfg.github_branch,
    }
    r = requests.put(
        api, json=payload, timeout=60,
        headers={"Authorization": f"Bearer {cfg.github_token}", "Accept": "application/vnd.github+json"},
    )
    if r.status_code >= 300:
        raise HostingError(f"github upload failed: {r.status_code} {r.text[:200]}")
    return f"https://raw.githubusercontent.com/{cfg.github_repo}/{cfg.github_branch}/{cfg.github_dir.strip('/')}/{filename}"
