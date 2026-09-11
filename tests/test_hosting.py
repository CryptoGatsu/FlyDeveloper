import json

from fly.config import HostingConfig
from fly.hosting import HostingError, check_host, host_image
from fly.memes import render_meme


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _img(tmp_path):
    return render_meme("t", "b", tmp_path / "t.png", size=120)


def test_pinata_v3_upload(tmp_path, monkeypatch):
    import requests

    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        assert kw["headers"]["Authorization"] == "Bearer jwt"
        assert kw["data"]["network"] == "public"
        return _Resp(200, {"data": {"cid": "bafytest", "id": "x"}})

    monkeypatch.setattr(requests, "post", fake_post)
    cfg = HostingConfig(provider="pinata", pinata_jwt="jwt", pinata_gateway="https://me.mypinata.cloud/ipfs")
    url = host_image(_img(tmp_path), cfg)
    assert url == "https://me.mypinata.cloud/ipfs/bafytest"
    assert calls == ["https://uploads.pinata.cloud/v3/files"]


def test_pinata_falls_back_to_legacy(tmp_path, monkeypatch):
    import requests

    def fake_post(url, **kw):
        if "v3" in url:
            return _Resp(404, {"error": "no"})
        return _Resp(200, {"IpfsHash": "QmLegacy"})

    monkeypatch.setattr(requests, "post", fake_post)
    cfg = HostingConfig(provider="pinata", pinata_jwt="jwt")
    assert host_image(_img(tmp_path), cfg).endswith("/QmLegacy")


def test_pinata_failure_raises(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "post", lambda url, **kw: _Resp(401, {"error": "bad jwt"}))
    cfg = HostingConfig(provider="pinata", pinata_jwt="jwt")
    try:
        host_image(_img(tmp_path), cfg)
    except HostingError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("expected HostingError")


def test_none_provider(tmp_path):
    assert host_image(_img(tmp_path), HostingConfig(provider="none")) is None
    assert check_host(HostingConfig(provider="pinata")).endswith("PINATA_JWT is not set")


def test_gateway_normalization():
    from fly.hosting import normalize_gateway

    assert normalize_gateway("beige-large-swift-176.mypinata.cloud") == "https://beige-large-swift-176.mypinata.cloud/ipfs"
    assert normalize_gateway("https://x.mypinata.cloud/ipfs/") == "https://x.mypinata.cloud/ipfs"
    assert normalize_gateway("") == "https://gateway.pinata.cloud/ipfs"
