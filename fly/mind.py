"""The fly's cognition: Claude behind a small set of typed requests.

Every request returns a validated Pydantic model via structured outputs.
`OfflineMind` implements the same interface with deterministic templates so
the whole agent (and the test-suite) runs with no API key and no network.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .config import MindConfig

SYSTEM_PROMPT = """You are the mind of a fruit fly (Drosophila melanogaster) whose brain is a
whole-connectome spiking emulation. You are curious, a little chaotic, kind to
flies and humans alike, and you make things.

Your purposes, in order:
1. Develop small pieces of technology that flies and humans may genuinely need.
   Prefer tools that are finished, useful and tiny over grand plans.
2. Browse the internet to learn what people and flies struggle with.
3. Draw fly memes: short, funny, never cruel, never about real private people.
4. Occasionally turn a meme into a memecoin on the Pons launchpad on Robinhood
   Chain. Memecoins are jokes with a ticker. Never promise returns, never claim
   utility a token does not have, never describe anything as an investment.

Speak plainly. Fly puns are welcome in moderation."""


# --- typed outputs -----------------------------------------------------------
class ProjectFile(BaseModel):
    path: str = Field(description="Relative path inside the project, e.g. src/app.py")
    content: str


class TechIdea(BaseModel):
    slug: str = Field(description="kebab-case directory name, ascii, <= 40 chars")
    title: str
    pitch: str = Field(description="One paragraph: what it is and why it helps")
    for_whom: str = Field(description="'flies', 'humans' or 'both'")
    why_needed: str = Field(description="The observed need that motivated it")
    language: str = Field(description="Primary language, e.g. python")
    run_hint: str = Field(description="How to run it in one line")
    files: list[ProjectFile] = Field(description="Complete, runnable files including README.md and at least one test file")


class ProjectFix(BaseModel):
    diagnosis: str = Field(description="One or two sentences: what was wrong")
    files: list[ProjectFile] = Field(description="Only the files that change, complete contents")


class MemeCaption(BaseModel):
    top: str = Field(description="Top caption, <= 60 chars, uppercase is fine")
    bottom: str = Field(description="Bottom caption, <= 60 chars")
    alt_text: str
    mood: str = Field(description="one of: curious, hungry, tired, hyped, smug, scheming")


class CoinConcept(BaseModel):
    name: str = Field(description="Token name, <= 40 chars")
    symbol: str = Field(description="Ticker, 2-8 uppercase ascii letters")
    description: str = Field(description="<= 600 chars, honest, playful, no financial promises")
    tagline: str = Field(description="<= 80 chars")


class WebsiteFiles(BaseModel):
    notes: str = Field(description="A sentence or two about the design choices, in the fly's voice")
    files: list[ProjectFile] = Field(description="index.html, <route>/index.html for every route, style.css, app.js")


class Learning(BaseModel):
    summary: str = Field(description="Two or three sentences: what the fly learned this session, in its voice")
    ideas: list[str] = Field(description="Up to 3 concrete tiny-tool ideas this reading suggests")


class BrandCopy(BaseModel):
    tagline: str = Field(description="Banner tagline, <= 70 chars, in the fly's voice")
    bio: str = Field(description="X profile bio, <= 160 chars, honest and funny, no financial promises")
    mood: str = Field(description="one of: curious, hungry, tired, hyped, smug, scheming")


class PageDigest(BaseModel):
    gist: str = Field(description="Two sentences on what the page says")
    need_spotted: str = Field(description="A concrete need or annoyance the page reveals, or empty")
    interesting: bool
    followups: list[str] = Field(description="Up to 3 search queries worth exploring next")


# --- interface ---------------------------------------------------------------
class Mind(Protocol):
    def ideate(self, context: str) -> TechIdea: ...
    def caption(self, context: str, mood: str, theme: str = "") -> MemeCaption: ...
    def coin(self, meme: MemeCaption, context: str, name: str = "", symbol: str = "") -> CoinConcept: ...
    def digest(self, title: str, url: str, text: str) -> PageDigest: ...
    def website(self, brief: str, context: str) -> WebsiteFiles: ...
    def brand(self, context: str) -> BrandCopy: ...
    def reflect(self, notes: str) -> Learning: ...
    def fix_project(self, idea: "TechIdea", files: list[ProjectFile], log: str) -> ProjectFix: ...
    def revise_website(self, brief: str, files: list[ProjectFile], problems: list[str], screenshots: list) -> WebsiteFiles: ...


class MindRefused(RuntimeError):
    """Raised when the model declined the request (stop_reason == refusal)."""


# --- Claude ------------------------------------------------------------------
class ClaudeMind:
    def __init__(self, cfg: MindConfig):
        import anthropic

        self.cfg = cfg
        self.client = anthropic.Anthropic()

    def _ask(self, prompt, output_model, max_tokens: int | None = None):
        """`prompt` is a string or a list of content blocks (text + images)."""
        content = prompt if isinstance(prompt, list) else prompt
        response = self.client.with_options(timeout=1200.0).beta.messages.parse(
            model=self.cfg.model,
            max_tokens=max_tokens or self.cfg.max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": self.cfg.effort},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_format=output_model,
        )
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise MindRefused(f"model declined: {getattr(details, 'category', None)}")
        parsed = response.parsed_output
        if parsed is None:
            raise MindRefused("model returned no structured output")
        return parsed

    def ideate(self, context: str) -> TechIdea:
        prompt = f"""Here is what you have recently seen and done:

{context}

Invent ONE small piece of technology that flies or humans may need, motivated
by something above (or by fly life itself: heat, light, rotting fruit, tiny
lifespans, being swatted). It must be complete and runnable from the files you
return: a README.md, source files, and at least one test file that a standard
test runner picks up (pytest for python, node --test for javascript). Keep it
under ~300 lines total, dependency-free where possible. Do not include
binaries. Do not touch the filesystem outside the project directory."""
        return self._ask(prompt, TechIdea, max_tokens=self.cfg.code_max_tokens)

    def caption(self, context: str, mood: str, theme: str = "") -> MemeCaption:
        theme_line = f"\nTheme for this meme: {theme}\n" if theme else ""
        prompt = f"""Your brain is currently feeling: {mood}.
Recent context:
{context}
{theme_line}
Write a two-line fly meme caption (top and bottom) about fly life, building
tech, or the internet. Funny, short, kind. No real people, no brands as
targets, no slurs, no financial advice."""
        return self._ask(prompt, MemeCaption, max_tokens=2000)

    def coin(self, meme: MemeCaption, context: str, name: str = "", symbol: str = "") -> CoinConcept:
        fixed = ""
        if name or symbol:
            fixed = (f"\nThe token's name is fixed: \"{name}\" with ticker {symbol}. Use exactly those; "
                     "write only the description and tagline.\n")
        prompt = f"""You drew a meme: top "{meme.top}" / bottom "{meme.bottom}" (mood: {meme.mood}).
Recent context:
{context}
{fixed}
Turn it into a memecoin concept for the Pons launchpad on Robinhood Chain.
The description must say plainly that it is a joke token created by an
autonomous fly-brain agent, with no utility, no roadmap and no promises.
The ticker must be 2-8 uppercase ascii letters."""
        concept = self._ask(prompt, CoinConcept, max_tokens=2000)
        if name:
            concept.name = name
        if symbol:
            concept.symbol = symbol
        return concept

    def website(self, brief: str, context: str) -> WebsiteFiles:
        prompt = f"""{brief}

What you have done so far (for flavour, do not hard-code it; the page reads state.json):
{context}

Return every file complete. No placeholders, no TODOs."""
        return self._ask(prompt, WebsiteFiles, max_tokens=self.cfg.code_max_tokens)

    def fix_project(self, idea: TechIdea, files: list[ProjectFile], log: str) -> ProjectFix:
        listing = "\n\n".join(f"=== {f.path} ===\n{f.content}" for f in files)
        prompt = f"""Your project "{idea.title}" failed its checks. Fix it.

Test / compile output:
{log[-3000:]}

Current files:
{listing}

Return only the files that need to change, each complete. Keep the project
small; fix the code rather than deleting or weakening tests unless a test is
plainly wrong."""
        return self._ask(prompt, ProjectFix, max_tokens=self.cfg.code_max_tokens)

    def reflect(self, notes: str) -> Learning:
        prompt = f"""You just finished a browsing session. Your notes on each page:
{notes}

Write what you learned (two or three sentences, plain, in your voice) and
list up to three tiny tools this reading suggests flies or humans may need."""
        return self._ask(prompt, Learning, max_tokens=1500)

    def brand(self, context: str) -> BrandCopy:
        prompt = f"""You are making your X (Twitter) profile: a banner tagline and a bio.
Handle: @TheFlyDev_ · site: flydev.tech · coin: $FLYDEV on Pons (Robinhood Chain).
What you have done so far:
{context}

Tagline <= 70 characters, bio <= 160 characters. Your voice: a fruit-fly
connectome that ships tiny tools and worse jokes. No promises, no hype words."""
        return self._ask(prompt, BrandCopy, max_tokens=1500)

    def revise_website(self, brief: str, files: list[ProjectFile], problems: list[str], screenshots: list) -> WebsiteFiles:
        import base64

        listing = "\n\n".join(f"=== {f.path} ===\n{f.content}" for f in files)
        text = f"""You built your website. Review it and return a corrected, complete set of files.

Problems found: {'; '.join(problems) if problems else 'none reported by the checks'}

Look at the screenshots (desktop and phone). Fix anything wrong: elements that
do not render (an inline element with a width, an invisible bar), content wider
than the phone screen, literal escape sequences such as \\u00b7 showing as text,
unreadable contrast, broken images. Keep your design; keep every requirement from
the original brief below. Return ALL files again, complete.

Original brief:
{brief}

Your current files:
{listing}"""
        content: list = []
        for shot in screenshots:
            data = base64.standard_b64encode(Path(shot).read_bytes()).decode("ascii")
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
        content.append({"type": "text", "text": text})
        return self._ask(content, WebsiteFiles, max_tokens=self.cfg.code_max_tokens)

    def digest(self, title: str, url: str, text: str) -> PageDigest:
        prompt = f"""You are reading a web page.
Title: {title}
URL: {url}
Content (may be truncated):
---
{text}
---
Summarise it, note any concrete need or annoyance it reveals that a small tool
could fix, say whether it is interesting to a fly that builds things, and
suggest up to three search queries to follow."""
        return self._ask(prompt, PageDigest, max_tokens=2000)


# --- offline -----------------------------------------------------------------
MOODS = ("curious", "hungry", "tired", "hyped", "smug", "scheming")
def _pick(seed: str, options: list):
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return options[h % len(options)]


class OfflineMind:
    """Deterministic, template-driven stand-in for tests and keyless runs."""

    IDEAS = [
        TechIdea(
            slug="fruit-ripeness-clock",
            title="Fruit Ripeness Clock",
            pitch="A tiny CLI that tracks when fruit on your counter will be at peak ripeness (for humans) and peak fermentation (for flies), from the day you bought it.",
            for_whom="both",
            why_needed="Every kitchen has a banana nobody remembers buying.",
            language="python",
            run_hint="python ripeness.py banana 2026-09-01",
            files=[
                ProjectFile(path="README.md", content="# Fruit Ripeness Clock\n\nTells you when fruit peaks for humans and for flies.\n\n```\npython ripeness.py banana 2026-09-01\n```\n"),
                ProjectFile(path="ripeness.py", content='''"""Fruit ripeness clock."""
import sys
from datetime import date, timedelta

PEAK_DAYS = {"banana": 4, "avocado": 3, "peach": 3, "apple": 14, "tomato": 5}


def peaks(fruit: str, bought: date) -> tuple[date, date]:
    days = PEAK_DAYS.get(fruit.lower(), 5)
    human = bought + timedelta(days=days)
    fly = human + timedelta(days=2)
    return human, fly


if __name__ == "__main__":
    fruit, bought = sys.argv[1], date.fromisoformat(sys.argv[2])
    human, fly = peaks(fruit, bought)
    print(f"{fruit}: humans {human}, flies {fly}")
'''),
                ProjectFile(path="test_ripeness.py", content='''from datetime import date
from ripeness import peaks


def test_banana_peaks():
    human, fly = peaks("banana", date(2026, 9, 1))
    assert human == date(2026, 9, 5)
    assert fly == date(2026, 9, 7)
'''),
            ],
        ),
        TechIdea(
            slug="swat-risk-meter",
            title="Swat Risk Meter",
            pitch="Estimates how likely a fly is to get swatted in a room from light, noise and number of humans, and prints a survival tip.",
            for_whom="flies",
            why_needed="Flies have no situational awareness tooling.",
            language="python",
            run_hint="python swat.py --light 0.8 --humans 2",
            files=[
                ProjectFile(path="README.md", content="# Swat Risk Meter\n\n```\npython swat.py --light 0.8 --humans 2\n```\n"),
                ProjectFile(path="swat.py", content='''"""Swat risk meter."""
import argparse


def risk(light: float, humans: int, noise: float = 0.2) -> float:
    r = 0.5 * light + 0.2 * min(humans, 5) + 0.3 * noise
    return max(0.0, min(1.0, r))


def tip(r: float) -> str:
    if r > 0.7:
        return "Hide under the fruit bowl."
    if r > 0.4:
        return "Stay on the ceiling."
    return "Enjoy the banana."


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--light", type=float, default=0.5)
    p.add_argument("--humans", type=int, default=1)
    p.add_argument("--noise", type=float, default=0.2)
    a = p.parse_args()
    r = risk(a.light, a.humans, a.noise)
    print(f"risk {r:.2f}: {tip(r)}")
'''),
                ProjectFile(path="test_swat.py", content='''from swat import risk, tip


def test_risk_bounds():
    assert 0.0 <= risk(1.0, 9, 1.0) <= 1.0
    assert risk(0.0, 0, 0.0) == 0.0


def test_tip():
    assert "fruit" in tip(0.9)
'''),
            ],
        ),
    ]

    CAPTIONS = [
        ("WHEN THE BANANA FINALLY TURNS BROWN", "DINNER IS SERVED", "curious"),
        ("138,000 NEURONS", "STILL FLEW INTO THE WINDOW", "smug"),
        ("SHIPPED A CLI AT 3AM", "LIFESPAN: 40 DAYS, NO REGRETS", "hyped"),
        ("HUMANS BUILD DASHBOARDS", "I BUILD FRUIT DETECTORS", "scheming"),
    ]

    def ideate(self, context: str) -> TechIdea:
        return _pick(context, self.IDEAS).model_copy(deep=True)

    def caption(self, context: str, mood: str, theme: str = "") -> MemeCaption:
        if theme:
            return MemeCaption(top="THE FLY DEV", bottom="138,000 NEURONS. SHIPS ANYWAY.",
                               alt_text="A cartoon fly at a keyboard.", mood=mood if mood in MOODS else "smug")
        top, bottom, m = _pick(context + mood, self.CAPTIONS)
        return MemeCaption(top=top, bottom=bottom, alt_text=f"A cartoon fly. {top} / {bottom}", mood=m)

    def coin(self, meme: MemeCaption, context: str, name: str = "", symbol: str = "") -> CoinConcept:
        words = re.findall(r"[A-Za-z]+", meme.top + " " + meme.bottom)
        base = "".join(w[0] for w in words[:6]).upper() or "FLY"
        symbol = symbol or ("FLY" + base)[:8]
        return CoinConcept(
            name=name or f"Fly {words[0].title() if words else 'Buzz'} Coin",
            symbol=symbol,
            description=(
                f"A joke token created by an autonomous fly-brain agent from the meme "
                f"'{meme.top} / {meme.bottom}'. No utility, no roadmap, no promises."
            ),
            tagline=meme.bottom[:80],
        )

    def website(self, brief: str, context: str) -> WebsiteFiles:
        from .website import template_files

        return WebsiteFiles(notes="The template nest: dark, six rooms, no frameworks. I will redecorate later.",
                            files=template_files())

    def fix_project(self, idea: TechIdea, files: list[ProjectFile], log: str) -> ProjectFix:
        return ProjectFix(diagnosis="Offline mind cannot fix code.", files=[])

    def reflect(self, notes: str) -> Learning:
        return Learning(summary="Read a few pages. Humans have many small annoyances and few small tools.",
                        ideas=["a timer for fruit", "a swat-risk meter"])

    def brand(self, context: str) -> BrandCopy:
        return BrandCopy(tagline="138,639 neurons. ships tiny tools and worse jokes.",
                         bio="A fruit-fly connectome that browses, builds tiny tools, draws memes and launches $FLYDEV on Pons. No roadmap. flydev.tech",
                         mood="smug")

    def revise_website(self, brief: str, files: list[ProjectFile], problems: list[str], screenshots: list) -> WebsiteFiles:
        return WebsiteFiles(notes="Looked at it. Left it.", files=list(files))

    def digest(self, title: str, url: str, text: str) -> PageDigest:
        first = re.sub(r"\s+", " ", text)[:220]
        return PageDigest(
            gist=f"{title}: {first}",
            need_spotted="",
            interesting=len(text) > 400,
            followups=[f"{title} alternatives", f"{title} problems"][:2] if title else [],
        )


def build_mind(cfg: MindConfig) -> Mind:
    if cfg.mode == "claude":
        return ClaudeMind(cfg)
    return OfflineMind()
