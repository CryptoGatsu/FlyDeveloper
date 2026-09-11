"""Put a meme somewhere a token's on-chain `logo` field can point to.

Pons stores the logo as a string of at most 512 bytes, so the image must
live at a URL: IPFS through Pinata, or a raw GitHub URL. With provider
"none" the fly can still plan launches, but never send them.
"""

from __future__ import annotations

import base64
from pathlib import Path

from .config import HostingConfig


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


def _pinata(path: Path, cfg: HostingConfig, name: str | None) -> str:
    import requests

    if not cfg.pinata_jwt:
        raise HostingError("PINATA_JWT is not set")
    with path.open("rb") as fh:
        r = requests.post(
            "https://api.pinata.cloud/pinning/pinFileToIPFS",
            headers={"Authorization": f"Bearer {cfg.pinata_jwt}"},
            files={"file": (name or path.name, fh, "image/png")},
            timeout=120,
        )
    if r.status_code >= 300:
        raise HostingError(f"pinata upload failed: {r.status_code} {r.text[:200]}")
    cid = r.json().get("IpfsHash")
    if not cid:
        raise HostingError("pinata returned no IpfsHash")
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
