"""The v2 cut (Nov 4): the demo narrated in English by the Mac's own voice, in the podcast studio's look, with the app's
Hindi in short clips and English subtitles under it. data/video/aftermath-poc-v2.mp4; v1, the cut with no narration,
stays as data/video/aftermath-poc-v1.mp4.

    uv run python scripts/video/edit2.py garage         # the garage photos for the hero (then record it: make_video.py)
    uv run python scripts/video/edit2.py haan           # the stand-in's «हाँ» for c1a
    uv run python scripts/video/narrate.py              # the narration (script v17b), a line at a time
    uv run python scripts/video/edit2.py build          # the timeline, the voices, the score and the mix
    uv run python scripts/video/edit2.py stills 0,12.5  # a look at moments, before rendering it all
    uv run python scripts/video/edit2.py render         # the frames, the film, and what to judge it by

Every frame is drawn by scripts/video/stage.html (Chromium, through render2.js) from the timeline written here: the
phone's frames as record.js saved them and the b-roll's frames are pictures on the page, so a pan or a push-in moves
smoothly. Each narration sentence is placed on its own, and each graphic comes in on the phrase that names it. The
score and room tone come from the podcast studio's seeded generator (its audio/music.py), ducked under every voice; the
voices are levelled alike and the mix is at -14 LUFS.
"""

import argparse
import base64
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from bisect import bisect_right
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from edit import PERSON, VOICES, Take, Timeline, coach, mirror, part, split  # noqa: E402
import narrate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "data" / "video"
V2, BROLL = VIDEO / "v2", VIDEO / "broll"
VO, AUDIO, FRAMES, OUT = V2 / "vo", V2 / "audio", V2 / "frames", V2 / "out"
FILM = VIDEO / "aftermath-poc-v2.mp4"
STUDIO = Path(os.environ.get("PODCAST_STUDIO", Path.home() / "src" / "private" / "podcast" / "studio"))
SR, FPS = 48000, 30

# The phone's whole screen in the frame (left, top, width; its page is 786 x 1704, an iPhone at 2x), on the right, and
# the column beside it.
PAGE_H = 1704
PX, PY, PW = 1344, 46, 456
COL, COLW = 120, 1060

# The podcast studio's moods (audio/moods.ts), as its score generator reads them.
AEOLIAN, PHRYGIAN, DORIAN = [0, 2, 3, 5, 7, 8, 10], [0, 1, 3, 5, 7, 8, 10], [0, 2, 3, 5, 7, 9, 10]


def mood(bpm, scale, progression, chord, brightness, movement, swing, pad, sub, arp, hats, ticks, kick):
    return {"bpm": bpm, "root": "D", "scale": scale, "progression": progression, "chord": chord, "barsPerChord": 2,
            "level": 0, "brightness": brightness, "movement": movement, "swing": swing,
            "pad": dict(zip(("db", "detune", "attack"), pad)), "sub": dict(zip(("db", "grid", "decay"), sub)),
            "arp": dict(zip(("db", "grid", "density", "register", "decay"), arp)),
            "hats": dict(zip(("db", "grid"), hats)), "ticks": dict(zip(("db", "grid"), ticks)),
            "kick": dict(zip(("db", "grid"), kick))}


MOODS = {
    "hook": mood(104, AEOLIAN, [0, 0, 5, 6], [0, 4, 8], 1100, 0.7, 0, (0, 9, 0.7), (-2, "X.x.x.x.X.x.x.x.", 0.11),
                 (-8, "x..x..x...x..x..", 0.75, [62, 81], 0.32), (-60, ""), (-16, "x.x.x.x.x.x.x.x."), (-60, "")),
    "tension": mood(96, PHRYGIAN, [0, 5, 0, 1], [0, 2, 4], 720, 0.6, 0, (0, 7, 1.6), (-1, "X.x.............", 0.3),
                    (-8, "x.......x.......", 0.5, [62, 79], 0.9), (-60, ""), (-16, "x...x...x...x..."), (-60, "")),
    "focus": mood(100, DORIAN, [0, 3, 2, 6], [0, 2, 4, 8], 1250, 0.5, 0, (0, 8, 0.8), (-3, "x...x...x...x...", 0.25),
                  (-8, "x.x.x.x.x.x.x.x.", 0.7, [62, 81], 0.3), (-15, "..x...x...x...x."), (-60, ""), (-60, "")),
    "resolve": mood(96, AEOLIAN, [5, 2, 6, 0], [0, 2, 4, 8], 1600, 0.4, 0, (0, 12, 1.2), (-9, "", 0.8),
                    (-8, "x...x...x...x...", 0.6, [62, 81], 0.8), (-19, "x.x.x.x.x.x.x.x."), (-60, ""), (-60, "")),
}

CHAPTERS = {1: "THE DANGER", 2: "WHY IT MATTERS", 3: "HOW IT WORKS", 4: "THE LANGUAGE PROBLEM", 5: "PROOF"}

CREDITS = [
    ("Narration", "macOS text-to-speech (Siri voice). The app's voices: Meta MMS-TTS (CC BY-NC 4.0); the person's is a "
                  "synthetic stand-in."),
    ("Staged", "No generator was run. The garage photos and clip: the builder's own, the house number painted out. "
               "Screen: the real app, recorded."),
    ("Models", "SAM 3.1 (on Apple MLX) · Muse Glimmer · Muse Spark and Voice Transcribe · Meta MMS"),
    ("Footage", "U.S. Coast Guard (Ian Gray; MSST Miami) · National Guard Bureau (Michael Dann) · U.S. Marine Corps "
                "(Justin X. Toledo), via DVIDS · NASA SVS / Black Marble · CDC. Public domain. No agency endorses "
                "Aftermath; DoW visual information does not imply DoW endorsement."),
    ("Figures", "CPSC 88 FR 24346 · Iqbal et al. 2012 · Portillo et al. 2024 · CDC · this repo's evals and tests "
                "(DIODE, Hypersim, FLEURS, the readers' comparison)"),
    ("Music and type", "Procedural score, generated · Inter and JetBrains Mono (SIL OFL 1.1)"),
]


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def url(path: Path) -> str:
    return Path(path).resolve().as_uri()


# --- items: what stage.html draws ------------------------------------------------------------------------------------

def H(content: str, x=None, y=None, w=None, cls="", at=0.0, until=None, anim="rise", style="", rot=0, h=None,
      ease=None) -> dict:
    item = {"kind": "html", "html": content, "x": x, "y": y, "cls": cls, "at": round(at, 3), "anim": anim,
            "style": style, "rot": rot}
    if ease:
        item["ease"] = ease
    if w:
        item["w"] = w
    if h:
        item["h"] = h
    if until is not None:
        item["until"] = round(until, 3)
    return item


def tag(chapter: int | None, at=0.0, anim="none", text=None) -> dict:
    label = text or CHAPTERS[chapter]
    number = f"<b>{chapter:02d}</b>" if chapter else ""
    return H(f"{number}{esc(label)}", cls="tag", at=at, anim=anim)


def source(text: str, at=0.0, video: str = "") -> dict:
    more = f"&nbsp;&nbsp;&nbsp;<b>VIDEO</b>{esc(video)}" if video else ""
    return H(f"<b>SOURCE</b>{esc(text)}{more}" if text else f"<b>VIDEO</b>{esc(video)}", cls="source", at=at,
             anim="fade")


def stamp(text, color, x, y, at, rot=-5, size=56, until=None) -> dict:
    return H(esc(text).replace("\n", "<br>"), x, y, cls="stamp", at=at, anim="slam", rot=rot, until=until,
             style=f"color:var(--{color});font-size:{size}px;line-height:1.08")


def pill(text, color, x, y, at, size=36, until=None, anim="pop") -> dict:
    return H(esc(text), x, y, cls="pill", at=at, anim=anim, until=until,
             style=f"color:var(--{color});background:var(--{color}-soft);font-size:{size}px")


def big(text, color, x, y, at, size=128, until=None, anim="pop") -> dict:
    return H(esc(text), x, y, cls="big", at=at, anim=anim, until=until, style=f"color:var(--{color});font-size:{size}px")


def text(content, x, y, w, at, cls="body", until=None, anim="rise", style="") -> dict:
    return H(content, x, y, w, cls=cls, at=at, until=until, anim=anim, style=style)


def sub(who: str, said: str, at: float, until: float, color="muted", y=640) -> dict:
    """The English of a Hindi line, beside the phone: who says it, and what."""
    return H(f'<div class="who">{esc(who)}</div><div class="say">{esc(said)}</div>', COL, y, COLW, cls="sub", at=at,
             until=until, style=f"border-left-color:var(--{color})")


def video(key: str, x, y, w, h, at=0.0, until=None, panel=True, radius=22, push=0.012) -> dict:
    folder = V2 / "broll" / key
    return {"kind": "video", "dir": url(folder), "count": len(list(folder.glob("*.jpg"))), "x": x, "y": y, "w": w,
            "h": h, "at": round(at, 3), "panel": panel, "radius": radius, "push": push, "anim": "none",
            **({"until": round(until, 3)} if until is not None else {})}


def shade() -> dict:
    return H("", 0, 0, 1920, cls="shade", h=1080, anim="none")


# --- the app's parts, as a diagram (m2 and m3) -------------------------------------------------------------------------

ARCH = {"phone": (72, 240, 250, 260), "laptop": (392, 140, 720, 460), "api": (392, 650, 720, 290),
        "rules": (1182, 215, 360, 310), "reply": (1612, 270, 236, 200)}  # left, top, width, height
PHONE_ICON = ('<svg width="44" height="70" viewBox="0 0 44 70" fill="none" stroke="#eef2fa" stroke-width="4">'
              '<rect x="3" y="3" width="38" height="64" rx="8"/><path d="M17 57h10"/></svg>')
SPEAKER = ('<svg width="56" height="48" viewBox="0 0 28 24" fill="none" stroke="#eef2fa" stroke-width="2.2" '
           'stroke-linejoin="round" stroke-linecap="round"><path d="M3 9h5l6-5v16l-6-5H3z"/>'
           '<path d="M18 8a6 6 0 0 1 0 8M21 5a10 10 0 0 1 0 14"/></svg>')


def architecture(at: dict) -> list[dict]:
    """The app's parts as a diagram the narration builds: the phone's page; the laptop, with SAM 3.1 on MLX, MMS and
    Muse Glimmer; or, with a signal, Meta's API, with Muse Spark 1.3 and Voice Transcribe; the rulebook, which decides;
    and the spoken reply. A part comes in at its time in ``at`` (seconds into the scene), or is there from the start if
    its time is None (the scene before showed it); a box not in ``at`` is a dashed outline until it's named."""
    def when(part: str, anim: str = "pop") -> dict:
        return {"at": 0.0, "anim": "none"} if at[part] is None else {"at": at[part], "anim": anim}

    def card(part: str, html_: str, color: str, padding: str = "0", dashed: bool = False) -> dict:
        x, y, w, h = ARCH[part]
        return H(html_, x, y, w, h=h, cls="card", style=f"padding:{padding};border-color:var(--{color})"
                 + (";border-style:dashed" if dashed else ""), **when(part))

    def row(part: str, name: str, what: str, y: float) -> dict:
        return H(f'<div style="font:700 40px Inter">{esc(name)}</div><div style="font:500 28px/1.3 Inter;'
                 f'color:var(--muted);margin-top:6px">{esc(what)}</div>', X0, y, 640, **when(part, "rise"))

    def label(part: str, text_: str, y: float) -> dict:
        return H(f'<div class="k" style="font-size:28px">{esc(text_)}</div>', X0, y, **when(part, "fade"))

    def badge(part: str, text_: str, color: str, x: float, y: float) -> dict:
        return H(esc(text_), x, y, cls="pill", style=f"color:var(--{color});background:var(--{color}-soft);"
                 "font-size:24px", **when(part))

    X0 = ARCH["laptop"][0] + 36
    ghosts = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="none" stroke="#2b3a5a" '
                     'stroke-width="3" stroke-dasharray="14 12"/>' for part, (x, y, w, h) in ARCH.items()
                     if at.get(part, 1.0) is not None and part != "phone")
    arrows = []
    for parts, d in ((("phone", "laptop"), "M330 370H382M366 354l16 16-16 16"),
                     (("laptop", "rules"), "M1120 370H1172M1156 354l16 16-16 16"),
                     (("rules", "reply"), "M1550 370H1602M1586 354l16 16-16 16"),
                     (("api", "rules"), "M1120 795H1362V533M1346 549l16-16 16 16")):
        if not all(p in at for p in parts):
            if all(p in at for p in parts if p not in ("rules", "reply")) and "laptop" in at:
                arrows.append(f'<path d="{d}" fill="none" stroke="#2b3a5a" stroke-width="4" stroke-dasharray="10 10"/>')
            continue
        times = [at[p] for p in parts if at[p] is not None]
        if times and max(times) > 0:  # dashed until it draws on
            arrows.append(f'<path d="{d}" fill="none" stroke="#2b3a5a" stroke-width="4" stroke-dasharray="10 10"/>')
        timing = f'data-at="{max(times):.2f}" data-dur="0.3" ' if times else ""
        arrows.append(f'<path class="d" {timing}d="{d}" stroke="#93a0b8" stroke-width="5"/>')
    items = [{"kind": "draw", "x": 0, "y": 0, "at": 0.0, "anim": "none",
              "svg": f'<svg width="1920" height="1080" viewBox="0 0 1920 1080">{ghosts}</svg>'}]
    if "phone" in at:
        items.append(card("phone", f'{PHONE_ICON}<div class="k" style="font-size:28px;margin-top:14px">PHONE</div>'
                                   '<div style="font:700 36px Inter;margin-top:8px">web page</div>'
                                   '<div style="font:500 28px Inter;color:var(--muted);margin-top:6px">photo · voice'
                                   '</div>', "ink", "26px 30px"))
    if "laptop" in at:
        items.append(card("laptop", "", "blue"))
    shown = [("laptop-k", lambda: label("laptop-k", "LAPTOP", 166)),
             ("offline", lambda: badge("offline", "no internet", "blue", 856, 158)),
             ("sam", lambda: row("sam", "SAM 3.1", "finds the door, then the distance ±6%", 226)),
             ("mlx", lambda: badge("mlx", "Apple MLX", "ink", 612, 230)),
             ("mms", lambda: row("mms", "Meta MMS", "hears and speaks Hindi", 342)),
             ("glimmer", lambda: row("glimmer", "Muse Glimmer", "reads the facts into a strict schema", 458)),
             ("api", lambda: card("api", "", "blue", dashed=True)),
             ("api", lambda: label("api", "META'S API", 676)),
             ("api", lambda: badge("api", "with a signal", "blue", 824, 668)),
             ("api", lambda: H("or", 734, 604, cls="mono", style="font-size:30px;color:var(--muted)",
                               **when("api", "fade"))),
             ("spark", lambda: row("spark", "Muse Spark 1.3", "reads the facts", 728)),
             ("transcribe", lambda: row("transcribe", "Muse Voice Transcribe", "hears the speech", 832)),
             ("rules", lambda: card("rules", '<div class="k" style="font-size:28px">RULEBOOK</div>'
                                    '<div class="mono" style="font-weight:700;font-size:36px;margin-top:12px">rules.py'
                                    '</div><div style="font:600 30px/1.25 Inter;margin-top:12px">decides every '
                                    'warning</div><div style="font:500 26px/1.35 Inter;color:var(--muted);'
                                    'margin-top:12px">cites CDC · CPSC ·<br>NIST · Ready.gov</div>', "ink",
                                    "28px 34px")),
             ("reply", lambda: card("reply", f'{SPEAKER}<div class="k" style="font-size:28px;margin-top:12px">REPLY'
                                    '</div><div style="font:600 30px/1.25 Inter;margin-top:8px">spoken, in Hindi</div>',
                                    "line", "26px 30px")),
             ("never", lambda: badge("never", "doesn't decide", "red", 720, 462)),
             ("never", lambda: badge("never", "doesn't decide", "red", 745, 732))]
    items += [make() for part, make in shown if part in at]
    items.append({"kind": "draw", "x": 0, "y": 0, "at": 0.0, "anim": "none",
                  "svg": f'<svg width="1920" height="1080" viewBox="0 0 1920 1080">{"".join(arrows)}</svg>'})
    return items


# --- the phone ---------------------------------------------------------------------------------------------------------

def seen(take: Take, n: int) -> dict:
    return next(e["where"] for e in take.events if e["kind"] == "shown" and e["reply"] == n)


def tapped(take: Take, selector: str, k: int = 1) -> dict:
    return [e["where"] for e in take.events if e["kind"] == "tap" and e["selector"] == selector][k - 1]


def phone(take: Take, segments: list[tuple], marks=None, blurs=None, x=PX, y=PY,
          w=PW) -> tuple[dict, Timeline, float]:
    """The whole screen over these stretches of the take ((start, end) or (start, end, hold), as edit.py's
    phone_video), never scrolled or cropped: the part being talked about gets a soft highlight instead. ``marks``
    gives, from the stretches' timeline, when each comes in: (time, the part's place on the page, colour), or (time,
    None) for none; ``blurs``, the parts of the page blurred from a time on: (time, top, height), in page pixels. Its
    length."""
    times = [t for t, _ in take.frames]
    frames, clock = [], 0.0
    for a, b, *hold in segments:
        i = max(0, bisect_right(times, a) - 1)
        frames.append([round(clock, 4), url(take.frames[i][1])])
        for j in range(i + 1, len(times)):
            if times[j] >= b:
                break
            frames.append([round(clock + times[j] - a, 4), url(take.frames[j][1])])
        clock += b - a + (hold[0] if hold else 0)
    at = Timeline(segments)
    boxes = [[0, None, 0, ""]]
    for t, where, *color in (marks(at) if marks else []):
        boxes.append([round(max(0.0, t), 3), None, 0, ""] if where is None else
                     [round(max(0.0, t), 3), where["y"], where["h"], color[0] if color else "amber"])
    item = {"kind": "phone", "x": x, "y": y, "w": w, "h": round(w * PAGE_H / 786), "frames": frames,
            "marks": sorted(boxes, key=lambda box: box[0]), "anim": "none"}
    if blurs:
        item["blurs"] = [[round(max(0.0, t), 3), top, h] for t, top, h in blurs(at)]
    return item, at, clock


def first_shown(take: Take, item: dict, when: float) -> float:
    """The phone's time of its first frame recorded at or after ``when`` in the take: where a new page appears."""
    recorded = {url(path): t for t, path in take.frames}
    return next(clock for clock, u in item["frames"] if recorded[u] >= when)


def inside_frame(scenes: list[dict]) -> None:
    """Every phone whole inside the 1920 x 1080 frame, bezel and all, to the end of its scene's slow push-in."""
    for sc in scenes:
        grow = 1 + (0.0045 if sc.get("push") is None else sc["push"]) * (sc["end"] - sc["start"])
        for it in sc["items"]:
            if it["kind"] != "phone":
                continue
            box = (it["x"] - 18, it["y"] - 18, it["x"] + it["w"] + 18, it["y"] + it["h"] + 18)
            x0, x1 = 960 + (box[0] - 960) * grow, 960 + (box[2] - 960) * grow
            y0, y1 = 540 + (box[1] - 540) * grow, 540 + (box[3] - 540) * grow
            assert x0 >= 0 and y0 >= 0 and x1 <= 1920 and y1 <= 1080, f"{sc['name']}: the phone leaves the frame"


# --- sound -------------------------------------------------------------------------------------------------------------

LOADED: dict[str, np.ndarray] = {}


def load(path: Path) -> np.ndarray:
    """Mono at 48 kHz."""
    key = str(path)
    if key not in LOADED:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", key, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        LOADED[key] = np.frombuffer(raw, np.float32).copy()
    return LOADED[key]


def audible(x: np.ndarray, floor_db=-45.0) -> tuple[float, float]:
    """Where a clip's sound starts and ends, in seconds."""
    loud = np.flatnonzero(np.abs(x) > 10 ** (floor_db / 20))
    return (loud[0] / SR, loud[-1] / SR) if len(loud) else (0.0, len(x) / SR)


def active_rms_db(x: np.ndarray) -> float:
    win = SR // 100
    n = len(x) // win
    power = (x[: n * win].reshape(n, win) ** 2).mean(axis=1)
    active = power[power > power.max() * 1e-4]
    return float(10 * np.log10(active.mean()))


def level_gain(x: np.ndarray, target=-20.0, peak=-1.5) -> float:
    """The gain that puts a voice clip at the narration's level: -20 dBFS active RMS, peaks under -1.5 dBFS."""
    gain = 10 ** ((target - active_rms_db(x)) / 20)
    top = np.abs(x).max() * gain
    return gain * min(1.0, 10 ** (peak / 20) / top) if top > 0 else gain


class Said:
    """A narration line placed in the film, whole (a line is never cut): when its sentences and words are said."""

    def __init__(self, line: str, at: float) -> None:
        info = LINES[line]
        self.line, self.text, self.sentences = line, info["text"], info["sentences"]
        self.start, self.end = at, at + info["seconds"]
        self.spans = {k: (at + a, at + b) for k, (a, b) in enumerate(zip(info["starts"], info["ends"]))}
        self.words = [(at + a, at + b) for _, a, b in info["words"]]

    def at(self, phrase: str, end: bool = False) -> float:
        """When a phrase is said, as Whisper heard the take: its first word's start, or with end, its last word's
        end."""
        if phrase not in self.text:
            raise KeyError(f"{phrase!r} isn't in {self.line}")
        i = self.text.index(phrase)
        if end:
            return self.words[len(self.text[: i + len(phrase)].split()) - 1][1]
        return self.words[len(self.text[: i + 1].split()) - 1][0]

    def __getitem__(self, k: int) -> tuple[float, float]:
        return self.spans[k]


def slot(said: Said, after: str, before: str) -> tuple[float, float]:
    """The silence a line leaves between two phrases for another voice (c1a's «हाँ»): its longest quiet run there."""
    x = load(VO / f"{said.line}.wav")
    win = SR // 100
    a, b = int((said.at(after, end=True) - said.start) * SR), int((said.at(before) - said.start + 0.6) * SR)
    seg = x[a:b]
    power = (seg[: len(seg) // win * win].reshape(-1, win) ** 2).mean(axis=1)
    quiet = power < (x ** 2).max() * 1e-5
    best, run = (0, 0), None
    for k, q in enumerate(list(quiet) + [False]):
        if q and run is None:
            run = k
        elif not q and run is not None:
            best = max(best, (run, k), key=lambda r: r[1] - r[0])
            run = None
    return said.start + (a + best[0] * win) / SR, said.start + (a + best[1] * win) / SR


class Cut:
    def __init__(self) -> None:
        self.t = 0.0
        self.scenes: list[dict] = []
        self.sounds: list[dict] = []  # {at, file, start, end, gain, kind}
        self.speech: list[tuple[float, float]] = []
        self.beats: list[dict] = []
        self.moods: list[tuple[float, str]] = [(0.0, "hook")]
        self.dips: list[tuple[float, float]] = []  # where the music and room tone drop out, so a word sits alone

    def scene(self, seconds: float, items: list[dict], glow="blue", xfade=0.0, push=None, name="") -> dict:
        s = {"name": name, "start": round(self.t, 4), "end": round(self.t + seconds, 4), "glow": glow,
             "items": [i for i in items if i]}
        if xfade:
            s["xfade"] = xfade
        if push is not None:
            s["push"] = push
        self.scenes.append(s)
        self.t += seconds
        return s

    def narrate(self, line: str, at: float) -> Said:
        said = Said(line, at)
        self.sounds.append({"at": said.start, "file": str(VO / f"{line}.wav"), "start": 0.0,
                            "end": LINES[line]["seconds"], "gain": 1.0, "kind": "narration"})
        self.speech.append((said.start, said.end))
        return said

    def voice(self, at: float, file: Path, kind: str, start: float | None = None, end: float | None = None,
              boost_db: float = 0.0) -> float:
        """An app or stand-in clip, its sound from ``at``, levelled with the narration (and raised by ``boost_db``).
        When its sound ends."""
        x = load(file)
        a, b = audible(x)
        a = max(0.0, a - 0.03) if start is None else start
        b = min(len(x) / SR, b + 0.06) if end is None else end
        gain = level_gain(x[int(a * SR): int(b * SR)]) * 10 ** (boost_db / 20)
        self.sounds.append({"at": at, "file": str(file), "start": a, "end": b, "gain": gain, "kind": kind})
        self.speech.append((at, at + b - a))
        return at + b - a

    def sfx(self, name: str, at: float, db: float = -4.0) -> None:
        lead = {"whoosh": 0.18, "sting": 3.6}.get(name, 0.0)  # whoosh peaks at 0.18 s; the sting hits at 3.6 s
        self.sounds.append({"at": max(0.0, at - lead), "file": str(AUDIO / "sfx" / f"{name}.wav"), "start": 0.0,
                            "end": None, "gain": 10 ** (db / 20), "kind": "sfx"})

    def beat(self, id: str, kind: str, start: float, end: float, text: str, key: float, visual: str) -> None:
        self.beats.append({"id": id, "kind": kind, "start": round(start, 2), "end": round(end, 2),
                           "key": round(key, 2), "text": text, "visual": visual})

    def said(self, said: Said, key: float, visual: str) -> None:
        self.beat(said.line, "narration", said.start, said.end, said.text, key, visual)


NARRATED_TESTS = 840  # p3: "all eight hundred and forty tests"
HAAN_BOOST_DB = 0.0  # c1a's «हाँ» over the other stand-in lines: +2 dB took its peak to 0 dBFS, and the mix's limiter
#                     pulled it back 5 dB, so it stays level with them


def tests_collected() -> int:
    """How many tests the suite has, as pytest collects them."""
    done = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True)
    return int(re.search(r"(\d+) tests? collected", done.stdout).group(1))


def garage_english(take: Take) -> dict:
    """The garage take's turns in English, from the app's own words at the readings it gave: the subtitles for its
    Hindi. Both photos carry the wide-door warning, so they're read as possibly too far, as the app read them."""
    from aftermath.conversation import Conversation

    class NoModel:
        def ask_json(self, *args, **kw):
            raise RuntimeError("these turns are all quick ones")

    c = Conversation(NoModel(), language="en")
    c.opening()
    near, far = take.reply(2)["door"], take.reply(3)["door"]
    out = {"garage-near": c.reply("", door=(near["feet"], near["lowest"]), reads_far=True).text,
           "garage-far": c.reply("", door=(far["feet"], far["lowest"]), reads_far=True).text,
           "garage-outside": c.reply("Yes, it's outside.").text}
    return {key: split(text) for key, text in out.items()}


def clip_seconds(file: Path) -> float:
    a, b = audible(load(file))
    return b + 0.06 - max(0.0, a - 0.03)


LINES: dict = {}


# --- the film ----------------------------------------------------------------------------------------------------------

def build() -> dict:
    from aftermath.guidance import SOURCES
    from aftermath.phrases import PAGE, door_note

    LINES.update(json.loads((VO / "lines.json").read_text()))
    english = {key: split(value) for key, value in mirror().items()}
    labels = PAGE["en"]["placement"]
    hero, hero_old, cold, symptom = Take("garage"), Take("hero"), Take("cold-open"), Take("symptom")
    english.update(garage_english(hero))
    c = Cut()
    mark = ('<svg width="150" height="150" viewBox="0 0 24 24" fill="none" stroke="#64a8ff" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/>'
            '<path d="M10 20v-6h4v6"/></svg>')
    hindi = "font-family:'Noto Sans Devanagari',Inter"
    still = 0.0015  # a phone scene's push-in: slow enough that the phone stays whole in the frame

    # 0. The first frame, which is also the thumbnail: the verdict at 10 ft, and the question.
    near = hero.replied(2)
    item, _, _ = phone(hero, [(near + 1.5, near + 1.6, 0.5)], lambda at: [(0, seen(hero, 2)["head"], "red")])
    c.scene(0.5, [tag(None, text="AFTERMATH"), item,
                  text("How far is<br>far enough?", COL, 230, COLW, 0, cls="hero", anim="none"),
                  dict(stamp(labels["too close"], "red", COL + 10, 560, 0, size=76), anim="none")],
            glow="red", push=0.0, name="poster")
    c.beat("poster", "title", 0, 0.5, "", 0.0, f"The phone, whole, shows the red verdict card for the garage photo "
           f"({hero.reply(2)['door']['feet']:.1f} ft), highlighted; beside it 'How far is far enough?' and a TOO CLOSE "
           "stamp.")

    # 1. Cold open, no narration: the person says where the generator is; the app answers at once.
    start = c.t
    talk, back = cold.at("voice"), cold.replied(2)
    said_garage = clip_seconds(VOICES / "garage.wav")
    garage = coach(cold, 2, [0], upto=",")[0][0]
    garage_hi = part(split(cold.reply(2)["text"])[0], ",")
    garage_en = part(english["garage"][0], ",") + "."
    first = (talk + 0.15, talk + 0.15 + 0.15 + said_garage + 0.1)
    hold = 0.35 + clip_seconds(garage) + 0.15
    never = seen(cold, 3)["verdict"]
    item, at, length = phone(cold, [first, (back - 0.1, back + 0.4, hold)],
                             lambda at: [(0.1, tapped(cold, "#talk")["talk"], "blue"), (at(back - 0.1), never, "red")])
    person_at = start + 0.15
    person_end = c.voice(person_at, VOICES / "garage.wav", "person")
    shown = start + at(back)
    coach_at = shown + 0.35
    coach_end = c.voice(coach_at, garage, "app")
    c.sfx("stamp", shown + 0.05, -6)
    c.scene(length, [item,
                     text("STAGED · SYNTHETIC VOICES<br>NO GENERATOR RUNNING", COL, 150, COLW, 0, cls="label mono",
                          anim="fade", style="font-size:32px;letter-spacing:.08em"),
                     sub("PERSON · HINDI", PERSON["garage"], person_at - start - 0.15, shown - start),
                     stamp(labels["never indoors"], "red", COL + 10, 330, shown - start + 0.05),
                     sub("APP · HINDI", garage_en, coach_at - start - 0.1, length, color="red")],
            glow="red", push=still, name="cold-open")
    c.beat("garage", "person", person_at, person_end, PERSON["garage"], person_at + 1.0,
           "The phone listens, its talk button highlighted; beside it the English subtitle of the person's Hindi: the "
           "generator is in the garage.")
    c.beat("garage-reply", "app", coach_at, coach_end, garage_en, shown + 0.3,
           f"The phone's red NEVER INDOORS card highlighted; beside it a red NEVER INDOORS stamp and, under APP · "
           f"HINDI, the subtitle '{garage_en}'")

    # 2. 01 The danger. h1: "that's how" is the garage just seen; then why a garage with its door open kills.
    start = c.t
    h1 = c.narrate("h1", start + 0.15)
    frozen, _, _ = phone(cold, [(back + 0.3, back + 0.4, 20)], lambda at: [(0, never, "red")])
    deaths_at = h1.at("generator deaths") - 0.1
    c.scene(deaths_at - start, [frozen, tag(1, anim="rise"),
                                dict(stamp(labels["never indoors"], "red", COL + 10, 330, 0), anim="none")],
            glow="red", push=still, name="h1-that")
    c.scene(h1[1][0] - 0.1 - c.t, [video("ian-drone", 0, 0, 1920, 1080, panel=False, radius=0, push=0.02), shade(),
                                   tag(1), source("", video="U.S. Coast Guard / DVIDS")], glow="red",
            name="h1-aftermath")
    c.said(h1, h1.start + 0.1, "The phone's red NEVER INDOORS card from the garage, held and highlighted, with the red "
                               "NEVER INDOORS stamp beside it; chapter tag 01 THE DANGER.")
    c.beat("h1-aftermath", "narration", deaths_at, h1[0][1], h1.sentences[0], deaths_at + 0.4,
           "Hurricane Ian's wreckage from the air, full frame; chapter tag 01 THE DANGER; VIDEO U.S. Coast Guard / "
           "DVIDS.")
    start = c.t
    c.sfx("whoosh", start + 0.05, -11)
    c.scene(h1.at("with the door open") - 0.1 - start,
            [video("garage-door", 690, 40, 540, 960, push=0.01), tag(1),
             pill("garage", "ink", 1290, 470, h1.at("in the garage") - start),
             source("", video="the builder's own garage")], glow="red", name="h1-real")
    c.beat("h1-real", "narration", h1[1][0], c.t, "Someone runs the generator in the garage", h1.at("in the garage")
           + 0.4, "The builder's own garage door, closed, just starting to lift, in a portrait panel; a pill 'garage'.")
    start = c.t
    gen_at, door_at, air_at = 0.0, 0.05, h1.at("plenty of air") - start
    puffs = "".join(f'<g data-show="{max(0.0, air_at - 0.6 + 0.12 * i):.2f}"><circle cx="{x}" cy="{y}" r="{r}" '
                    'fill="rgba(147,160,184,.30)"/></g>'
                    for i, (x, y, r) in enumerate([(905, 430, 34), (960, 395, 44), (860, 385, 30), (1020, 430, 38),
                                                   (700, 400, 40), (600, 360, 46), (480, 400, 42), (380, 350, 36),
                                                   (300, 420, 40)]))
    garage_svg = ('<svg width="1500" height="640" viewBox="0 0 1500 640">'
                  '<path class="d" data-at="0" data-dur="0.5" d="M40 560H1460" stroke="#24324e" stroke-width="6"/>'
                  '<path class="d" data-at="0.1" data-dur="0.7" d="M180 560V300l250-170 250 170v260" stroke="#93a0b8" '
                  'stroke-width="7"/>'
                  '<path class="d" data-at="0.3" data-dur="0.6" d="M680 560V330h560v230" stroke="#93a0b8" '
                  'stroke-width="7"/>'
                  f'<g data-show="{gen_at}"><rect x="830" y="455" width="170" height="100" rx="14" fill="#16223a" '
                  'stroke="#ff4359" stroke-width="7"/><path d="M856 455v-30h118v30M876 508h78" fill="none" '
                  'stroke="#ff4359" stroke-width="7"/></g>'
                  f'<g data-show="{door_at}"><rect x="740" y="345" width="440" height="36" rx="5" fill="#16223a" '
                  'stroke="#ffb547" stroke-width="5"/><path d="M752 357h416M752 369h416" stroke="#ffb547" '
                  'stroke-width="3"/></g>' + puffs + '</svg>')
    c.sfx("pop", start + door_at, -10)
    c.scene(h1.end + 0.15 - start, [tag(1), {"kind": "draw", "x": 210, "y": 250, "at": 0.0, "anim": "none",
                                             "svg": garage_svg},
                                    pill("garage", "ink", 1030, 190, gen_at), pill("door open", "amber", 1330, 190,
                                                                                    door_at)],
            glow="red", name="h1-garage")
    c.beat("h1-garage", "narration", start, h1.end, "with the door open, because it feels like there's plenty of air.",
           h1.at("plenty of air"), "A drawn garage with its door rolled open and a red generator inside, grey CO "
                                   "drifting from it into the house; pills 'garage' and 'door open'.")

    # h2: who the voice was, and the app's no, in Hindi; then the question.
    start = c.t
    h2 = c.narrate("h2", start + 0.1)
    c.scene(h2.at("where it goes instead") - 0.1 - start, [
        tag(1),
        H(f'<div class="k">THE APP, IN HINDI</div><div class="head" style="margin-top:22px;{hindi};'
          f'font-size:64px;line-height:1.35">{esc(garage_hi)}</div><div class="label" style="margin-top:18px">'
          f'{esc(garage_en)}</div>', 260, 280, 1400, cls="card", anim="none", style="border-color:var(--red)")],
        glow="red", name="h2-no")
    c.said(h2, h2.at("in Hindi"), f"A card THE APP, IN HINDI with the app's Hindi line and '{garage_en}' under it.")
    start = c.t
    c.sfx("whoosh", start + 0.05, -9)
    c.scene(h2.end + 0.15 - start, [tag(1), text("Where should it<br>go instead?", 0, 330, 1920, 0.0, cls="hero",
                                                  style="text-align:center", anim="none"),
                                     {"kind": "draw", "x": 560, "y": 640, "at": 0.15, "anim": "none",
                                      "svg": '<svg width="800" height="80" viewBox="0 0 800 80"><path class="d" '
                                             'data-at="0" data-dur="0.6" d="M20 40H780" stroke="#ffb547" '
                                             'stroke-width="6"/><path class="d" data-at="0.45" data-dur="0.2" '
                                             'd="M20 18V62M780 18V62" stroke="#ffb547" stroke-width="6"/></svg>'}],
            glow="red", name="h2-question")
    c.beat("h2-question", "narration", h2[1][0], h2.end, h2.sentences[1], h2.at("where it goes instead") + 0.3,
           "'Where should it go instead?' in big white type with an amber measuring line drawn under it.")

    # h3: the photo from 10 ft, the app's verdict in Hindi, the narration's.
    start = c.t
    photo1 = hero.at("photo", 1)
    close = coach(hero, 2, [1], upto=":")[0][0]
    n3 = Said("h3", start + 0.95)
    app_at = n3.end + 0.15
    end = app_at + clip_seconds(close) + 0.2
    item, at, length = phone(hero, [(photo1 - 0.45, photo1 + 0.3), (near - 0.1, near + 0.9, end - start - 1.75)],
                             lambda at: [(at(near - 0.1) + 0.15, seen(hero, 2)["head"], "red")])
    h3 = c.narrate("h3", n3.start)
    app_end = c.voice(app_at, close, "app")
    c.sfx("pop", h3.at("about ten feet"), -8)
    c.sfx("stamp", h3.at("far too close"), -5)
    near_en = part(english["garage-near"][1], ":") + "."
    c.scene(length, [item, tag(1),
                     big("10 ft", "red", COL, 250, h3.at("about ten feet") - start),
                     stamp(labels["too close"], "red", COL + 10, 470, h3.at("far too close") - start),
                     sub("APP · HINDI", near_en, app_at - start - 0.1, length, color="red")], glow="red", name="h3",
            push=still)
    c.said(h3, h3.at("far too close"), "The phone, whole, shows its red verdict card for the garage photo from 10 ft, "
                                       "highlighted; beside it a big red '10 ft' and a red TOO CLOSE stamp.")
    c.beat("near-reply", "app", app_at, app_end, near_en, app_at + 0.4,
           f"Beside the phone: a big red '10 ft', the red TOO CLOSE stamp and, under APP · HINDI, the subtitle "
           f"'{near_en}'")

    # h4: from 30 ft the app asks if it's outside; the person's yes; still borderline, since a garage door can read
    # long, and the question about the door's height. The app's real verdict on the user's garage.
    start = c.t
    photo2, far, answer = hero.at("photo", 2), hero.replied(3), hero.replied(4)
    said_yes = clip_seconds(VOICES / "outside.wav")
    card_at = 0.5 + 0.1
    yes_at = start + card_at + 0.45
    answered_at = yes_at + said_yes + 0.2 - start  # the borderline card
    h4 = Said("h4", start + answered_at + 0.35)
    end = h4.end + 0.2
    ask_at = h4.at("asks the door's height") - start
    border_at = h4.at("borderline") - start
    segments = [(photo2 - 0.3, photo2 + 0.2), (far - 0.1, far + 0.7, answered_at - 1.3),
                (answer - 0.1, answer + 0.9, end - start - answered_at - 1.0)]
    w3, w4 = seen(hero, 3), seen(hero, 4)
    item, at, length = phone(hero, segments,
                             lambda at: [(card_at + 0.1, w3["head"], "amber"),
                                         (yes_at - start - 0.1, w3["talk"], "blue"),
                                         (answered_at + 0.15, w4["head"], "amber"),
                                         (ask_at - 0.1, w4["reply"], "amber")])
    yes_end = c.voice(yes_at, VOICES / "outside.wav", "person")
    c.narrate("h4", h4.start)
    feet = hero.reply(3)["door"]["feet"]
    ask_en = " ".join(english["garage-outside"][1:])
    c.sfx("pop", start + card_at + 0.05, -9)
    c.sfx("pop", start + answered_at + 0.05, -10)
    c.sfx("stamp", start + border_at, -6)
    c.sfx("pop", start + ask_at, -9)
    c.scene(length, [item, tag(1),
                     big(f"{feet:.0f} ft", "amber", COL, 250, card_at),
                     sub("PERSON · HINDI", PERSON["outside"], yes_at - start - 0.15, ask_at - 0.1, y=620),
                     stamp(labels["borderline"], "amber", COL + 10, 450, border_at, size=56),
                     sub("APP · ON SCREEN", ask_en, ask_at, length, color="amber", y=600)],
            glow="amber", name="h4", push=still)
    c.beat("outside", "person", yes_at, yes_end, PERSON["outside"], yes_at + 0.5,
           f"The phone shows the amber card for the garage photo from 30 ft, its talk button highlighted as the person "
           f"answers; beside it a big amber '{feet:.0f} ft' and the subtitle 'Yes, it's outside.'")
    c.beat("h4", "narration", h4.start, h4[0][1], h4.sentences[0], start + border_at + 0.3,
           f"The phone's borderline card highlighted; beside it the amber '{feet:.0f} ft', an amber BORDERLINE stamp "
           "and the person's 'Yes, it's outside.'")
    c.beat("h4-ask", "narration", h4[1][0], h4.end, h4.sentences[1], start + ask_at + 0.6,
           f"On the whole phone screen the highlight glides to the app's question; beside it the amber "
           f"'{feet:.0f} ft', BORDERLINE, and under APP · ON SCREEN, '{ask_en}'")

    # 3. 02 Why it matters.
    c.moods.append((c.t - 1.0, "tension"))
    start = c.t
    w1 = c.narrate("w1", start + 0.3)
    c.sfx("whoosh", start, -9)
    c.sfx("pop", start + 0.35, -9)
    c.scene(w1.at("thirteen hundred") - 0.45 - start,
            [tag(2, anim="rise"), video("night-lights", 72, 170, 1060, 596, push=0.008),
             big("9 in 10", "amber", 1190, 200, 0.3, size=112),
             text("CO deaths came within 3 days", 1190, 400, 660, 0.45, cls="label"),
             source("Iqbal et al. 2012, US disasters 1991–2009", 0.3, video="NASA Black Marble")],
            glow="amber", xfade=0.3, name="w1-days")
    start = c.t
    deaths_at = w1.at("thirteen hundred") - start
    inside_at = w1.at("mostly with the generator") - start
    c.sfx("pop", start + deaths_at, -8)
    c.sfx("pop", start + inside_at, -9)
    c.scene(w1.end + 0.15 - start,
            [tag(2), video("generators", 72, 170, 1060, 596, until=inside_at - 0.4),
             video("generator-panel", 72, 170, 1060, 596, at=inside_at - 0.4),
             {"kind": "count", "html": "{n}", "from": 0, "to": 1332, "dur": 0.9, "cls": "big", "x": 1190, "y": 200,
              "at": round(deaths_at, 3), "anim": "pop",
              "style": "color:var(--red);font-size:120px;width:520px;text-align:center"},
             text("CO deaths involving portable generators, 2004–2021", 1190, 400, 660, deaths_at + 0.15,
                  cls="label"),
             text('Most: inside a house<br>or a garage', 1190, 600, 660, inside_at, cls="body",
                  style="border-left:6px solid var(--amber);padding-left:24px"),
             source("CPSC, 88 FR 24346 (2023)", deaths_at, video="National Guard Bureau / DVIDS")],
            glow="amber", name="w1-deaths")
    c.said(w1, w1.at("thirteen hundred"), "A portable generator in a panel; beside it a red '1,332', 'CO deaths "
                                          "involving portable generators, 2004–2021' and 'Most: inside a house or a "
                                          "garage'; SOURCE CPSC, 88 FR 24346 (2023).")

    start = c.t
    w2 = c.narrate("w2", start + 0.1)
    c.scene(w2.at("which is hard") - 0.1 - start,
            [tag(2), video("cdc", 72, 170, 1060, 596, push=0.004),
             text("more than<br>20 feet", 1190, 220, 660, w2.at("more than twenty") - start, cls="title"),
             text("from any door or window", 1190, 430, 660, w2.at("from any door") - start, cls="label"),
             source("CDC, Carbon Monoxide Poisoning Basics", 0.2, video="CDC")], glow="amber", name="w2-advice")
    start = c.t
    guess = ('<svg width="1500" height="300" viewBox="0 0 1500 300">'
             '<g data-show="0"><rect x="40" y="150" width="190" height="110" rx="14" fill="none" stroke="#93a0b8" '
             'stroke-width="6"/><path d="M70 150v-30h130v30" fill="none" stroke="#93a0b8" stroke-width="6"/></g>'
             '<g data-show="0.1"><path d="M1290 270V120l100-80 100 80v150" fill="none" stroke="#93a0b8" '
             'stroke-width="6"/><rect x="1355" y="170" width="60" height="100" rx="4" fill="none" stroke="#ffb547" '
             'stroke-width="6"/></g>'
             '<path class="d" data-at="0.2" data-dur="0.7" d="M260 205H1260" stroke="#ffb547" stroke-width="6"/></svg>')
    c.sfx("whoosh", start + 0.2, -10)
    c.scene(w2.at("and the warning") - 0.1 - start,
            [tag(2), text("Hard to judge in the dark.", 0, 220, 1920, 0.0, cls="head", style="text-align:center"),
             {"kind": "draw", "x": 210, "y": 420, "at": 0.0, "anim": "none", "svg": guess},
             text("?", 0, 440, 1920, 0.4, cls="hero", style="text-align:center;color:var(--amber)", anim="pop")],
            glow="amber", push=0.002, name="w2-guess")
    start = c.t
    c.sfx("pop", start + 0.1, -8)
    c.scene(w2.at("so the app starts") - 0.1 - start,
            [tag(2), big("59%", "amber", 140, 300, 0.1, size=150),
             text("preferred a language other than English", 820, 300, 960, 0.25, cls="head"),
             text("CO patients at one Houston children's hospital, 2021 Texas freeze", 820, 480, 960, 0.4,
                  cls="label"),
             source("Portillo et al. 2024", 0.1)], glow="amber", name="w2-language")
    c.said(w2, w2.at("doesn't always come"), "A big amber '59%' with 'preferred a language other than English'; "
                                             "SOURCE Portillo et al. 2024.")
    start = c.t
    asked = hero.replied(4)  # the garage take's card, in Hindi
    hindi_card, _, _ = phone(hero, [(asked + 1.0, asked + 1.1, 20)], lambda at: [(0, seen(hero, 4)["head"], "amber")])
    c.scene(w2.end + 0.25 - start, [tag(2), hindi_card, pill("Hindi", "ink", COL, 300, 0.0, anim="rise"),
                                   text("Hindi first", COL, 420, 900, 0.15, cls="title")],
            glow="blue", push=still, name="w2-hindi")
    c.beat("w2-hindi", "narration", w2.at("so the app starts"), w2.end, "so the app starts with Hindi.",
           w2.at("with Hindi") + 0.3, "The whole phone screen with the garage's amber verdict card in Hindi, "
                                      "highlighted; a pill 'Hindi' and 'Hindi first' beside it.")

    # 4. 03 How it measures.
    c.moods.append((c.t - 1.0, "focus"))
    start = c.t
    d1 = c.narrate("d1", start + 0.15)
    gen_at, photo_at = d1.at("stand where") - start, d1.at("one photo") - start
    door_at = d1.at("nearest door") - start
    diagram = ('<svg width="1700" height="560" viewBox="0 0 1700 560">'
               '<path class="d" data-at="0" data-dur="0.6" d="M40 500H1660" stroke="#24324e" stroke-width="6"/>'
               '<path class="d" data-at="0.2" data-dur="0.8" d="M1230 500V250l190-150 190 150v250" stroke="#93a0b8" '
               'stroke-width="7"/>'
               f'<g data-show="{door_at - 0.1:.2f}"><rect x="1360" y="330" width="110" height="170" rx="6" '
               'fill="rgba(255,181,71,.16)" stroke="#ffb547" stroke-width="7"/></g>'
               f'<g data-show="{gen_at:.2f}"><rect x="120" y="380" width="210" height="120" rx="16" fill="#16223a" '
               'stroke="#ff4359" stroke-width="7"/><path d="M150 380v-36h150v36M175 440h100" fill="none" '
               'stroke="#ff4359" stroke-width="7"/></g>'
               f'<g data-show="{photo_at:.2f}"><rect x="372" y="250" width="64" height="116" rx="12" fill="#0b111d" '
               'stroke="#eef2fa" stroke-width="6"/><circle cx="404" cy="282" r="9" fill="#64a8ff"/></g>'
               f'<path class="d" data-at="{door_at - 0.3:.2f}" data-dur="0.35" d="M450 300L1350 400" stroke="#64a8ff" '
               'stroke-width="5"/></svg>')
    c.sfx("whoosh", start + door_at - 0.3, -8)
    c.scene(d1.end + 0.15 - start,
            [tag(3, anim="rise"), {"kind": "draw", "x": 110, "y": 300, "at": 0.0, "anim": "none", "svg": diagram},
             pill("generator", "red", 150, 820, gen_at), pill("one photo", "blue", 330, 200, photo_at),
             pill("nearest door", "amber", 1270, 820, door_at - 0.1)], glow="blue", xfade=0.3, name="d1-diagram")
    c.said(d1, d1.at("one photo"), "A drawn diagram: a red generator, a phone beside it, a blue sight line to a "
                                   "house's amber door; pills 'generator', 'one photo', 'nearest door'.")

    start = c.t
    d2 = c.narrate("d2", start + 0.1)
    doors = json.loads((V2 / "doors" / "doors.json").read_text())
    pictures = door_pictures(doors)
    trace_at, height_at = d2.at("finds the door") - start, d2.at("most doors are") - start
    tall_at = d2.at("its height in the photo") - start
    near_door, far_door = pictures["garage-10ft"], pictures["garage-30ft"]
    span = near_door["span"]
    c.sfx("whoosh", start + trace_at, -8)
    c.sfx("pop", start + height_at, -9)
    c.scene(tall_at - 0.1, [
        tag(3), {"kind": "img", "src": near_door["photo"], "x": 300, "y": 150, "w": 600, "h": 800, "cls": "panel",
                 "anim": "none", "push": 0.01},
        {"kind": "trace", "src": near_door["outline"], "x": 300, "y": 150, "w": 600, "h": 800, "at": trace_at,
         "dur": 0.9, "cx": near_door["cx"], "cy": near_door["cy"], "anim": "none"},
        {"kind": "draw", "x": 300, "y": 150, "at": height_at, "anim": "none",
         "svg": f'<svg width="600" height="800" viewBox="0 0 600 800"><path class="d" data-at="0" data-dur="0.5" '
                f'd="M{span[0]} {span[1]}V{span[2]}" stroke="#ff4359" stroke-width="7"/></svg>'},
        pill("Meta · SAM 3.1", "blue", 1000, 240, 0.0),
        text("finds the door", 1000, 340, 800, trace_at, cls="head"),
        big("6 ft 8 in", "amber", 1000, 520, height_at, size=100),
        text("most doors", 1000, 690, 800, height_at + 0.15, cls="label"),
        text("it asks about yours", 1000, 745, 800, height_at + 0.5, cls="label", style="color:var(--amber)")],
        glow="blue", name="d2-trace")
    c.beat("d2", "narration", d2.start, start + tall_at - 0.1, "Meta's SAM 3.1 finds the door, and since most doors "
           "are about six foot eight,", d2.at("most doors are") + 0.3, "The door photo with SAM 3.1's yellow outline "
           "round the door and a red line down its height; beside it 'Meta · SAM 3.1', 'finds the door', a big amber "
           "'6 ft 8 in', 'most doors' and, in amber, 'it asks about yours'.")
    # Its height in the photo and the phone's lens give the distance (door.py's pinhole model), over the two doors.
    start = c.t
    lens_at, gives_at = d2.at("the phone's lens") - start, d2.at("give the distance") - start
    asks_at = d2[1][0] - start
    c.sfx("pop", start, -9)
    c.sfx("pop", start + lens_at, -9)
    c.sfx("pop", start + gives_at, -9)
    c.scene(asks_at - 0.1, [
        tag(3), text("its height in the photo", 120, 135, 700, 0.0, cls="head", anim="none"),
        text("+ the phone’s lens", 830, 135, 560, lens_at, cls="head", style="color:var(--blue)"),
        text("→ the distance", 1400, 135, 500, gives_at, cls="head"),
        text("distance = focal length (px) × 6 ft 8 in ÷ door height (px)", 0, 228, 1920, gives_at + 0.15,
             cls="label mono", style="text-align:center;font-size:32px"),
        {"kind": "img", "src": near_door["traced"], "x": 525, "y": 320, "w": 390, "h": 520, "cls": "panel",
         "anim": "none"},
        {"kind": "img", "src": far_door["traced"], "x": 1005, "y": 320, "w": 390, "h": 520, "cls": "panel",
         "anim": "none"},
        big("10 ft", "red", 590, 865, 0.0, size=80, anim="none"), big("30 ft", "amber", 1070, 865, 0.0, size=80,
                                                                       anim="none")],
        glow="blue", name="d2-heights")
    c.beat("d2-lens", "narration", start, start + asks_at - 0.1, "its height in the photo and the phone's lens give "
           "the distance.", start + gives_at + 0.3, "Over two traced doors labelled 10 ft (red) and 30 ft (amber): "
           "'its height in the photo + the phone's lens → the distance' and the formula 'distance = focal length (px) "
           "× 6 ft 8 in ÷ door height (px)'.")
    # Garage doors are taller, so it asks: a door and a garage door drawn to scale, and the app's own question.
    start = c.t
    asked_at = d2.at("so the app asks") - start
    garage = door_note("garage-door", "en")
    panels = "".join(f'<path class="d" data-at="{0.45 + 0.06 * i:.2f}" data-dur="0.3" d="M646 {300 - 63 * i}H1210" '
                     'stroke="#ffb547" stroke-width="3" opacity=".7"/>' for i in (1, 2, 3))
    doors_svg = ('<svg width="1320" height="330" viewBox="0 0 1320 330">'
                 '<path class="d" data-at="0" data-dur="0.4" d="M20 300H1300" stroke="#24324e" stroke-width="6"/>'
                 '<path class="d" data-at="0.1" data-dur="0.45" d="M250 300V60h108v240" stroke="#93a0b8" '
                 'stroke-width="6"/>'
                 '<path class="d" data-at="0.25" data-dur="0.55" d="M640 300V48h576v252" stroke="#ffb547" '
                 f'stroke-width="6"/>{panels}'
                 '<g data-show="0.7"><path d="M630 12H1226" stroke="#ffb547" stroke-width="3" '
                 'stroke-dasharray="12 10"/></g></svg>')
    c.sfx("whoosh", start + 0.1, -10)
    c.sfx("pop", start + asked_at, -9)
    c.scene(d2.end + 0.2 - start, [
        tag(3), {"kind": "draw", "x": 300, "y": 170, "at": 0.0, "anim": "none", "svg": doors_svg},
        text("most doors<br>6 ft 8 in", 450, 500, 400, 0.3, cls="label", style="text-align:center"),
        text("garage doors<br>7–8 ft", 1028, 500, 400, 0.6, cls="label",
             style="text-align:center;color:var(--amber)"),
        H(f'<div class="k">THE APP ASKS</div><div class="body" style="margin-top:16px">“{esc(garage)}”</div>', 260, 680,
          1400, cls="card", at=asked_at, style="border-color:var(--amber)")], glow="blue", name="d2-asks")
    c.beat("d2-asks", "narration", start, d2.end, d2.sentences[1], d2.end - 0.2,
           f"A regular door (6 ft 8 in) and a wider, taller garage door (7–8 ft) drawn to scale; under them a card "
           f"THE APP ASKS “{garage}”")

    # m2: the conversation is Meta's models too: on the laptop with no internet, or through Meta's API with a signal.
    start = c.t
    m2 = c.narrate("m2", start + 0.1)
    talk_at, models_at = m2.at("The conversation") - start, m2.at("Meta's models") - start
    offline_at, api_at = m2.at("no internet") - start, m2.at("or through") - start
    spark_at = m2.at("Meta's API") - start
    for t in (talk_at, models_at, offline_at, api_at, spark_at):
        c.sfx("pop", start + t, -10)
    laptop_at = m2.at("on the laptop") - start
    built = {"phone": None, "laptop": talk_at, "sam": talk_at, "mlx": talk_at + 0.2, "reply": talk_at + 0.3,
             "mms": models_at, "glimmer": models_at + 0.25, "laptop-k": laptop_at, "offline": offline_at,
             "api": api_at, "spark": spark_at, "transcribe": spark_at + 0.25}
    c.sfx("whoosh", start + 0.05, -10)
    c.scene(m2.end + 0.35 - start, [tag(3), *architecture(built)], glow="blue", name="m2-arch")
    c.said(m2, start + spark_at + 0.3, "A diagram builds: the PHONE's web page, an arrow to a blue LAPTOP box with "
                                       "'SAM 3.1 · finds the door, then the distance ±6%' on 'Apple MLX', 'Meta MMS · "
                                       "hears and speaks Hindi' and 'Muse Glimmer · reads the facts into a strict "
                                       "schema' and a 'no internet' pill; a REPLY box; below, 'or', a dashed META'S "
                                       "API box 'with a signal': 'Muse Spark 1.3 · reads the facts', 'Muse Voice "
                                       "Transcribe · hears the speech'.")

    # 5. 04 The language problem: a title card, then the second problem, being understood.
    c.moods.append((c.t - 0.6, "tension"))
    start = c.t
    c.sfx("sting", start + 0.05, -7)
    c.scene(1.2, [H('<b style="color:var(--red)">04</b>', 0, 330, 1920, cls="hero mono", anim="pop",
                    style="text-align:center;font-size:120px"),
                  text("THE LANGUAGE PROBLEM", 0, 500, 1920, 0.1, cls="title mono",
                       style="text-align:center;letter-spacing:.12em;font-weight:700")],
            glow="amber", xfade=0.3, push=0.004, name="c4-title")
    c.beat("c4-title", "title", start, c.t, "", start + 0.6, "A chapter card on the navy desk: a red '04' over 'THE "
                                                          "LANGUAGE PROBLEM' in big white mono.")
    start = c.t
    c1 = c.narrate("c1", start + 0.15)
    one_at, two_at = c1.at("the first problem") - start, c1.at("The second") - start
    c.sfx("pop", start + one_at, -9)
    c.sfx("whoosh", start + two_at - 0.1, -10)
    c.sfx("pop", start + two_at, -8)
    c.scene(c1[2][0] - 0.1 - start, [
        tag(4, anim="rise"),
        H('<div class="k">1</div><div class="head" style="margin-top:14px">where to put it '
          '<span style="color:var(--blue)">✓</span></div>', 160, 380, 700, cls="card", at=one_at,
          style="border-color:var(--line)"),
        {"kind": "draw", "x": 880, "y": 430, "at": round(two_at - 0.3, 3), "anim": "none",
         "svg": '<svg width="160" height="80" viewBox="0 0 160 80"><path class="d" data-at="0" data-dur="0.3" '
                'd="M10 40H145M120 18l25 22-25 22" stroke="#93a0b8" stroke-width="7"/></svg>'},
        H('<div class="k" style="color:var(--amber)">2</div><div class="head" style="margin-top:14px">being '
          'understood</div>', 1060, 380, 700, cls="card", at=two_at, style="border-color:var(--amber)")],
        glow="amber", name="c1-two")
    c.beat("c1-two", "narration", c1.start, c1[1][1], " ".join(c1.sentences[:2]), start + two_at + 0.4,
           "Two cards with an arrow between: '1 · where to put it ✓' (a blue tick) and, in amber, '2 · being "
           "understood'; chapter tag 04 THE LANGUAGE PROBLEM.")
    start = c.t
    mms_at, api_wer_at = c1.at("nearly one Hindi word") - start, c1.at("the API about") - start
    short_at = c1.at("short answers") - start
    c.sfx("pop", start + mms_at, -9)
    c.sfx("pop", start + api_wer_at, -9)
    c.sfx("pop", start + short_at, -10)
    c.scene(max(c1.end + 0.6, start + short_at + 3.0) - start, [
        tag(4), text("Hindi words heard wrong", 0, 170, 1920, 0.0, cls="head", style="text-align:center"),
        big("18.2%", "amber", 330, 310, mms_at, size=120), text("MMS, on the laptop", 330, 500, 560, mms_at + 0.15,
                                                                cls="label"),
        big("10.5%", "blue", 1100, 310, api_wer_at, size=120),
        text("Muse Voice Transcribe, Meta's API", 1100, 500, 640, api_wer_at + 0.15, cls="label"),
        H('<span class="pill" style="color:var(--amber);background:var(--amber-soft);font-size:44px">short answers: '
          'the hardest</span>', 0, 680, 1920, at=short_at, anim="pop", style="text-align:center"),
        source("Google FLEURS, 50 read sentences (CC BY 4.0); short answers: this repo's evals", 0.3)],
        glow="amber", name="c1-heard")
    c.beat("c1-heard", "narration", c1[2][0], c1.end, c1.sentences[2], start + short_at + 0.4,
           "'Hindi words heard wrong': a big amber '18.2%' for MMS on the laptop and a big blue '10.5%' for Muse Voice "
           "Transcribe on Meta's API, and an amber pill 'short answers: the hardest'; SOURCE Google FLEURS and this "
           "repo's evals.")

    # c1a: what the person said and what the speech model wrote, one card each, the stand-in's «हाँ» in the pause
    # the line leaves for it; each card stays at least 3.5 s after its last part comes in.
    READ = 3.5
    start = c.t
    c1a = c.narrate("c1a", start + 0.5)
    quiet = slot(c1a, "in Hindi,", "and the speech model")
    said_haan = clip_seconds(VOICES / "haan.wav")
    haan_at = quiet[0] + (quiet[1] - quiet[0] - said_haan) / 2
    # The word alone: the music and room tone drop out under it, with 80 ms fades (the user's ear check, Nov 4: this
    # take, a little clearer), and no sound effect lands on it.
    haan_end = c.voice(haan_at, VOICES / "haan.wav", "person", boost_db=HAAN_BOOST_DB)
    c.dips.append((haan_at + 0.01, haan_end - 0.03))
    model_at, fhcc_at = c1a.at("the speech model") - start, c1a.at("F H C C") - start
    word_at = fhcc_at + 0.45
    c.sfx("stamp", start + fhcc_at, -6)
    lead = Said("c1b", 0.0).at("a warning could")  # the risk card comes in on these words
    c1b = Said("c1b", max(c1a.end + 0.5, start + word_at + 0.27 + READ + 0.1 - lead))  # the cut is 0.1 s early
    risk_at = c1b.at("a warning could")
    c.scene(risk_at - 0.1 - start, [
        tag(4),
        H(f'<div class="k" style="font-size:30px">WHAT THE PERSON SAID</div><div class="hero" style="{hindi};'
          'font-size:150px;margin-top:18px;'
          'line-height:1.15">«हाँ»</div><div class="head" style="margin-top:14px">“yes”, in Hindi</div>'
          '<div class="mono" style="margin-top:22px;font-size:28px;letter-spacing:.1em;color:var(--muted)">PERSON · '
          'HINDI</div>', 120, 250, 760, h=470, cls="card", at=haan_at - start, anim="pop",
          style="border-color:var(--line)"),
        {"kind": "draw", "x": 890, "y": 470, "at": round(model_at - 0.3, 3), "anim": "none",
         "svg": '<svg width="140" height="80" viewBox="0 0 140 80"><path class="d" data-at="0" data-dur="0.3" '
                'd="M10 40H125M100 18l25 22-25 22" stroke="#93a0b8" stroke-width="7"/></svg>'},
        H('<div class="k" style="font-size:30px">WHAT THE SPEECH MODEL WROTE</div>', 1040, 250, 760, h=470, cls="card",
          at=model_at,
          style="border-color:var(--amber)"),
        H("fhcc", 1040, 360, 760, cls="hero mono", at=fhcc_at, anim="slam",
          style="color:var(--amber);font-size:150px;text-align:center"),
        H("not a word", 1040, 560, 760, cls="head", at=word_at, style="text-align:center")],
        glow="amber", xfade=0.3, name="c1-said")
    c.said(c1a, start + fhcc_at, "Two big cards: WHAT THE PERSON SAID «हाँ» “yes”, in Hindi (PERSON · HINDI), an "
                                 "arrow, and WHAT THE SPEECH MODEL WROTE, an amber 'fhcc', 'not a word'.")
    c.beat("haan", "person", haan_at, haan_end, "«हाँ» (yes)", haan_at + 0.4,
           "The card WHAT THE PERSON SAID: «हाँ», “yes”, in Hindi, PERSON · HINDI, as the stand-in says it.")
    # c1b: the risk, held until the rule.
    c.narrate("c1b", c1b.start)
    lead = Said("c1c", 0.0).at("one rule")
    c1c = Said("c1c", max(c1b.end + 0.6, risk_at + 0.27 + READ + 0.1 - lead))
    rule_at = c1c.at("one rule")
    start = c.t
    c.sfx("stamp", risk_at, -6)
    c.scene(rule_at - 0.1 - start, [
        tag(4),
        H('<div class="k" style="color:var(--red)">THE RISK</div><div class="title" style="margin-top:26px">a garbled '
          'answer must never<br>count as yes</div>', 160, 330, 1600, cls="card", at=risk_at - start,
          style="border-color:var(--red);padding:44px 56px")],
        glow="red", name="c1-risk")
    c.beat("c1b", "narration", c1b.start, c1b.end, c1b.text, risk_at + 0.4,
           "A big card: THE RISK, 'a garbled answer must never count as yes'.")
    # c1c: the rule, beside the phone; then the app keeping it: a mumbled answer, and it asks again.
    start = c.t
    c.narrate("c1c", c1c.start)
    unsure_at, add_at = c1c.at("If it isn't sure") - start, c1c.at("can add a warning") - start
    clear_at, again_at = c1c.at("never clear one") - start, c1c.at("asks again") - start
    mumble, unclear = hero_old.at("voice", 1, line="mumble"), hero_old.replied(4)
    said_mumble = clip_seconds(VOICES / "mumble.wav")
    mumble_at = c1c.end + 0.35 - start
    b_len = 0.1 + said_mumble + 0.25
    reply_at = mumble_at + b_len + 0.05
    end = max(reply_at + 2.6, again_at + 0.27 + READ)
    segments = [(mumble - 1.2, mumble - 0.9, mumble_at - 0.3 - 0.1), (mumble - 0.2, mumble - 0.2 + b_len + 0.1),
                (unclear - 0.1, unclear + 0.9, end - reply_at - 0.9)]
    # The take is the first cut's, in the hallway: its card (30.2 ft, the hallway photo) and the turn under it are
    # blurred throughout, so they never contradict the garage, and only the app's "Sorry" reads.
    # The page changes on the first frame recorded after the reply, so the smaller blur starts exactly there.
    before, after = seen(hero_old, 3)["reply"], seen(hero_old, 4)["reply"]
    item, at, length = phone(hero_old, segments,
                             lambda at: [(mumble_at - 0.1, tapped(hero_old, "#talk", 1)["talk"], "blue")])
    new_page = first_shown(hero_old, item, unclear)
    item["marks"].append([new_page, after["y"], after["h"], "amber"])
    item["blurs"] = [[0, 0, before["y"] + before["h"] + 10], [new_page, 0, after["y"] - 14]]
    c.voice(start + mumble_at, VOICES / "mumble.wav", "person")
    for t in (unsure_at, add_at, clear_at, again_at):
        c.sfx("pop", start + t, -10)
    c.sfx("stamp", start + reply_at + 0.4, -6)
    row = "font:700 54px/1.2 Inter;margin-top:18px"
    c.scene(length, [
        item, tag(4),
        H('<div class="k">THE RULE</div>', COL, 150, COLW, h=520, cls="card", at=0.0, anim="none",
          style="border-color:var(--amber)"),
        H("unsure →", COL + 44, 240, 900, at=unsure_at, style=f"{row};color:var(--amber)"),
        H("can add a warning", COL + 44, 320, 900, at=add_at, style=row),
        H("never clears one", COL + 44, 400, 900, at=clear_at, style=row),
        H("asks again", COL + 44, 480, 900, at=again_at, style=row),
        H("", COL + 28, 478, 420, h=80, at=reply_at + 0.4, anim="fade",
          style="border:4px solid var(--amber);border-radius:16px;background:var(--amber-soft)"),
        sub("PERSON · HINDI", "Hmm…", mumble_at - 0.15, reply_at, y=720),
        sub("APP · ON SCREEN", english["mumble"][0], reply_at + 0.2, length, color="amber", y=720)],
        glow="amber", name="c1-rule", push=still)
    c.beat("c1c", "narration", c1c.start, c1c.end, c1c.text, start + again_at + 0.4,
           "Beside the whole phone screen (the old take's card blurred), a card THE RULE: 'unsure → can add a "
           "warning · never clears one · asks again', each line in as it's said.")
    c.beat("mumble", "person", start + mumble_at, start + mumble_at + said_mumble, "Hmm…", start + mumble_at + 0.3,
           "The phone listens, its talk button highlighted; THE RULE card beside it, and the subtitle 'Hmm…'.")
    c.beat("asks-again", "app", start + reply_at, c.t, english["mumble"][0], start + reply_at + 0.7,
           f"The phone's 'Sorry' reply highlighted in amber, the card above it blurred; THE RULE card's 'asks again' "
           f"boxed in amber, and under APP · ON SCREEN: '{english['mumble'][0]}'")
    # c1d: how that has held.
    start = c.t
    c1d = c.narrate("c1d", start + 0.4)
    zero_at = c1d.at("a hundred and twenty") - start
    c.sfx("stamp", start + zero_at, -5)
    c.scene(max(c1d.end + 0.5 - start, zero_at + 0.15 + 0.27 + READ), [
        tag(4),
        H('0 <span style="color:var(--muted);font-weight:500">/</span> 120', 0, 250, 1920, cls="hero mono",
          at=zero_at, anim="slam", style="text-align:center;font-size:200px;color:var(--blue)"),
        text("unclear answers cleared a warning", 0, 500, 1920, zero_at + 0.15, cls="title", style="text-align:center"),
        source("this repo's evals: README, Reading: Spark and Glimmer (Oct 29)", 0.3)], glow="blue", name="c1-zero")
    c.said(c1d, start + zero_at + 0.6, "A huge blue '0 / 120' over 'unclear answers cleared a warning' in big type; "
                                       "SOURCE this repo's evals.")

    # c2: symptom words get the emergency line from the rules, in a tenth of a second, before the language model.
    start = c.t
    talk, back = symptom.at("voice"), symptom.replied(2)
    answered = symptom.replied(2) - symptom.at("sent")
    assert answered < 0.15, f"the symptom reply took {answered:.2f} s: the screen says 0.1 s"
    said_head = clip_seconds(VOICES / "headache.wav")
    fresh = coach(symptom, 2, [0], upto=",")[0][0]
    e = Said("c2", start + 0.2)
    b_start = e.end - start + 0.15
    b_len = 0.1 + 0.3 + said_head + 0.25
    reply_at = b_start + b_len + 0.1
    fresh_at = start + reply_at + 0.3
    end = fresh_at + clip_seconds(fresh) + 0.35
    segments = [(talk - 0.9, talk - 0.6, b_start - 0.3), (talk + 0.1, talk + 0.1 + b_len),
                (back - 0.1, back + 0.6, end - start - reply_at - 0.6)]
    item, at, length = phone(symptom, segments,
                             lambda at: [(b_start + 0.2, tapped(symptom, "#talk")["talk"], "blue"),
                                         (reply_at + 0.1, seen(symptom, 2)["reply"], "red")])
    c2 = c.narrate("c2", e.start)
    head_at = start + b_start + 0.3
    head_end = c.voice(head_at, VOICES / "headache.wav", "person")
    fresh_end = c.voice(fresh_at, fresh, "app")
    c.sfx("stamp", start + reply_at + 0.05, -5)
    c.sfx("pop", start + reply_at + 0.35, -9)
    fresh_en = part(english["headache"][0], " and call") + "…"
    c.scene(length, [item, tag(4),
                     pill("headache", "red", COL, 240, c2.at("headache") - start, until=reply_at, size=44),
                     pill("dizzy", "red", COL + 400, 240, c2.at("dizzy") - start, until=reply_at, size=44),
                     sub("PERSON · HINDI", PERSON["headache"], head_at - start - 0.15, reply_at),
                     stamp("fresh air · call 911", "red", COL + 10, 240, reply_at + 0.05, size=52),
                     H(f'<span class="big" style="color:var(--ink);font-size:72px">{answered:.1f} s</span>'
                       '<span class="label" style="margin-left:22px">· no language model</span>', COL + 10, 390, COLW,
                       at=reply_at + 0.35, anim="pop"),
                     sub("APP · HINDI", fresh_en, fresh_at - start - 0.1, length, color="red", y=560)],
            glow="red", name="c2-symptom", push=still)
    c.said(c2, c2.at("feeling dizzy"), "The whole phone screen before the person speaks; beside it red pills "
                                       "'headache' and 'dizzy'; chapter tag 04 THE LANGUAGE PROBLEM.")
    c.beat("headache", "person", head_at, head_end, PERSON["headache"], head_at + 0.5,
           "The phone listens, its talk button highlighted; beside it the red pills 'headache' and 'dizzy' and the "
           "subtitle 'I have a headache.'")
    c.beat("fresh-air", "app", fresh_at, fresh_end, fresh_en, fresh_at + 0.3,
           f"The phone's red emergency reply with its 911 button, highlighted; beside it a red FRESH AIR · CALL 911 "
           f"stamp, '{answered:.1f} s · no language model', and the English of the app's Hindi.")

    # m3: the model never gives the safety advice; the rulebook does, in code, in the CDC's own words.
    start = c.t
    m3 = c.narrate("m3", start + 0.15)
    never_at, advice_at = m3.at("never gives") - start, m3.at("the safety advice") - start
    built = dict.fromkeys(("phone", "laptop", "laptop-k", "sam", "mlx", "mms", "glimmer", "offline", "api", "spark",
                           "transcribe", "reply"))
    built.update(never=never_at, rules=advice_at)
    c.sfx("whoosh", start + 0.05, -10)
    c.sfx("pop", start + never_at, -9)
    c.sfx("stamp", start + advice_at, -7)
    c.scene(m3[1][0] - 0.1 - start, [tag(4), *architecture(built)], glow="blue", name="m3-never")
    c.beat("m3-never", "narration", m3.start, m3[0][1], m3.sentences[0], start + advice_at + 0.3,
           "The whole diagram again: red 'doesn't decide' pills on Muse Glimmer and Muse Spark, and the RULEBOOK box "
           "lighting up: 'rules.py · decides every warning · cites CDC · CPSC · NIST · Ready.gov', arrows on to the "
           "REPLY.")
    start = c.t
    cdc_at = m3.at("the CDC's guidance") - start
    code = ('<span class="nu"># src/aftermath/rules.py</span>\n'
            'TOO_CLOSE_FT, BORDERLINE_FT = <span class="nu">17.0</span>, <span class="nu">23.0</span>\n\n'
            '<span class="kw">if</span> feet &lt; TOO_CLOSE_FT:\n'
            '    <span class="kw">return</span> <span class="st">"too close"</span>\n'
            '<span class="kw">if</span> feet &lt;= BORDERLINE_FT <span class="kw">or</span> reads_far:\n'
            '    <span class="kw">return</span> <span class="st">"borderline"</span>\n'
            '<span class="kw">return</span> <span class="st">"meets the guidance"</span>')
    quote = esc(SOURCES["cdc-distance"].quote).replace("more than 20 feet", '<span class="hl">more than 20 feet</span>')
    c.sfx("pop", start, -9)
    c.sfx("pop", start + cdc_at, -9)
    c.sfx("stamp", start + cdc_at + 0.5, -5)
    c.scene(max(m3.end + 0.6 - start, cdc_at + 0.5 + 0.27 + 2.6), [
        tag(4),
        H(f'<div class="k">THE RULEBOOK, IN CODE</div><div class="code" style="margin-top:20px;font-size:28px">{code}'
          '</div>', 72, 190, 860, cls="card", anim="none", style="border-color:var(--ink);padding:30px 34px"),
        H(f'<div class="k">THE CDC\'S OWN WORDS, IN THE APP</div><div class="body" style="margin-top:18px;'
          f'font-weight:600;font-size:40px">“{quote}”</div><div class="label" style="margin-top:20px;font-size:32px">'
          'CDC · Carbon Monoxide Poisoning Basics</div>', 980, 190, 868, cls="card", at=cdc_at,
          style="border-color:var(--blue);padding:30px 34px"),
        stamp("not from the model", "red", 980, 800, cdc_at + 0.5, size=50),
        source("CDC, quoted in src/aftermath/guidance.py", 0.3)], glow="blue", name="m3-rules")
    c.beat("m3-rules", "narration", start, m3.end, m3.sentences[1], start + cdc_at + 0.8,
           "Two cards: THE RULEBOOK, IN CODE (rules.py's 17 and 23 ft thresholds and its bands) and THE CDC'S OWN "
           "WORDS, IN THE APP, the CDC's sentence with 'more than 20 feet' highlighted, a red NOT FROM THE MODEL stamp "
           "under it; SOURCE CDC, quoted in src/aftermath/guidance.py.")

    # 6. 05 Proof.
    c.moods.append((c.t - 0.6, "focus"))
    start = c.t
    p1 = c.narrate("p1", start + 0.15)
    tape_at, scans_at, within_at = (p1.at("tape measure") - start, p1.at("public laser scans") - start,
                                    p1.at("within about three") - start)
    rows = [("10 ft", "10.0", "+0.2%"), ("10 ft", "10.0", "+0.3%"), ("15 ft", "15.1", "+0.5%"),
            ("20 ft", "20.4", "+1.9%"), ("25 ft", "25.8", "+3.1%"), ("30 ft", "30.2", "+0.6%")]
    table = "".join(f'<div style="display:flex;gap:40px;margin-top:10px"><span style="width:150px">{a}</span>'
                    f'<span style="width:130px;color:var(--ink)">{b}</span><span style="color:var(--amber)">{e}</span>'
                    '</div>' for a, b, e in rows)
    c.sfx("pop", start + tape_at, -9)
    c.sfx("pop", start + scans_at, -9)
    c.sfx("stamp", start + within_at, -6)
    c.scene(p1.end + 0.2 - start, [
        tag(5, anim="rise"),
        H(f'<div class="k">TAPE MEASURE · ONE DOOR</div><div class="code" style="margin-top:16px;color:var(--muted);'
          f'white-space:normal">{table}</div>', 72, 170, 760, cls="card", at=tape_at),
        H('<div class="k">LASER SCANS · DIODE</div><div class="head" style="margin-top:16px">7 doors</div>'
          '<div class="label" style="margin-top:10px">true height known:<br>median −0.2%, worst −2.0%</div>',
          890, 170, 560, cls="card", at=scans_at),
        H('<div class="label">within about</div><div class="big" style="margin-top:8px;color:var(--amber);'
          'display:inline-block">3%</div>', 1500, 170, 360, at=within_at, anim="slam", rot=-4),
        source("this repo's evals: README, How the distance is measured", 0.3)], glow="blue", xfade=0.3,
        name="p1-tape")
    c.said(p1, p1.at("within about three"), "A tape-measure table (10–30 ft, errors +0.2% to +3.1%), a DIODE scans "
                                            "card, and a big amber '3%' landing beside them.")

    start = c.t
    p2 = c.narrate("p2", start + 0.1)
    zero_at = p2.at("it never called") - start
    hidden_at = p2.at("One partly hidden") - start if "One partly hidden" in p2.text else None
    held_at = p2.at("now held back") - start if "now held back" in p2.text else None
    c.sfx("stamp", start + zero_at, -4)
    c.sfx("pop", start + zero_at + 0.35, -10)
    if held_at is not None:
        c.sfx("pop", start + held_at, -9)
    c.scene(p2.end + 0.25 - start, [
        tag(5),
        H('0 <span style="color:var(--muted);font-weight:500">of</span> 31', 0, 200, 1920, cls="hero mono",
          at=zero_at, anim="slam", style="text-align:center;font-size:190px;color:var(--blue)"),
        text("door views under 20 ft rated far enough", 0, 440, 1920, zero_at + 0.15, cls="head",
             style="text-align:center"),
        pill("11 laser scans", "ink", 560, 590, zero_at + 0.35),
        pill("20 renders", "ink", 1040, 590, zero_at + 0.5),
        text("one partly hidden door slipped through early on", 0, 730, 1920, hidden_at, cls="label",
             style="text-align:center") if hidden_at is not None else None,
        pill("now held back", "amber", 810, 810, held_at) if held_at is not None else None,
        source("DIODE (11) and Hypersim (20), this repo's evals", 0.3)], glow="blue", name="p2-zero")
    c.said(p2, start + (held_at if held_at is not None else zero_at + 0.6),
           "A huge blue '0 of 31' with 'door views under 20 ft rated far enough' and pills '11 laser scans' and '20 "
           "renders'" + (", 'one partly hidden door slipped through early on' and an amber pill 'now held back'."
                         if held_at is not None else "."))

    c.moods.append((c.t - 1.0, "resolve"))
    start = c.t
    p3 = c.narrate("p3", start + 0.2)
    code_at = p3[1][0] - start
    tests_at = p3.at("eight hundred and forty tests") - start
    tests = tests_collected()
    if tests != NARRATED_TESTS:
        print(f"WARNING: {tests} tests are collected, and the narration says {NARRATED_TESTS}", file=sys.stderr)
    c.sfx("impact", start + code_at, -8)
    c.sfx("pop", start + tests_at, -9)
    c.scene(p3.end + 0.5 - start, [
        text("It doesn't replace a<br>carbon monoxide alarm.", 0, 200, 1920, p3[0][0] - start, cls="title",
             style="text-align:center"),
        H(mark.replace('width="150" height="150"', 'width="70" height="70"'), 760, 505, at=code_at),
        text("Aftermath", 850, 507, 500, code_at, cls="head"),
        text("github.com/vkend/aftermath", 0, 625, 1920, code_at + 0.15, cls="head mono",
             style="text-align:center;color:var(--blue);font-size:52px"),
        H(f'<span class="big" style="color:var(--ink);font-size:72px">{tests} tests</span>', 0, 750, 1920,
          at=tests_at, anim="pop", style="text-align:center")],
        glow="blue", xfade=0.3, name="p3-end")
    c.said(p3, p3.at("eight hundred and forty tests") + 0.3, "On the navy desk: 'It doesn't replace a carbon monoxide "
           f"alarm.', then the Aftermath mark, github.com/vkend/aftermath in blue and a big '{tests} tests'.")

    start = c.t
    credits = "".join(f'<div style="display:flex;gap:28px;margin-top:20px"><span class="mono" style="flex:0 0 330px;'
                      f'color:var(--muted);font-size:32px;letter-spacing:.06em">{esc(k.upper())}</span>'
                      f'<span style="font-size:32px;line-height:1.3">{esc(v)}</span></div>' for k, v in CREDITS)
    c.scene(2.5, [H(credits, 110, 120, 1700, anim="fade", ease=0.2)], glow="blue", push=0.0, name="credits")
    total = round(c.t, 3)
    c.beat("credits", "title", start, total, "", start + 1.0, "Credits on the navy desk: narration, staging, models, "
           "footage, figures, music and type.")

    inside_frame(c.scenes)
    for beat in c.beats:
        beat["key"] = round(hero_time(c.scenes, beat), 2)
    timeline = {"total": total, "fadeOut": 0.8, "fadeIn": 0.0, "scenes": c.scenes, "fonts": fonts()}
    return {"timeline": timeline, "cut": c}


def arrived(item: dict) -> float:
    """How long after its start an item has fully come in."""
    if item["kind"] in ("count", "trace"):
        return item.get("delay", 0) + item.get("dur", 0.9)
    if item["kind"] == "draw":
        ends = [float(x) + float(d) for x, d in re.findall(r'data-at="([\d.]+)" data-dur="([\d.]+)"', item["svg"])]
        ends += [float(x) + 0.27 for x in re.findall(r'data-show="([\d.]+)"', item["svg"])]
        return max(ends, default=0.0)
    if item.get("anim") == "slam":
        return 0.16
    if item.get("anim") == "none":
        return 0.0
    return item.get("ease", 0.27)


def hero_time(scenes: list[dict], beat: dict) -> float:
    """A beat's hero frame: in the scene it was keyed to, 0.3 s after the last of its reveals has landed (counting
    only what came in before the beat ended and is still there), so nothing is half faded in."""
    scene = next(sc for sc in scenes if sc["start"] <= beat["key"] < sc["end"])
    done = beat["key"] - 0.3
    for item in scene["items"]:
        at = scene["start"] + item.get("at", 0)
        gone = scene["start"] + item["until"] if "until" in item else None
        if at > beat["end"] or (gone is not None and gone <= beat["key"]):
            continue
        done = max(done, at + arrived(item))
    return min(scene["end"] - 0.1, done + 0.3)


def garage() -> None:
    """The garage photos the hero sends to the app, and their outlines. data/video/garage/clean holds the builder's
    photos at taped distances, the house number painted out and their metadata stripped (the 30 ft one cropped to 3:4,
    leaving out the house next door); each gets back only its lens's 35 mm-equivalent focal length, so the app measures
    it as it would the phone's (24 mm on the full frame, about 33 mm on the crop). Then the app's own measurement of
    each, for the outline the film traces. Record the take next: make_video.py record --only garage."""
    from PIL import Image

    from aftermath.cache import ResponseCache
    from aftermath.door import measure
    from aftermath.segment import LocalSam31

    full = (4284 ** 2 + 5712 ** 2) ** 0.5  # the iPhone frame's diagonal, in pixels
    doors_file = V2 / "doors" / "doors.json"
    doors = json.loads(doors_file.read_text())
    for name, source in (("garage-10ft", "10ft-photo"), ("garage-30ft", "30ft-photo")):
        image = Image.open(VIDEO / "garage" / "clean" / f"{source}.jpg")
        exif = Image.Exif()
        exif.get_ifd(0x8769)[0xA405] = round(24 * full / (image.width ** 2 + image.height ** 2) ** 0.5)
        photo = VIDEO / "work" / f"{name}.jpg"
        image.save(photo, quality=95, exif=exif)
        reading = measure(photo, LocalSam31(ResponseCache(ROOT / "data" / "cache")))
        Image.fromarray(reading.mask.astype(np.uint8) * 255).save(V2 / "doors" / f"{name}-mask.png")
        doors[name] = {"feet": reading.feet, "lowest": reading.lowest_ft, "span": reading.values["span"],
                       "shape": list(reading.mask.shape), "warnings": reading.warnings}
        print(f"{name}: {reading.feet:.1f} ft (near end {reading.lowest_ft:.1f}), {reading.warnings}")
    doors_file.write_text(json.dumps(doors, indent=1))


def haan() -> None:
    """The stand-in's «हाँ» for c1a, which the narration leaves a pause for (Siri can't say it): the person's voice, as
    make_video.py's audition makes it (MMS-TTS, pitched 0.85, half a second of silence first), and the first take
    Whisper, asked for a yes or a no, hears as «हाँ». A lone syllable is hard to hear: the app's MMS heard none of
    twelve takes as «हाँ» (which is c1's story), and Whisper unprompted none of forty. MMS-TTS doesn't say it the same
    way twice, so a take once made is kept."""
    import torch
    from mlx_audio.stt.utils import load_model

    from aftermath.speech import Voice, write_wav

    folder = VIDEO / "work" / "audition"
    voice, ears = Voice(), load_model(narrate.WHISPER)
    for k in range(40):
        said = ("हां", "हाँ")[k % 2]
        raw, take = folder / f"haan-try{k}-raw.wav", folder / f"haan-try{k}-0.85.wav"
        if not take.exists():
            torch.manual_seed(k)
            write_wav(raw, voice.speak(said, "hi"), voice.rate("hi"))
            sh(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"asetrate={16000 * 0.85:.0f},aresample=48000,"
                f"atempo={1 / 0.85:.4f},adelay=500:all=1,apad=pad_dur=0.3", "-ac", "1", str(take)])
        sh(["ffmpeg", "-v", "error", "-y", "-i", str(take), "-ar", "16000", "-ac", "1", str(folder / "heard.wav")])
        heard = ears.generate(str(folder / "heard.wav"), language="hi", initial_prompt="हाँ या नहीं?").text.strip(" ।?")
        a, b = audible(load(take))
        print(f"{take.name} ({said}): heard «{heard}», {b - a:.2f} s")
        if heard in ("हाँ", "हां") and b - a >= 0.3:
            shutil.copy(take, VIDEO / "work" / "voices" / "haan.wav")
            return
    sys.exit("no take of «हाँ» was heard as meant")


def haan_cut() -> None:
    """The swap for c1a's «हाँ», if the lone take doesn't sound like one: the first word of the stand-in's «हाँ, बाहर है»
    (the take make_video.py's audition kept, which the app heard as meant), cut where the voice dips before «बाहर»,
    with half a second of silence first as the other lines have. data/video/work/voices/haan-cut.wav; copy it over
    haan.wav to use it."""
    x = load(VOICES / "outside.wav")
    win = SR // 200  # 5 ms
    n = len(x) // win
    power = 10 * np.log10((x[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    onset = int(np.flatnonzero(power > power.max() - 35)[0])
    dip = onset + 20 + int(np.argmin(power[onset + 20: onset + 60]))  # 0.1-0.3 s in: the end of «हाँ»
    word = x[max(0, onset - 4) * win: dip * win].copy()
    word[: SR // 100] *= np.linspace(0, 1, SR // 100)
    word[-int(0.015 * SR):] *= np.linspace(1, 0, int(0.015 * SR))
    pad = np.zeros(SR // 2, np.float32)
    write_wav(VOICES / "haan-cut.wav", np.concatenate([pad, word, pad]))
    print(f"haan-cut.wav: «हाँ» from outside.wav, {onset * win / SR:.2f}-{dip * win / SR:.2f} s ({len(word) / SR:.2f} s)")


def door_pictures(doors: dict) -> dict:
    """The two door photos at 600×800, plain and with SAM's outline, and the outline alone for the trace."""
    from PIL import Image

    folder = V2 / "doors"
    out = {}
    for name, info in doors.items():
        photo = Image.open(VIDEO / "work" / f"{name}.jpg").convert("RGB").resize((600, 800), Image.Resampling.LANCZOS)
        mask = np.array(Image.open(folder / f"{name}-mask.png").resize((600, 800), Image.Resampling.NEAREST)) > 127
        inner = np.pad(mask, 1)
        edge = mask & ~(inner[2:, 1:-1] & inner[:-2, 1:-1] & inner[1:-1, 2:] & inner[1:-1, :-2])

        def thick(e: np.ndarray, r: int) -> np.ndarray:
            out_ = e.copy()
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dx * dx + dy * dy <= r * r:
                        out_ |= np.roll(np.roll(e, dy, 0), dx, 1)
            return out_

        line, dark = thick(edge, 3), thick(edge, 6)
        rgba = np.zeros((800, 600, 4), np.uint8)
        rgba[dark] = (0, 0, 0, 150)
        rgba[line] = (255, 210, 0, 255)
        Image.fromarray(rgba, "RGBA").save(folder / f"{name}-outline.png")
        photo.save(folder / f"{name}-600.jpg", quality=90)
        traced = Image.alpha_composite(photo.convert("RGBA"), Image.fromarray(rgba, "RGBA")).convert("RGB")
        traced.save(folder / f"{name}-traced.jpg", quality=90)
        ys, xs = np.nonzero(mask)
        scale = 600 / info["shape"][1]
        span = [round(v * scale) for v in info["span"]] if info.get("span") else None
        out[name] = {"photo": url(folder / f"{name}-600.jpg"), "outline": url(folder / f"{name}-outline.png"),
                     "traced": url(folder / f"{name}-traced.jpg"), "cx": round(xs.mean() / 6, 1),
                     "cy": round(ys.mean() / 8, 1), "span": span}
    return out


def fonts() -> list[dict]:
    folder = VIDEO / "fonts"
    faces = [("Inter", "inter-latin-wght-normal.woff2", {"weight": "100 900"}),
             ("JetBrains Mono", "jetbrains-mono-latin-400-normal.woff2", {"weight": "400"}),
             ("JetBrains Mono", "jetbrains-mono-latin-500-normal.woff2", {"weight": "500"}),
             ("JetBrains Mono", "jetbrains-mono-latin-700-normal.woff2", {"weight": "700"}),
             ("Noto Sans Devanagari", "NotoSansDevanagari.ttf", {"weight": "100 900"})]
    kind = {"woff2": "font/woff2", "ttf": "font/ttf"}
    return [{"family": family, "url": f"data:{kind[file.rsplit('.', 1)[1]]};base64," + base64.b64encode((folder / file).read_bytes())
             .decode(), "descriptors": d} for family, file, d in faces]


# The b-roll, as frames: (clip, start, seconds, filter before the grade). Graded cool, toward the navy desk.
BROLL_CUTS = {
    "ian-drone": ("01_ian_pine-island_uscg-drone_4k.mp4", 13.0, 3.0, "scale=1920:1080"),
    "ian-boat": ("02_ian_fort-myers-beach_uscg-msst.mp4", 31.0, 3.0, "scale=1920:1080"),
    "fort-myers": ("02_ian_fort-myers-beach_uscg-msst.mp4", 54.0, 3.0, "scale=1920:1080"),
    "generators": ("10_sandy_portable-generators_ny-national-guard.mp4", 85.0, 5.0, "scale=1280:720"),
    "generator-panel": ("10_sandy_portable-generators_ny-national-guard.mp4", 0.3, 5.0, "scale=1280:720"),
    "night-lights": ("07_ian_florida-night-lights-before-after_nasa-black-marble_4k.webm", 2.0, 8.0,
                     "crop=1920:1080:1280:540,scale=1280:720"),
    "cdc": ("11_cdc_prevent-co-poisoning_20ft-animation.webm", 42.0, 3.6,
            "scale=-2:720,pad=1280:720:(ow-iw)/2:0:color=white"),
    "lineman": ("08_dorian_power-line-repair_usmc.mp4", 74.0, 5.0, "scale=1280:720"),
    # The user's garage door, closed and only starting to lift: it ends at 4.4 s, before the gap under it shows the
    # floor inside (nothing inside the garage is shown).
    "garage-door": (VIDEO / "garage" / "clean" / "garage-door.mp4", 3.2, 1.2, "scale=540:960"),
}
GRADE = "eq=saturation=0.8:contrast=1.03:brightness=-0.03,colorbalance=rs=-0.03:bs=0.05:rm=-0.02:bm=0.03"


def extract_broll() -> None:
    for key, (clip, start, seconds, vf) in BROLL_CUTS.items():
        folder = V2 / "broll" / key
        stamp_file = folder / "made.json"
        made = json.dumps([str(clip), start, seconds, vf, GRADE])
        if stamp_file.exists() and stamp_file.read_text() == made:
            continue
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        grade = "" if key == "cdc" else f",{GRADE}"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(seconds), "-i", str(BROLL / clip),
                        "-vf", f"fps={FPS},{vf}{grade}", "-q:v", "3", str(folder / "%04d.jpg")], check=True)
        stamp_file.write_text(made)


# --- the sound ---------------------------------------------------------------------------------------------------------

def sh(command: list[str]) -> None:
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        sys.exit(f"{' '.join(command[:3])}… failed:\n{done.stderr[-3000:]}")


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1] if x.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def read_wav(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def mixdown(c: Cut, total: float) -> dict:
    AUDIO.mkdir(parents=True, exist_ok=True)
    n = int(round(total * SR))
    buses = {"voice": np.zeros(n, np.float32), "sfx": np.zeros(n, np.float32)}
    for s in c.sounds:
        x = load(Path(s["file"]))
        a = int(s["start"] * SR)
        b = len(x) if s["end"] is None else int(s["end"] * SR)
        piece = x[a:b] * s["gain"]
        if s["kind"] != "sfx":  # 8 ms edges, so a cut clip never clicks
            ramp = min(len(piece) // 2, int(0.008 * SR))
            piece[:ramp] *= np.linspace(0, 1, ramp)
            piece[len(piece) - ramp:] *= np.linspace(1, 0, ramp)
        at = int(round(s["at"] * SR))
        piece = piece[: max(0, n - at)]
        buses["sfx" if s["kind"] == "sfx" else "voice"][at: at + len(piece)] += piece
    write_wav(AUDIO / "voice.wav", buses["voice"])
    # The score: the studio's generator, its moods changing a second before each chapter's first line.
    changes = sorted(c.moods)
    segments = [{"start": round(max(0.0, a), 3), "end": round(b, 3), "mood": m, "ambience": "room"}
                for (a, m), (b, _) in zip(changes, changes[1:] + [(total, "")])]
    segments[0]["start"] = 0.0
    speech = sorted((round(a, 3), round(b, 3)) for a, b in c.speech)
    plan = {"total": total, "sampleRate": SR, "moods": MOODS, "segments": segments,
            "speech": [{"start": a, "end": b} for a, b in speech],
            "levels": {"musicGapDb": -17, "musicDuckDb": -13, "ambienceDuckDb": -4}}
    (AUDIO / "plan.json").write_text(json.dumps(plan, indent=1))
    sh(["python3", str(STUDIO / "audio" / "music.py"), "score", "--plan", str(AUDIO / "plan.json"), "--out",
        str(AUDIO), "--seed", "7"])
    music, room = read_wav(AUDIO / "music.wav")[:n], read_wav(AUDIO / "ambience.wav")[:n]
    bed, fade = np.ones(n, np.float32), int(0.08 * SR)
    for a, b in c.dips:  # silent under the word, with 80 ms fades either side
        i, j = int(a * SR), int(b * SR)
        bed[i:j] = 0.0
        bed[i - fade:i] = np.minimum(bed[i - fade:i], np.linspace(1, 0, fade, dtype=np.float32))
        bed[j:j + fade] = np.minimum(bed[j:j + fade], np.linspace(0, 1, fade, dtype=np.float32))
    music *= bed[: len(music), None]
    room *= bed[: len(room), None]
    voice = np.repeat(buses["voice"][:, None], 2, axis=1)
    sfx = np.repeat(buses["sfx"][:, None], 2, axis=1)
    mix = voice + sfx
    mix[: len(music)] += music
    mix[: len(room)] += room
    write_wav(AUDIO / "premix.wav", mix / max(1.0, np.abs(mix).max() / 0.98))
    # Two passes of loudnorm: -14 LUFS, true peak under -2 dBTP here, so under -1.5 once it's AAC.
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(AUDIO / "premix.wav"), "-af",
                            "loudnorm=I=-14:TP=-2:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    m = json.loads(first[first.rindex("{"): first.rindex("}") + 1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(AUDIO / "premix.wav"), "-af",
                    f"loudnorm=I=-14:TP=-2:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                    f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
                    "linear=true,aresample=48000", "-ar", str(SR), str(AUDIO / "mix.wav")], check=True)
    # How far the music sits under the voice while someone speaks.
    under = []
    for a, b in speech:
        i, j = int(a * SR), int(b * SR)
        v = np.sqrt(np.mean(buses["voice"][i:j] ** 2) + 1e-12)
        mu = np.sqrt(np.mean(music[i:j] ** 2) + 1e-12)
        under.append(20 * np.log10(v / mu))
    return {"music_under_voice_db": {"min": round(float(min(under)), 1), "median": round(float(np.median(under)), 1),
                                     "under_8_db": [list(w) for w, u in zip(speech, under) if u < 8]},
            "plan_segments": segments}


def build_all() -> None:
    if not (AUDIO / "sfx" / "pop.wav").exists():
        sh(["python3", str(STUDIO / "audio" / "music.py"), "sfx", "--out", str(AUDIO / "sfx"), "--seed", "7"])
    extract_broll()
    made = build()
    timeline, c = made["timeline"], made["cut"]
    V2.mkdir(parents=True, exist_ok=True)
    (V2 / "timeline.json").write_text(json.dumps(timeline))
    sound = mixdown(c, timeline["total"])
    OUT.mkdir(parents=True, exist_ok=True)
    timing = {"total": timeline["total"], "beats": c.beats,
              "scenes": [{"name": s["name"], "start": s["start"], "end": s["end"]} for s in timeline["scenes"]],
              "sound": sound}
    (OUT / "timing.json").write_text(json.dumps(timing, indent=1, ensure_ascii=False))
    captions(c)
    print(f"timeline {timeline['total']:.1f} s, {len(timeline['scenes'])} scenes; music under voice: "
          f"{sound['music_under_voice_db']}")


def captions(c: Cut) -> None:
    """captions.srt for the narration: at most two lines of 42 characters, each cue from its first word to its last,
    as Whisper heard them."""
    import textwrap

    cues = []
    for said in [x for x in c.sounds if x["kind"] == "narration"]:
        info, k = LINES[Path(said["file"]).stem], 0
        for sentence in info["sentences"]:
            n = len(sentence.split())
            chunk: list = []
            for word in info["words"][k:k + n] + [None]:
                if word is None or (chunk and len(" ".join(w for w, _, _ in chunk)) + len(word[0]) + 1 > 84):
                    cues.append((said["at"] + chunk[0][1], said["at"] + chunk[-1][2],
                                 "\n".join(textwrap.wrap(" ".join(w for w, _, _ in chunk), 42))))
                    chunk = []
                if word is not None:
                    chunk.append(word)
            k += n
    cues.sort()

    def stamp_(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    (OUT / "captions.srt").write_text("".join(f"{i}\n{stamp_(a)} --> {stamp_(b)}\n{t}\n\n"
                                              for i, (a, b, t) in enumerate(cues, 1)))


def node_env() -> dict:
    return {"NODE_PATH": str(VIDEO / "node" / "node_modules"), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"}


def stills(times: str) -> None:
    folder = OUT / "stills"
    subprocess.run(["node", str(Path(__file__).with_name("render2.js")), str(V2 / "timeline.json"), str(folder), "1",
                    times], check=True, env=node_env())
    print(folder)


def render(workers: int, reuse: bool = False) -> None:
    if not reuse:  # with reuse, only the sound changed: the frames drawn last time are encoded again
        shutil.rmtree(FRAMES, ignore_errors=True)
        subprocess.run(["node", str(Path(__file__).with_name("render2.js")), str(V2 / "timeline.json"), str(FRAMES),
                        str(workers)], check=True, env=node_env())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(FRAMES / "%05d.jpg"), "-i",
                    str(AUDIO / "mix.wav"), "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-vf", "scale=out_range=tv:out_color_matrix=bt709,setparams=range=tv:"
                    "color_primaries=bt709:color_trc=bt709:colorspace=bt709", "-color_range", "tv",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac",
                    "-b:a", "320k", "-ar", str(SR), "-shortest", "-movflags", "+faststart", str(FILM)], check=True)
    report()


def report() -> None:
    """What to judge the cut by: the thumbnail, a frame every 2 s, cuts a minute, and a listen check of the first 90 s."""
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(FRAMES / "00000.jpg"), "-vf", "scale=1280:720",
                    str(OUT / "thumbnail.png")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(FILM), "-vf", "fps=1/2,scale=320:-2,tile=6x15",
                    "-frames:v", "1", "-q:v", "3", str(OUT / "strip.jpg")], check=True)
    spec = importlib.util.spec_from_file_location("analyze", STUDIO.parent / "scripts" / "analyze.py")
    analyze = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyze)
    scores = OUT / "scenes_all.txt"
    changes = OUT / "scenes_1fps.txt"
    for f in (scores, changes):
        f.unlink(missing_ok=True)
    duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(FILM)], capture_output=True, text=True).stdout)
    pace = analyze.pacing(analyze.scene_scores(str(FILM), str(scores), "scale=192:-2", 0.015),
                          analyze.scene_scores(str(FILM), str(changes), "fps=1,scale=96:-2", 0.15), duration)
    first = AUDIO / "first-90s.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(FILM), "-t", "90", "-vn", str(first)], check=True)
    timing = json.loads((OUT / "timing.json").read_text())
    timing["pacing"] = pace
    timing["listen"] = listen(first, timing)
    (OUT / "timing.json").write_text(json.dumps(timing, indent=1, ensure_ascii=False))
    print(json.dumps({"duration": duration, "pacing": pace, "listen": timing["listen"]}, indent=1))


def listen(first: Path, timing: dict) -> dict:
    """The first 90 s: each voice's level in the mix, clicks, dead air, and the sting against its cut."""
    x = read_wav(first).mean(axis=1)
    levels = {}
    for beat in timing["beats"]:
        if beat["start"] >= 90 or beat["kind"] == "title":
            continue
        seg = x[int(beat["start"] * SR): int(min(90, beat["end"]) * SR)]
        if len(seg) > SR // 4:
            levels[beat["id"]] = round(active_rms_db(seg), 1)
    d = np.abs(np.diff(x))
    local = np.convolve(np.abs(x), np.ones(480) / 480, mode="same")[1:]
    clicks = int(np.sum((d > 0.25) & (d > 12 * local)))
    voiced = sorted((b["start"], b["end"]) for b in timing["beats"] if b["kind"] in ("narration", "app", "person"))
    gaps, last = [], 0.9
    for a, b in voiced:
        if a < 90 and a - last > 2.0:
            gaps.append([round(last, 2), round(a, 2)])
        last = max(last, b)
    title = next(s["start"] for s in timing["scenes"] if s["name"] == "c4-title")
    return {"voice_levels_db": levels, "clicks": clicks, "silences_over_2s": gaps,
            "sting_hits_at": round(title + 0.05, 2), "chapter_04_card_at": round(title, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser("garage", help="the garage photos for the hero take, and their outlines")
    h = steps.add_parser("haan", help="the stand-in's «हाँ» for c1a")
    h.add_argument("--cut", action="store_true", help="the swap: «हाँ» cut from the stand-in's «हाँ, बाहर है»")
    steps.add_parser("build")
    s = steps.add_parser("stills")
    s.add_argument("times", help="seconds, comma-separated")
    r = steps.add_parser("render")
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--reuse", action="store_true", help="encode the frames drawn last time, with the new sound")
    steps.add_parser("report")
    args = parser.parse_args()
    if args.step == "garage":
        garage()
    elif args.step == "haan":
        haan_cut() if args.cut else haan()
    elif args.step == "build":
        build_all()
    elif args.step == "stills":
        stills(args.times)
    elif args.step == "render":
        render(args.workers, args.reuse)
    else:
        report()


if __name__ == "__main__":
    main()
