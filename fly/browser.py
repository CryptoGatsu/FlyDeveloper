"""The fly browses the internet.

Plain HTTP with `requests` and BeautifulSoup: search through DuckDuckGo's
HTML endpoint, the Hacker News front page through the public Algolia API,
and page fetches with readable-text extraction. No JavaScript execution.
Every network failure degrades to an empty result so the fly can move on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote as requests_quote, urljoin, urlparse

from .config import BrowserConfig

DDG_HTML = "https://html.duckduckgo.com/html/"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
HN_API = "https://hn.algolia.com/api/v1/search?tags=front_page"
HN_SEARCH = "https://hn.algolia.com/api/v1/search?query="


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[str] = field(default_factory=list)


@dataclass
class PageNote:
    url: str
    title: str
    gist: str
    need_spotted: str
    interesting: bool
    followups: list[str]


def _clean_text(html: str, max_chars: int) -> tuple[str, str, list[str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    title = (soup.title.string if soup.title and soup.title.string else "").strip()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = re.sub(r"\n\s*\n+", "\n\n", main.get_text("\n", strip=True))
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http"):
            links.append(href)
    return title, text[:max_chars], links[:200]


class Browser:
    def __init__(self, cfg: BrowserConfig, log=None):
        self.cfg = cfg
        self.log = log or (lambda msg: None)
        import requests

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": cfg.user_agent, "Accept-Language": "en"})

    # -- primitives ----------------------------------------------------------
    def fetch(self, url: str) -> Page | None:
        try:
            r = self.session.get(url, timeout=self.cfg.timeout_sec, allow_redirects=True)
            r.raise_for_status()
        except Exception:
            return None
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return None
        title, text, links = _clean_text(r.text, self.cfg.max_chars_per_page)
        return Page(url=r.url, title=title or url, text=text, links=links)

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        """Try DuckDuckGo (html, then lite), then Hacker News, then Wikipedia."""
        self.last_engine = ""
        for engine, fn in (("duckduckgo", self._ddg_html), ("duckduckgo-lite", self._ddg_lite),
                           ("hackernews", self._hn_search), ("wikipedia", self._wiki_search)):
            try:
                out = fn(query, n)
            except Exception as exc:
                self.log(f"  {engine} failed: {exc}")
                out = []
            if out:
                self.last_engine = engine
                return out
        return []

    @staticmethod
    def _unwrap_ddg(href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            href = parse_qs(parsed.query).get("uddg", [href])[0]
        return href

    def _ddg_html(self, query: str, n: int) -> list[SearchResult]:
        from bs4 import BeautifulSoup

        r = self.session.post(DDG_HTML, data={"q": query}, timeout=self.cfg.timeout_sec)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out: list[SearchResult] = []
        for res in soup.select("div.result"):
            a = res.select_one("a.result__a")
            if not a or not a.get("href"):
                continue
            snippet_el = res.select_one(".result__snippet")
            out.append(SearchResult(a.get_text(strip=True), self._unwrap_ddg(a["href"]),
                                    snippet_el.get_text(" ", strip=True) if snippet_el else ""))
            if len(out) >= n:
                break
        return out

    def _ddg_lite(self, query: str, n: int) -> list[SearchResult]:
        from bs4 import BeautifulSoup

        r = self.session.post(DDG_LITE, data={"q": query}, timeout=self.cfg.timeout_sec)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out: list[SearchResult] = []
        for a in soup.select("a.result-link"):
            if a.get("href"):
                out.append(SearchResult(a.get_text(strip=True), self._unwrap_ddg(a["href"]), ""))
            if len(out) >= n:
                break
        return out

    def _hn_search(self, query: str, n: int) -> list[SearchResult]:
        r = self.session.get(HN_SEARCH + requests_quote(query), timeout=self.cfg.timeout_sec)
        r.raise_for_status()
        out = []
        for h in r.json().get("hits", [])[:n]:
            if h.get("url"):
                out.append(SearchResult(h.get("title", ""), h["url"], f"{h.get('points', 0)} points on HN"))
        return out

    def _wiki_search(self, query: str, n: int) -> list[SearchResult]:
        r = self.session.get(WIKI_SEARCH, params={"action": "opensearch", "search": query, "limit": n, "format": "json"},
                             timeout=self.cfg.timeout_sec)
        r.raise_for_status()
        data = r.json()
        return [SearchResult(t, u, d) for t, d, u in zip(data[1], data[2], data[3])]

    def hn_front(self, n: int = 10) -> list[SearchResult]:
        try:
            r = self.session.get(HN_API, timeout=self.cfg.timeout_sec)
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except Exception:
            return []
        out = []
        for h in hits[:n]:
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            out.append(SearchResult(h.get("title", ""), url, f"{h.get('points', 0)} points"))
        return out

    # -- a browsing session --------------------------------------------------
    def explore(self, mind, memory, topics: list[str], budget: int | None = None) -> list[PageNote]:
        """Search a few topics, read the most promising pages, keep notes.

        `mind.digest` decides what each page means; `memory` avoids re-reading.
        """
        budget = budget or self.cfg.max_pages_per_session
        candidates: list[SearchResult] = []
        for topic in topics[:3]:
            self.log(f"searching: {topic}")
            found = self.search(topic, n=5)
            self.log(f"  {len(found)} results" + (f" via {self.last_engine}" if found else " (every engine failed or blocked)"))
            memory.add("searches", {"query": topic, "engine": self.last_engine,
                                    "results": [{"title": f.title, "url": f.url} for f in found[:5]]})
            candidates.extend(found)
        self.log("checking the Hacker News front page")
        hn = self.hn_front(6)
        self.log(f"  {len(hn)} stories")
        if hn:
            memory.add("searches", {"query": "Hacker News front page", "engine": "hackernews",
                                    "results": [{"title": f.title, "url": f.url} for f in hn]})
        candidates.extend(hn)
        if not candidates:
            memory.note("tried to browse but every search engine failed; is the network up?")

        notes: list[PageNote] = []
        seen: set[str] = set()
        for cand in candidates:
            if len(notes) >= budget:
                break
            if not cand.url or cand.url in seen or memory.visited(cand.url):
                continue
            seen.add(cand.url)
            self.log(f"reading: {cand.title[:70]} <{cand.url}>")
            page = self.fetch(cand.url)
            if page is None or len(page.text) < 200:
                self.log("  nothing readable there")
                continue
            try:
                digest = mind.digest(page.title, page.url, page.text)
                self.log(f"  gist: {digest.gist[:160]}")
                if digest.need_spotted:
                    self.log(f"  need spotted: {digest.need_spotted[:160]}")
            except Exception as exc:  # the mind may refuse or time out
                memory.note(f"could not digest {page.url}: {exc}")
                continue
            note = PageNote(page.url, page.title, digest.gist, digest.need_spotted, digest.interesting, digest.followups)
            notes.append(note)
            memory.add("pages", {
                "url": note.url, "title": note.title, "gist": note.gist,
                "need": note.need_spotted, "interesting": note.interesting, "followups": note.followups,
            })
        return notes
