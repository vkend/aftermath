"""The first cut, with no narration: recordings, cards and b-roll into data/video/aftermath-poc-v1.mp4 (see
make_video.py; edit2.py makes the narrated v2).

Each shot is rendered on its own (1920×1080, 30 fps, AAC), then all are joined. In the app's shots the phone shows the
recording, cut where the app was working (the captions give the time it took the first time), and holds on a reply
while the coach speaks. The coach's audio is the app's own voice (speech.Voice, MMS-TTS) saying the sentences of the
recorded reply that carry the verdict, each spoken on its own so the cut falls cleanly: the voice leaves silences
inside sentences as well as between them, so the reply's audio can't be cut at its sentences. The stand-in's voice
plays when the fake microphone played it. The English subtitles are the app's own English for the same turns, so they
say what the Hindi says.
"""

import json
import re
import subprocess
import wave
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from cards import SCALE, SCREEN, WINDOW, caption, render, render_cards

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "data" / "video"
TAKES, CARDS, EDIT, BROLL = VIDEO / "takes", VIDEO / "cards", VIDEO / "edit", VIDEO / "broll"
VOICES = VIDEO / "work" / "voices"
FPS = 30
STAGED = "Staged · a synthetic voice stands in for a person · no generator running"
HEARD = ""  # how often the stand-in's yes was heard, from the audition (set in cut)

# What the stand-in says, in English.
PERSON = {"garage": "The power's out. I've started the generator in the garage.", "outside": "Yes, it's outside.",
          "still-outside": "Yes, it's outside.", "mumble": "Hmm…", "headache": "I have a headache.",
          "nobody": "No, nobody.", "alarm": "Yes, it's working.", "en-outside": "Yes, it's outside.",
          "es-garage": "The generator is in the garage."}


class Take:
    """One scene as record.js saved it: events and frames, with times in seconds from the scene's start."""

    def __init__(self, name: str) -> None:
        self.folder = TAKES / name
        self.events = json.loads((self.folder / "events.json").read_text())
        self.t0 = self.events[0]["t"]
        self.frames = [(f["t"] - self.t0, self.folder / "frames" / f["file"])
                       for f in json.loads((self.folder / "frames.json").read_text())]
        self.replies = [e for e in self.events if e["kind"] == "reply"]

    def at(self, kind: str, n: int = 1, **match) -> float:
        hits = [e for e in self.events if e["kind"] == kind and all(e.get(k) == v for k, v in match.items())]
        return hits[n - 1]["t"] - self.t0

    def reply(self, n: int) -> dict:
        return self.replies[n - 1]

    def replied(self, n: int) -> float:
        return self.replies[n - 1]["t"] - self.t0

    def audio(self, n: int) -> Path:
        return self.folder / self.replies[n - 1]["audio"]


def split(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!।])\s+", text.strip()) if s]


@dataclass
class Sound:
    at: float  # seconds into the shot
    file: Path
    start: float = 0.0
    end: float | None = None
    volume: float = 1.0


@dataclass
class Caption:
    png: Path
    start: float
    end: float


@dataclass
class Shot:
    name: str
    seconds: float
    video: list[str]  # ffmpeg inputs for the picture
    picture: str  # the filter that makes [v] from input 0 (and the frame, input 1, for the phone)
    sounds: list[Sound] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    fade: tuple[float, float] = (0.0, 0.0)  # seconds of fade from and to black: only at the film's two ends


def phone_video(take: Take, segments: list[tuple], out: Path) -> float:
    """The screen over these stretches of the take, (start, end) or (start, end, hold): one after another, each
    holding its last picture for ``hold`` seconds (while the coach speaks), at 30 fps. Its length."""
    times = [t for t, _ in take.frames]
    pieces = []
    for a, b, *hold in segments:
        i, t = max(0, bisect_right(times, a) - 1), a
        while t < b - 1e-6:
            end = min(times[i + 1] if i + 1 < len(times) else b, b)
            pieces.append((take.frames[i][1], end - t))
            t = end
            if end < b:
                i += 1
        if hold:
            pieces.append((take.frames[max(0, bisect_right(times, b) - 1)][1], hold[0]))
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{path}'\nduration {seconds:.4f}\n" for path, seconds in pieces)
                       + f"file '{pieces[-1][0]}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-vf", f"fps={FPS},scale=out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "14",
                    str(out)], check=True)
    return sum(b - a + (hold[0] if hold else 0) for a, b, *hold in segments)


class Timeline:
    """Maps a take's times to a shot's, across the stretches kept (a hold counts after its stretch)."""

    def __init__(self, segments: list[tuple]) -> None:
        self.segments = segments

    def __call__(self, t: float) -> float:
        done = 0.0
        for a, b, *hold in self.segments:
            if t < b:
                return done + max(0.0, t - a)
            done += b - a + (hold[0] if hold else 0)
        return done


def render_shot(shot: Shot, out: Path) -> Path:
    inputs = list(shot.video)
    pictures = inputs.count("-i")
    for c in shot.captions:
        inputs += ["-loop", "1", "-t", f"{shot.seconds:.3f}", "-i", str(c.png)]
    for s in shot.sounds:
        inputs += ["-i", str(s.file)]
    graph = [shot.picture]
    last = "v"
    # One panel at a time: a caption ends where the next begins.
    starts = sorted(c.start for c in shot.captions)
    for k, c in enumerate(shot.captions):
        end = min([c.end] + [t for t in starts if c.start < t < c.end])
        graph.append(f"[{last}][{pictures + k}:v]overlay=0:0:enable='between(t,{c.start:.3f},{end:.3f})'[c{k}]")
        last = f"c{k}"
    fades = "".join([f"fade=t=in:st=0:d={shot.fade[0]}," if shot.fade[0] else "",
                     f"fade=t=out:st={shot.seconds - shot.fade[1]:.3f}:d={shot.fade[1]}," if shot.fade[1] else ""])
    # Every shot the same: standard-range 4:2:0 (the phone's JPEG frames are full range), so the parts join as
    # they are.
    graph.append(f"[{last}]{fades}scale=out_range=tv,format=yuv420p[vout]")
    mixes = []
    for k, s in enumerate(shot.sounds):
        index = pictures + len(shot.captions) + k
        trim = f"atrim=start={s.start:.3f}" + (f":end={s.end:.3f}" if s.end is not None else "")
        graph.append(f"[{index}:a]{trim},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
                     f"volume={s.volume},adelay={round(s.at * 1000)}:all=1[a{k}]")
        mixes.append(f"[a{k}]")
    if mixes:
        graph.append(f"{''.join(mixes)}amix=inputs={len(mixes)}:normalize=0:duration=longest,apad,"
                     f"atrim=0:{shot.seconds:.3f}[aout]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{shot.seconds:.3f}[aout]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(graph), "-map", "[vout]",
                    "-map", "[aout]", "-t", f"{shot.seconds:.3f}", "-r", str(FPS), "-color_range", "tv",
                    "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)], check=True)
    return out


def still(name: str, png: Path, seconds: float, sounds: list[Sound] = ()) -> Shot:
    return Shot(name, seconds, ["-loop", "1", "-t", f"{seconds:.3f}", "-i", str(png)],
                f"[0:v]scale={1920}:{1080},fps={FPS}[v]", list(sounds))


def broll(name: str, clip: str, start: float, seconds: float, overlay: Path | None = None,
          crop: str = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080") -> Shot:
    shot = Shot(name, seconds, ["-ss", f"{start}", "-t", f"{seconds}", "-i", str(BROLL / clip)],
                f"[0:v]{crop},fps={FPS},setsar=1[v]")
    if overlay:
        shot.captions.append(Caption(overlay, 0.4, seconds))
    return shot


def frames(name: str, folder: Path, seconds: float) -> Shot:
    return Shot(name, seconds, ["-framerate", str(FPS), "-i", str(folder / "%03d.png")],
                f"[0:v]fps={FPS},tpad=stop_mode=clone:stop_duration=5,trim=0:{seconds}[v]")


class Captions:
    """Captions to render in one go: each is a PNG the size of the frame, with the panel beside the phone."""

    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add(self, kicker: str, who: str = "", english: str = "", note: str = "", verdict: tuple = ()) -> Path:
        name = f"cap-{len(self.jobs):03d}"
        self.jobs.append({"name": name, "page": caption(kicker, who, english, note, verdict), "transparent": True})
        return CARDS / "captions" / f"{name}.png"

    def render(self) -> None:
        render(self.jobs, CARDS / "captions")


# Where the phone's view of the recording starts (its top, in the recording's pixels) to show a part of the page,
# from where record.js found the parts once a reply was shown or a button tapped: the verdict card from its top;
# the reply, or the Talk button and the line under it, with as much of the card above as fits; the photo buttons.
def card_view(where: dict) -> int:
    return where["verdict"]["y"] - 20


def reply_view(where: dict) -> int:
    return max(card_view(where), where["reply"]["y"] + where["reply"]["h"] + 30 - WINDOW)


def talk_view(where: dict) -> int:
    return max(card_view(where), where["talk"]["y"] + where["talk"]["h"] + 90 - WINDOW)


def turn_view(where: dict) -> int:
    """The reply near the top, what was heard above its answer: the turn itself, not the card above it."""
    return where["reply"]["y"] - 200


def buttons_view(where: dict) -> int:
    return max(card_view(where), where["talk"]["y"] + where["talk"]["h"] + 280 - WINDOW)


def view_top(views: list[tuple[float, int, str]], move: float = 0.9) -> str:
    """An ffmpeg expression for the view's top over the shot: each (time, top, how) holds until the next; "cut"
    jumps there at its time, "pan" eases there over ``move`` seconds from its time."""
    views = [(t, max(0, min(1704 - WINDOW, round(top))), how) for t, top, how in views]
    pieces, current = [], views[0][1]  # (until, expression)
    for t, top, how in views[1:]:
        pieces.append((t, f"{current}"))
        if how == "pan" and top != current:
            u = f"(t-{t:.3f})/{move}"
            pieces.append((t + move, f"{current}+({top - current})*(3*pow({u},2)-2*pow({u},3))"))
        current = top
    expression = f"{current}"
    for until, piece in reversed(pieces):
        expression = f"if(lt(t,{until:.3f}),{piece},{expression})"
    return expression


def app_shot(name: str, take: Take, segments: list[tuple], views=None) -> tuple[Shot, Timeline]:
    """The phone over these stretches of the take, the view following ``views(at)``: (shot time, top, how), see
    view_top. The phone's screen is wide and runs off the bottom of the picture, so the view shows part of the page."""
    phone = phone_video(take, segments, EDIT / f"{name}-phone.mp4")
    at = Timeline(segments)
    x, y, w, h = SCREEN
    top = view_top(views(at)) if views else "0"
    shot = Shot(name, phone, ["-i", str(EDIT / f"{name}-phone.mp4"), "-i", str(CARDS / "frame.png")],
                f"color=c=0x0f1419:s=1920x1080:r={FPS}:d={phone:.3f}[bg];"
                f"[0:v]crop=786:{WINDOW}:0:'{top}',scale={w}:{round(WINDOW * SCALE)}[ph];"
                f"[bg][ph]overlay={x}:{y}:shortest=1[p];[p][1:v]overlay=0:0[v]")
    return shot, at


VOICE = []  # the app's voice, loaded once


def part(text: str, upto: str | None) -> str:
    """A sentence, or only its part before ``upto`` (the clause that carries the verdict)."""
    return text.split(upto)[0].strip() if upto and upto in text else text


def coach(take: Take, n: int, picks: list[int], upto: str | None = None) -> list[tuple[Path, float, float]]:
    """The chosen sentences (0-based) of reply n, each spoken by the app's voice on its own: (file, start, end)."""
    import hashlib

    import torch

    from aftermath.speech import Voice, write_wav

    language = take.reply(n)["language"] or "hi"
    out = []
    for i in picks:
        text = part(split(take.reply(n)["text"])[i], upto)
        file = EDIT / "voice" / f"{hashlib.sha256(f'{language} {text}'.encode()).hexdigest()[:16]}.wav"
        if not file.exists():
            if not VOICE:
                VOICE.append(Voice())
            torch.manual_seed(0)  # the same take every time
            file.parent.mkdir(parents=True, exist_ok=True)
            write_wav(file, VOICE[0].speak(text, language), VOICE[0].rate(language))
        with wave.open(str(file)) as w:
            out.append((file, 0.0, w.getnframes() / w.getframerate() + 0.15))
    return out


def spoken(take: Take, n: int, picks: list[int], upto: str | None = None, limit: float | None = None) -> float:
    """How long the chosen sentences of reply n last (at most ``limit`` seconds)."""
    length = sum(b - a for _, a, b in coach(take, n, picks, upto))
    return min(length, limit) if limit else length


def mirror() -> dict[str, str]:
    """The same turns in English, from the app's own words: the subtitles for its Hindi."""
    from aftermath.conversation import Conversation

    class NoModel:
        def ask_json(self, *args, **kw):
            raise RuntimeError("the subtitles' turns are all quick ones")

    out = {}
    c = Conversation(NoModel(), language="en")
    c.opening()
    out["garage"] = c.reply("The power is out and the generator is in the garage.").text
    c = Conversation(NoModel(), language="en")
    c.opening()
    out["near"] = c.reply("", door=(9.6, 9.1), lens_assumed=True).text
    out["far"] = c.reply("", door=(30.2, 28.5)).text
    out["mumble"] = c.reply("hmm").text
    out["outside"] = c.reply("Yes, it's outside.").text
    night = c.check_in()
    out["checkin"] = night.opening()
    out["checkin-outside"] = night.reply("No, nobody.").text
    out["checkin-alarm"] = night.reply("Yes, it's outside.").text
    out["checkin-done"] = night.reply("Yes, I have one.").text
    c = Conversation(NoModel(), language="en")
    c.opening()
    out["lens"] = c.reply("", door=(28.9, 27.3), lens_assumed=True).text
    out["lens-tap"] = c.tap("confirm-1x", True).text
    c = Conversation(NoModel(), language="en")
    c.opening()
    out["headache"] = c.reply("My head hurts.").text
    return out


def cut(video: Path = VIDEO) -> Path:
    from aftermath.guidance import SOURCES

    global HEARD
    EDIT.mkdir(parents=True, exist_ok=True)
    english = {key: split(text) for key, text in mirror().items()}
    tried = json.loads((VIDEO / "work" / "audition" / "results.json").read_text())
    takes = [r for k, r in tried.items() if r["line"] == "outside" and k.endswith("-0.85.wav")]
    HEARD = (f"MMS heard {sum(r['as meant'] for r in takes)} of {len(takes)} synthetic takes of this line as a "
             "plain yes, and took none of the others as one.")
    caps = Captions()
    shots: list[Shot] = []

    def person(shot: Shot, at, take: Take, line: str, kicker: str, n: int = 1, note: str = "",
               verdict: tuple = ()) -> float:
        """The stand-in's line where the fake microphone played it; its caption until the reply. Its length."""
        start = at(take.at("voice", n, line=line) + 0.3)
        seconds = next(e["seconds"] for e in take.events if e.get("line") == line and e["kind"] == "voice")
        shot.sounds.append(Sound(start, VOICES / f"{line}.wav"))
        shot.captions.append(Caption(caps.add(kicker, "Person (synthetic voice)", PERSON[line], note, verdict),
                                     start - 0.2, start + seconds + 0.5))
        return start + seconds

    def says(shot: Shot, at_time: float, take: Take, n: int, picks: list[int], kicker: str, key: str,
             note: str = "", upto: str | None = None, limit: float | None = None, quiet: float | None = None,
             verdict: tuple = (), english_text: str | None = None, shown: float | None = None) -> float:
        """Reply n's chosen sentences from at_time, with their English beside the phone and the verdict it shows;
        when they end. ``upto`` keeps each sentence's part before it, ``limit`` stops the audio there, with ``quiet``
        (seconds) the line is shown and not spoken, and ``shown`` is when the panel appears (at_time - 0.1)."""
        t = at_time
        text = [part(line, upto) for line in split(take.reply(n)["text"])]
        if quiet:
            t += quiet
        else:
            for file, a, b in coach(take, n, picks, upto):
                end = b if not limit else min(b, a + limit - (t - at_time))
                shot.sounds.append(Sound(t, file, a, end))
                t += end - a
        lines_en = english_text or (" ".join(part(english[key][i], upto) for i in picks) if key
                                    else " ".join(text[i] for i in picks))
        if limit:
            lines_en += "…"
        begin = at_time - 0.1 if shown is None else shown
        shot.captions.append(Caption(caps.add(kicker, "Coach", lines_en, note, verdict), begin, t + 0.4))
        return t

    from aftermath.phrases import PAGE

    labels = PAGE["en"]["placement"]

    def verdict(take: Take, n: int) -> tuple:
        """The verdict reply n left on the phone, for the panel: its English label, the distance, and its tone."""
        r = take.reply(n)
        door = r.get("door")
        return labels[r["placement"]], f"{door['feet']:g} ft · {door['metres']:g} m" if door else "", r["level"]

    def fill(shot: Shot, kicker: str, doing: str = "") -> Shot:
        """One panel all through the shot: the kicker, and what the person is doing, until the first caption; each
        caption held until the next, and the last until the end."""
        shot.captions.sort(key=lambda c: c.start)
        if shot.captions and shot.captions[0].start > 0.05:
            intro = caps.add(kicker, "Person" if doing else "", doing)
            shot.captions.insert(0, Caption(intro, 0, shot.captions[0].start))
        for c, after in zip(shot.captions, shot.captions[1:]):
            c.end = max(c.end, after.start)
        if shot.captions:
            shot.captions[-1].end = shot.seconds
        return shot

    def seen(take: Take, n: int) -> dict:
        """Where the page's parts were once reply n was shown."""
        return next(e["where"] for e in take.events if e["kind"] == "shown" and e["reply"] == n)

    def tapped(take: Take, selector: str, k: int = 1) -> dict:
        """Where they were at the k-th tap on ``selector``."""
        return [e["where"] for e in take.events if e["kind"] == "tap" and e["selector"] == selector][k - 1]

    # 1. Cold open: the garage, and the danger at once.
    take = Take("cold-open")
    kicker = STAGED
    talk, sent, back = take.at("voice"), take.at("sent"), take.replied(2)
    length = spoken(take, 2, [0], upto=":")
    shot, at = app_shot("01-cold-open", take, [(talk - 0.5, sent + 0.2), (back - 0.1, back + 0.5, length + 0.3)],
                        lambda at: [(0, talk_view(tapped(take, "#talk")), "cut"),
                                    (at(back - 0.1), reply_view(seen(take, 3)), "cut")])
    shot.fade = (0.4, 0.0)
    person(shot, at, take, "garage", STAGED)
    says(shot, at(back) + 0.5, take, 2, [0], STAGED, "garage", upto=":", shown=at(back) + 0.4,
         note="Reply in 0.1 s: a danger needs no model.", verdict=verdict(take, 2))
    shots.append(fill(shot, kicker))

    # 2. Title, and the problem: b-roll (muted) under the numbers.
    shots.append(still("02-title", CARDS / "title.png", 4))
    shots.append(broll("03-deaths", "01_ian_pine-island_uscg-drone_4k.mp4", 13, 4.0, CARDS / "n-deaths.png"))
    shots.append(broll("04-days", "07_ian_florida-night-lights-before-after_nasa-black-marble_4k.webm", 2.5, 4.0,
                       CARDS / "n-days.png", crop="crop=1280:1080:1280:540,scale=1280:1080,pad=1920:1080:640:0"))
    shots.append(broll("05-language", "01_ian_pine-island_uscg-drone_4k.mp4", 41, 4.4, CARDS / "n-language.png"))
    shots.append(broll("06-cdc", "11_cdc_prevent-co-poisoning_20ft-animation.webm", 42.0, 3.6,
                       crop="scale=-2:1080,pad=1920:1080:(1920-iw)/2:0:color=white"))
    shots.append(still("07-rule", CARDS / "rule.png", 4.2))
    shots.append(still("08-nist", CARDS / "nist.png", 4))
    shots.append(frames("09-diagram", CARDS / "diagram", 5))

    # 3. The hero: too close, then 30 ft (only if outside), an unclear answer asked again, then a plain yes.
    take = Take("hero")
    kicker = "Test photos of a hallway on a tape, Oct 29 · no generator running"
    photo1, photo2 = take.at("photo", 1), take.at("photo", 2)
    near, far = take.replied(2), take.replied(3)
    length = spoken(take, 2, [1])
    shot, at = app_shot("10-near", take, [(photo1 - 0.7, photo1 + 0.4), (near - 0.1, near + 1.6, length)],
                        lambda at: [(0, buttons_view(tapped(take, "#door-label", 1)), "cut"),
                                    (at(near - 0.1), card_view(seen(take, 2)), "cut"),
                                    (at(near + 1.6) + 0.5 * length, reply_view(seen(take, 2)), "pan")])
    says(shot, at(near) + 0.9, take, 2, [1], kicker, "near", shown=at(near) + 0.4, verdict=verdict(take, 2),
         note="From 10 ft. The door was found in 0.9 s; the spoken reply was ready in 3.5 s.")
    shots.append(fill(shot, kicker, "Takes a photo of the door from 10 ft."))
    take = Take("lens")
    kicker = "The other route: a photo with no lens data"
    photo, asked, answered = take.at("photo"), take.replied(2), take.replied(3)
    tap = take.at("tap", 1, selector="#tap-yes")
    shot, at = app_shot("10b-lens", take, [(photo - 0.4, photo + 0.3), (asked - 0.1, asked + 0.6, 1.6),
                                           (tap - 0.3, tap + 0.4), (answered - 0.1, answered + 1.8)],
                        lambda at: [(0, buttons_view(tapped(take, "#door-label")), "cut"),
                                    (at(asked - 0.1), card_view(seen(take, 2)), "cut"),
                                    (at(answered - 0.1), card_view(seen(take, 3)), "cut")])
    says(shot, at(asked) + 0.2, take, 2, [2], kicker, "lens", quiet=at(answered) - at(asked) - 0.3,
         shown=at(asked) + 0.4,
         note="Take Photo leaves the lens out, so the coach asks first. One tap answers.", verdict=verdict(take, 2))
    says(shot, at(answered) + 0.4, take, 3, [0], kicker, "", quiet=1.4, verdict=verdict(take, 3),
         english_text=english["lens-tap"][-1], note="At 1×: now only “is it outside?”")
    shots.append(fill(shot, kicker, "Takes a photo with the camera inside Safari."))
    take = Take("hero")
    kicker = "Test photos of a hallway on a tape, Oct 29 · no generator running"
    length = spoken(take, 3, [1])
    shot, at = app_shot("11-far", take, [(photo2 - 0.7, photo2 + 0.4), (far - 0.1, far + 1.6, length)],
                        lambda at: [(0, buttons_view(tapped(take, "#door-label", 2)), "cut"),
                                    (at(far - 0.1), card_view(seen(take, 3)), "cut"),
                                    (at(far + 1.6) + 0.5 * length, reply_view(seen(take, 3)), "pan")])
    says(shot, at(far) + 0.9, take, 3, [1], kicker, "far", shown=at(far) + 0.4, verdict=verdict(take, 3),
         note="30 ft on the tape: it reads 30.2 ft, at least 28.5 ft.")
    shots.append(fill(shot, kicker, "Takes a photo of the door from 30 ft."))
    kicker = "An unclear answer never clears a warning"
    mumble, unclear = take.at("voice", 1, line="mumble"), take.replied(4)
    length = spoken(take, 4, [0, 2])
    shot, at = app_shot("12-unclear", take, [(mumble - 0.6, take.at("sent", 1, line="mumble") + 0.3),
                                             (unclear - 0.1, unclear + 1.0, length)],
                        lambda at: [(0, talk_view(tapped(take, "#talk", 1)), "cut"),
                                    (at(unclear - 0.1), turn_view(seen(take, 4)), "cut")])
    person(shot, at, take, "mumble", kicker, verdict=verdict(take, 3))
    says(shot, at(unclear) + 0.4, take, 4, [0, 2], kicker, "mumble", verdict=("Unclear → asks again", "", "warning"),
         note=f"Heard «{take.reply(4).get('heard') or '…'}». The warning stays until a plain answer.")
    shots.append(fill(shot, kicker))
    kicker = "A plain answer"
    yes, answer = take.at("voice", 1, line="outside"), take.replied(5)
    length = spoken(take, 5, [1])
    shot, at = app_shot("13-outside", take, [(yes - 0.6, take.at("sent", 1, line="outside") + 0.3),
                                             (answer - 0.1, answer + 1.6, length + 0.3)],
                        lambda at: [(0, talk_view(tapped(take, "#talk", 3)), "cut"),
                                    (at(answer - 0.1), card_view(seen(take, 5)), "cut"),
                                    (at(answer + 1.6) + 0.55 * length, reply_view(seen(take, 5)), "pan")])
    person(shot, at, take, "outside", kicker, verdict=verdict(take, 4))
    says(shot, at(answer) + 0.9, take, 5, [1], kicker, "outside", shown=at(answer) + 0.4, verdict=verdict(take, 5),
         note="Judged on the low end of the range. It never says “safe”.")
    shots.append(fill(shot, kicker))

    # 4. Symptoms.
    take = Take("symptom")
    kicker = "Symptoms come first"
    talk, back = take.at("voice"), take.replied(2)
    length = spoken(take, 2, [0])
    shot, at = app_shot("15-symptom", take, [(talk - 0.4, take.at("sent") + 0.2),
                                             (back - 0.1, back + 0.6, length + 0.2)],
                        lambda at: [(0, talk_view(tapped(take, "#talk")), "cut"),
                                    (at(back - 0.1), seen(take, 2)["reply"]["y"] - 20, "cut")])
    person(shot, at, take, "headache", kicker)
    says(shot, at(back) + 0.4, take, 2, [0], kicker, "headache", verdict=("Fresh air now · call 911", "", "emergency"),
         note="Symptom words skip the model: 911 at once.")
    shots.append(fill(shot, kicker))

    # 5. The overnight check-in (its first question and answer), and the family's summary.
    take = Take("hero")
    kicker = "Overnight: a reminder brings the person back for three questions"
    begun, nobody = take.replied(6), take.at("voice", 1, line="nobody")
    keep = [(take.at("tap", 1, selector="#check-now") - 0.2, begun + 0.6, spoken(take, 6, [1]) + 0.2),
            (nobody - 0.3, take.at("sent", 1, line="nobody") + 0.2), (take.replied(7) - 0.1, take.replied(7) + 1.0)]
    shot, at = app_shot("16-checkin", take, keep,
                        lambda at: [(0, tapped(take, "#check-now")["tonight"]["y"] - 20, "cut"),
                                    (at(begun - 0.1), turn_view(seen(take, 6)), "cut"),
                                    (at(nobody - 0.3), talk_view(tapped(take, "#talk", 5)), "cut"),
                                    (at(take.replied(7) - 0.1), turn_view(seen(take, 7)), "cut")])
    overnight = ("Overnight check\u2011in", "", "info")  # a hyphen the line won't break at
    says(shot, at(begun) + 0.5, take, 6, [1], kicker, "", verdict=overnight,
         english_text=english["checkin"][-1])  # the English opening has one sentence more than the Hindi
    person(shot, at, take, "nobody", kicker, verdict=overnight)
    shots.append(fill(shot, kicker, "Taps “Check in now”."))
    summary = take.at("summary")
    summary_top = next(e["where"] for e in take.events if e["kind"] == "summary")["summary"]["y"] - 40
    shot, at = app_shot("17-summary", take, [(summary - 0.05, summary + 0.6, 6.8)],  # once it's on screen
                        lambda at: [(0, summary_top, "cut")])
    shot.captions.append(Caption(caps.add("The summary, in plain English", "",
                                          "What was measured, what the check-in found, and what's still unknown.",
                                          "The person shares it from the phone. It holds no name or address, and "
                                          "never says “safe”.", ("For the family", "", "info")), 0, shot.seconds))
    shots.append(fill(shot, kicker))

    # 6. Other languages: the same rules in English, and the agencies' own Spanish.
    take = Take("english")
    kicker = "The same rules in English"
    answer = take.replied(3)
    length = spoken(take, 3, [1])
    shot, at = app_shot("18-english", take, [(answer - 0.1, answer + 0.6, length + 0.3)],
                        lambda at: [(0, card_view(seen(take, 3)), "cut"),
                                    (at(answer + 0.6) + 0.5 * length, reply_view(seen(take, 3)), "pan")])
    says(shot, at(answer) + 0.3, take, 3, [1], kicker, "", verdict=verdict(take, 3),
         note="After the same photo and the same plain “yes, it's outside”.")
    shots.append(fill(shot, kicker))
    take = Take("spanish")
    back = take.replied(2)
    file, a, b = coach(take, 2, [0])[0]
    shot, at = app_shot("19-spanish", take, [(back - 0.1, back + 0.6, 6.4)],
                        lambda at: [(0, reply_view(seen(take, 3)), "cut")])
    shot.sounds.append(Sound(at(back) + 0.4, file, a, a + 5.6))
    shot.captions.append(Caption(caps.add("Spanish: only the agencies' own safety lines", "Coach (CPSC's Spanish)",
                                          SOURCES["cpsc-indoors"].quote.split(". ")[0] + ".",
                                          verdict=verdict(take, 2)), 0, shot.seconds))
    shots.append(fill(shot, kicker))

    # 7. How it works, does it work, and the close.
    shots.append(still("20-architecture", CARDS / "architecture.png", 7))
    shots.append(still("21-results", CARDS / "results.png", 10))
    shots.append(still("22-close", CARDS / "close.png", 5))
    shots.append(still("23-credits", CARDS / "credits.png", 6))
    shots[-1].fade = (0.0, 0.6)

    caps.render()
    parts = [render_shot(shot, EDIT / f"{shot.name}.mp4") for shot in shots]
    listing = EDIT / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    out = video / "aftermath-poc-v1.mp4"
    # Encoded once more as a whole: joined as they are, the parts' differing H.264 headers made a straight-through
    # decode skip the cards.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c:v", "libx264",
                    "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace",
                    "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out)], check=True)
    total = sum(s.seconds for s in shots)
    print(f"{out}: {len(shots)} shots, {int(total // 60)}:{total % 60:04.1f}")
    return out


CREDITS = [
    "Staged for this video: no generator was run. The door photos are the builder's own, with people and rooms "
    "blurred. The person's voice is a synthetic stand-in, pitched lower than the coach's.",
    "Screen recordings: the real app on one laptop, through its own page, at iPhone size (Playwright, headless "
    "Chromium). Both voices are Meta MMS-TTS (CC BY-NC 4.0), the app's own voice model.",
    "Models: SAM 3.1 (SAM License) · Muse Glimmer · Muse Spark and Muse Voice Transcribe (Meta Model API terms) · "
    "Meta MMS speech recognition (CC BY-NC 4.0).",
    "Hurricane Ian aerials: U.S. Coast Guard video by Petty Officer 3rd Class Ian Gray (via DVIDS), public domain.",
    "Florida night lights before and after Ian: NASA's Scientific Visualization Studio / NASA Black Marble "
    "(SSAI/Michala Garrison), public domain.",
    "“Prevent Carbon Monoxide Poisoning” animation: Centers for Disease Control and Prevention (CDC), public domain.",
    "The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW "
    "endorsement. No agency endorses Aftermath.",
    "Figures: CPSC, 88 FR 24346 (2023) · Iqbal et al., Am J Public Health 2012 · Portillo et al. 2024 · NIST · CDC. "
    "Speech evaluation: Google FLEURS (CC BY 4.0).",
    "Type: Noto Sans and Noto Sans Devanagari (SIL Open Font License 1.1).",
]
