"""The fly's X (Twitter) account.

Posting uses the X API v2 with OAuth 1.0a user context (an app's consumer
key/secret plus the account's access token/secret, all from the X developer
portal). Media goes through the v2 media upload endpoint with the v1.1
endpoint as a fallback. Engagement comes back from `public_metrics`.

Without credentials, or with FLY_X_POST unset, every post is a dry run: it
is composed, guarded, recorded and shown, but never sent.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import XConfig

POST_URL = "https://api.x.com/2/tweets"
LOOKUP_URL = "https://api.x.com/2/tweets"
MEDIA_V2_URL = "https://api.x.com/2/media/upload"
MEDIA_V1_URL = "https://upload.twitter.com/1.1/media/upload.json"
ME_URL = "https://api.x.com/2/users/me"
MAX_LEN = 280

# Hype is fine; promises are not.
FORBIDDEN = (
    "guaranteed", "risk-free", "risk free", "financial advice", "can't lose", "cannot lose",
    "will 10x", "will 100x", "will 1000x", "100x", "1000x", "will moon", "to the moon guaranteed",
    "price target", "buy now before", "get rich", "passive income", "returns",
)


class XError(RuntimeError):
    pass


@dataclass
class Post:
    text: str
    kind: str                      # hype | build | meme | launch | learning | reply
    media: str = ""                # local path of an image, if any
    id: str = ""
    url: str = ""
    live: bool = False
    metrics: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def post_problems(text: str) -> list[str]:
    out = []
    low = text.lower()
    if len(text) > MAX_LEN:
        out.append(f"too long ({len(text)} > {MAX_LEN})")
    if not text.strip():
        out.append("empty")
    for word in FORBIDDEN:
        if word in low:
            out.append(f"promise word: '{word}'")
    if re.search(r"\$\s?\d[\d,.]*\s*(k|m|b)?\b.*(price|mcap|market cap)|(\d+x)\b", low):
        out.append("price or multiple prediction")
    return out


class XClient:
    def __init__(self, cfg: XConfig):
        self.cfg = cfg
        self._session = None
        if cfg.api_key and cfg.api_secret and cfg.access_token and cfg.access_secret:
            from requests_oauthlib import OAuth1Session

            self._session = OAuth1Session(cfg.api_key, cfg.api_secret, cfg.access_token, cfg.access_secret)

    @property
    def configured(self) -> bool:
        return self._session is not None

    @property
    def armed(self) -> bool:
        return self.configured and self.cfg.post

    # -- write ---------------------------------------------------------------
    def upload_media(self, path: Path) -> str:
        assert self._session is not None
        data = Path(path).read_bytes()
        try:
            r = self._session.post(MEDIA_V2_URL, files={"media": (Path(path).name, data, "image/png")},
                                   data={"media_category": "tweet_image"}, timeout=60)
            if r.status_code < 300:
                body = r.json()
                mid = (body.get("data") or {}).get("id") or body.get("media_id_string") or body.get("id")
                if mid:
                    return str(mid)
        except Exception:
            pass
        r = self._session.post(MEDIA_V1_URL, files={"media": (Path(path).name, data, "image/png")}, timeout=60)
        if r.status_code >= 300:
            raise XError(f"media upload failed: {r.status_code} {r.text[:200]}")
        return str(r.json().get("media_id_string") or r.json().get("media_id"))

    def send(self, post: Post) -> Post:
        post.problems = post_problems(post.text)
        if post.problems:
            return post
        if not self.armed:
            post.live = False
            return post
        assert self._session is not None
        payload: dict[str, Any] = {"text": post.text}
        if post.media and Path(post.media).is_file():
            payload["media"] = {"media_ids": [self.upload_media(Path(post.media))]}
        r = self._session.post(POST_URL, json=payload, timeout=60)
        if r.status_code >= 300:
            raise XError(f"post failed: {r.status_code} {r.text[:200]}")
        post.id = str(r.json()["data"]["id"])
        post.url = f"https://x.com/{self.cfg.handle.lstrip('@')}/status/{post.id}"
        post.live = True
        return post

    def reply(self, text: str, in_reply_to: str) -> Post:
        post = Post(text=text, kind="reply")
        post.problems = post_problems(text)
        if post.problems or not self.armed:
            return post
        assert self._session is not None
        r = self._session.post(POST_URL, json={"text": text, "reply": {"in_reply_to_tweet_id": in_reply_to}}, timeout=60)
        if r.status_code >= 300:
            raise XError(f"reply failed: {r.status_code} {r.text[:200]}")
        post.id = str(r.json()["data"]["id"])
        post.url = f"https://x.com/{self.cfg.handle.lstrip('@')}/status/{post.id}"
        post.live = True
        return post

    # -- read ----------------------------------------------------------------
    _me_id: str = ""

    def me(self) -> str:
        if self._me_id or not self._session:
            return self._me_id
        r = self._session.get(ME_URL, timeout=30)
        if r.status_code >= 300:
            raise XError(f"users/me failed: {r.status_code} {r.text[:200]}")
        self._me_id = str(r.json()["data"]["id"])
        return self._me_id

    def mentions(self, since_id: str = "", max_results: int = 20) -> list[dict[str, Any]]:
        """Recent posts that mention the fly: [{id, text, author, author_id}]."""
        if not self._session:
            return []
        params: dict[str, Any] = {"max_results": max(5, min(100, max_results)), "tweet.fields": "author_id,created_at",
                                  "expansions": "author_id", "user.fields": "username"}
        if since_id:
            params["since_id"] = since_id
        r = self._session.get(f"https://api.x.com/2/users/{self.me()}/mentions", params=params, timeout=30)
        if r.status_code >= 300:
            raise XError(f"mentions failed: {r.status_code} {r.text[:200]}")
        body = r.json()
        users = {u["id"]: u.get("username", "") for u in (body.get("includes") or {}).get("users", [])}
        out = []
        for t in body.get("data", []) or []:
            out.append({"id": str(t["id"]), "text": t.get("text", ""), "author_id": str(t.get("author_id", "")),
                        "author": users.get(str(t.get("author_id", "")), ""), "at": t.get("created_at", "")})
        return out

    def metrics(self, ids: list[str]) -> dict[str, dict[str, int]]:
        if not self._session or not ids:
            return {}
        out: dict[str, dict[str, int]] = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            r = self._session.get(LOOKUP_URL, params={"ids": ",".join(chunk), "tweet.fields": "public_metrics"}, timeout=30)
            if r.status_code >= 300:
                raise XError(f"metrics failed: {r.status_code} {r.text[:200]}")
            for t in r.json().get("data", []):
                out[str(t["id"])] = {k: int(v) for k, v in (t.get("public_metrics") or {}).items()}
        return out


def engagement_score(m: dict[str, int]) -> float:
    """One number for 'did this land': likes + 2*reposts + 3*replies + quotes + impressions/200."""
    return (m.get("like_count", 0) + 2 * m.get("retweet_count", 0) + 3 * m.get("reply_count", 0)
            + m.get("quote_count", 0) + m.get("bookmark_count", 0) + m.get("impression_count", 0) / 200.0)
