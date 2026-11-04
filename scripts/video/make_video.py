"""The proof-of-concept demo video, built in code from screen recordings of the real app.

    uv run python scripts/video/make_video.py prepare --near <10 ft door photo> --far <30 ft door photo>
    uv run aftermath serve --host 127.0.0.1 --port 9443        # in another terminal: the real app and models
    uv run python scripts/video/make_video.py record             # the phone page at iPhone size, through the app
    uv run python scripts/video/make_video.py cards              # title, numbers, diagram, chart and credits
    uv run python scripts/video/make_video.py edit               # data/video/aftermath-poc-v1.mp4
    uv run python scripts/video/narrate.py                       # v2's narration, then edit2.py: the narrated cut

Everything it reads and writes is under data/video/, which is never committed: the b-roll (public domain, listed in
data/video/broll/SOURCES.md), the door photos, the voices, the recordings and the cut. docs/video-credits.md lists
what the video uses and under what terms.

- **prepare**: the door photos, with what's personal blurred (a person, the rest of the room) before the app sees them,
  in the two forms a phone sends: from Photo Library, with the camera's lens data, and from Safari's own camera, which
  keeps only the rotation. And the stand-in person's voice: takes chosen by **audition**.
- **audition**: MMS-TTS (the app's own voice, so no other licence), pitched apart from the coach, says each line with
  several seeds; each take goes through the page's own recording path (scripts/video/audition.js) to the app's MMS,
  and the first take the app reads as meant is kept: «हाँ, बाहर है» as a plain yes, the mumble as unclear. A person
  says it again when they're misheard; the takes that weren't heard right are listed, not hidden.
- **record**: scripts/video/record.js (Playwright, headless Chromium at 393×852, 2× pixels) talks to the running app
  through its own page: it taps the buttons, uploads the photos and speaks the stand-in's lines into a fake
  microphone, which the page records as it would a person's. It saves the screen as it was drawn, and each reply's
  text, state and audio.
- **cards** and **edit**: text, diagrams and the chart are HTML pages rendered by the same browser (ffmpeg here has no
  text filters), then ffmpeg cuts the recordings, the coach's audio (each reply cut to its verdict sentence), the
  stand-in's voice and the b-roll (muted) together, with English subtitles under every Hindi line.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "data" / "video"
WORK = VIDEO / "work"
TAKES = VIDEO / "takes"
PLAYWRIGHT = "1.63.0"  # the recorder's Playwright, installed under data/video/node

# What the stand-in person says (the coach's own hints where it gives one: «हाँ, बाहर है», «नहीं, किसी को नहीं», «हाँ,
# काम कर रहा है»), and what the app must make of it: a place, a plain yes or no to a question, unclear, symptoms.
LINES = {
    "garage": ("hi", "बिजली चली गई है, मैंने जनरेटर गैराज में चालू किया है", "garage"),
    "outside": ("hi", "हाँ, बाहर है", "yes:confirm-outside"),
    "mumble": ("hi", "हम्म", "unclear:confirm-outside"),
    "headache": ("hi", "सिर में दर्द हो रहा है", "symptoms"),
    "nobody": ("hi", "नहीं, किसी को नहीं", "no:checkin-symptoms"),
    "still-outside": ("hi", "हाँ, बाहर है", "yes:checkin-outside"),
    "alarm": ("hi", "हाँ, काम कर रहा है", "yes:checkin-co-alarm"),
    "en-outside": ("en", "Yes, it's outside.", "yes:confirm-outside"),
    "es-garage": ("es", "El generador está en el garaje.", "garage"),
}
# How the voice is told to say a line, where the written form came out wrong: MMS-TTS said «बाहर» like «बार» and
# dropped a first "yes". The caption shows the line as written.
SAY_AS = {"outside": ["हाँ बाहर है", "हाँ बा हर है", "हाँ बाहार है", "हां जी बाहर है"],
          "still-outside": ["हाँ बाहर है", "हाँ बा हर है", "हाँ बाहार है", "हां जी बाहर है"],
          "en-outside": ["yes it's outside", "yeah it's outside", "yes, yes, it's outside", "yess it's outside"]}
PITCHES = (1.18, 0.85)  # the stand-in's voice, raised or lowered from the coach's
SEEDS = range(4)
# Regions to blur, as fractions of the upright photo (left, top, right, bottom): the person, the children's drawings,
# the furniture and the rest of the room in the far photo; a sign and a bag beside the door in the near one.
BLUR = {"far": [(0.0, 0.33, 0.37, 1.0)], "near": [(0.94, 0.36, 1.0, 0.66)]}


def run(*command: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, **kw)


def prepare(near: Path, far: Path) -> None:
    """The photos, blurred, in their Photo Library and Take Photo forms, and the stand-in's lines."""
    from PIL import Image, ImageFilter, ImageOps

    WORK.mkdir(parents=True, exist_ok=True)
    for name, source in (("near", near), ("far", far)):
        jpeg = WORK / f"{name}-camera.jpg"
        run("sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", str(source), "--out", str(jpeg),
            capture_output=True)
        raw = Image.open(jpeg)
        exif = raw.getexif()
        image = ImageOps.exif_transpose(raw).convert("RGB")
        width, height = image.size
        for left, top, right, bottom in BLUR[name]:
            box = (round(left * width), round(top * height), round(right * width), round(bottom * height))
            image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(width / 60)), box[:2])
        exif[0x0112] = 1  # the pixels are upright now
        image.save(WORK / f"{name}-library.jpg", quality=92, exif=exif)  # keeps the lens data
        safari = Image.Exif()
        safari[0x0112] = 1
        image.resize((4032, 3024) if width > height else (3024, 4032)).save(WORK / f"{name}-takephoto.jpg",
                                                                           quality=92, exif=safari)
        jpeg.unlink()
    chosen = WORK / "audition" / "chosen.json"
    if chosen.exists():  # the auditioned takes, as the voices the recorder plays
        voices = WORK / "voices"
        voices.mkdir(exist_ok=True)
        for name, take in json.loads(chosen.read_text()).items():
            shutil.copy(take, voices / f"{name}.wav")
    print(f"prepared {WORK}")


def heard_as_meant(heard: str, check: str) -> bool:
    """Whether the app reads what MMS heard as the line means."""
    from aftermath.conversation import QUESTIONS, Conversation, quick_place, read_answer, says_symptoms

    kind, _, rule = check.partition(":")
    if kind == "garage":
        return quick_place(heard, "measure-distance") == "garage"
    if kind == "symptoms":
        return says_symptoms(heard)
    answer = read_answer(heard, QUESTIONS[rule])
    if kind == "unclear":
        return answer is None and Conversation._misheard(heard) or bool(answer and answer.bare and not answer.plain)
    if not (answer and answer.plain):
        return False
    question = QUESTIONS[rule]  # a yes, or the question's own words for it ("outside" alone, for outdoors)
    return answer.lean == kind or answer.value is not None and answer.of(question) == getattr(question, kind)


def audition(base: str) -> None:
    """Takes of each line, heard through the page's path by the app's MMS; the first heard as meant is chosen."""
    import torch

    from aftermath.cache import ResponseCache
    from aftermath.speech import Listener, Voice, to_wav16k, write_wav

    folder = WORK / "audition"
    folder.mkdir(parents=True, exist_ok=True)
    voice, takes = Voice(), []
    for name, (language, text, _) in LINES.items():
        # In one breath: the voice says a part cut off at a comma on its own, and a lone «हाँ» or "yes" came out too
        # short for MMS to hear.
        for variant, said in enumerate(SAY_AS.get(name, [text.replace(",", "")])):
          for seed in SEEDS:
            raw = folder / f"{name}-{variant}{seed}-raw.wav"
            if not raw.exists():
                torch.manual_seed(seed)
                write_wav(raw, voice.speak(said, language), voice.rate(language))
            for pitch in PITCHES:
                take = folder / f"{name}-{variant}{seed}-{pitch}.wav"
                # Half a second of silence first: MMS-TTS starts at its first sample, and MMS lost that first
                # syllable every time without it («हाँ, बाहर है» heard as «वार है», "yes" as "this").
                run("ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    f"asetrate={16000 * pitch:.0f},aresample=48000,atempo={1 / pitch:.4f},adelay=500:all=1,"
                    "apad=pad_dur=0.3", "-ac", "1", str(take))
                takes.append(take)
    listing = folder / "takes.json"
    listing.write_text(json.dumps([str(t) for t in takes]))
    env = {"NODE_PATH": str(node_modules()), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"}
    run("node", str(Path(__file__).with_name("audition.js")), base, str(listing), env=env)
    ears = Listener(ResponseCache(folder / "cache"))
    results, chosen = {}, {}
    for pitch in PITCHES:  # one pitch for every line, so the person keeps one voice
        for name, (language, text, check) in LINES.items():
            for take in sorted(folder.glob(f"{name}-[0-9]*-{pitch}.wav")):
                heard = ears.transcribe(to_wav16k(take.with_suffix(".webm"), folder / "heard.wav"), language)
                ok = heard_as_meant(heard, check)
                results[take.name] = {"line": name, "said": text, "heard": heard, "as meant": ok}
                if ok and name not in chosen.get(pitch, {}):
                    chosen.setdefault(pitch, {})[name] = str(take)
    (folder / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    best = max(PITCHES, key=lambda p: len(chosen.get(p, {})))
    for name in LINES:
        tried = [r for k, r in results.items() if r["line"] == name and k.endswith(f"-{best}.wav")]
        print(f"{name:14} {'chosen ' + Path(chosen[best][name]).name if name in chosen.get(best, {}) else 'NONE':28}"
              f" {sum(r['as meant'] for r in tried)} of {len(tried)} heard as meant")
    (folder / "chosen.json").write_text(json.dumps(chosen.get(best, {}), indent=1))


def node_modules() -> Path:
    """Playwright for the recorder, installed once under data/video/node."""
    folder = VIDEO / "node"
    if not (folder / "node_modules" / "playwright").exists():
        run("npm", "install", "--silent", "--prefix", str(folder), f"playwright@{PLAYWRIGHT}")
    return folder / "node_modules"


def record(base: str, only: list[str]) -> None:
    shots = WORK / "shots.json"
    shots.write_text(json.dumps({"scenes": SCENES, "only": only, "work": str(WORK)}, ensure_ascii=False, indent=1))
    env = {"NODE_PATH": str(node_modules()), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"}
    run("node", str(Path(__file__).with_name("record.js")), base, str(shots), str(TAKES), env=env)


# The scenes, as the recorder plays them: each in a fresh page (a new conversation) unless it says otherwise.
SCENES = [
    {"name": "cold-open", "steps": [{"tap": "#begin"}, {"say": "garage"}, {"rest": 3000}]},
    {"name": "hero", "steps": [
        {"tap": "#begin"}, {"rest": 1500},
        {"photo": "near-takephoto.jpg"}, {"rest": 2500},
        {"photo": "far-library.jpg"}, {"rest": 2500},
        {"say": "mumble"}, {"rest": 2500},
        {"say": "outside"}, {"rest": 2500},
        {"tap": "#check-now"}, {"rest": 1500},
        {"say": "nobody"}, {"rest": 1500},
        {"say": "still-outside"}, {"rest": 1500},
        {"say": "alarm"}, {"rest": 1500},
        {"summary": True}, {"rest": 3000}]},
    {"name": "lens", "steps": [{"tap": "#begin"}, {"rest": 1500}, {"photo": "far-takephoto.jpg"}, {"rest": 2500},
                               {"tap": "#tap-yes"}, {"rest": 3000}]},
    {"name": "symptom", "steps": [{"tap": "#begin"}, {"rest": 1500}, {"say": "headache"}, {"rest": 3000}]},
    {"name": "english", "language": "en", "steps": [{"tap": "#begin"}, {"rest": 1500}, {"photo": "far-library.jpg"},
                                                    {"rest": 2000}, {"say": "en-outside"}, {"rest": 3000}]},
    {"name": "spanish", "language": "es", "steps": [{"tap": "#begin"}, {"rest": 1500}, {"say": "es-garage"},
                                                    {"rest": 3000}]},
    # The narrated cut's hero (Nov 4): the builder's garage at taped 10 and 30 ft, as edit2.py's "garage" step makes
    # the photos (cleaned, with only their lens data). "Is it outside?" can't be tapped, so the stand-in says it.
    {"name": "garage", "steps": [{"tap": "#begin"}, {"rest": 1500}, {"photo": "garage-10ft.jpg"}, {"rest": 2500},
                                 {"photo": "garage-30ft.jpg"}, {"rest": 2500}, {"say": "outside"}, {"rest": 3500}]},
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    steps = parser.add_subparsers(dest="step", required=True)
    p = steps.add_parser("prepare")
    p.add_argument("--near", type=Path, required=True, help="a door photo from about 10 ft, with its lens data")
    p.add_argument("--far", type=Path, required=True, help="a door photo from about 30 ft, with its lens data")
    r = steps.add_parser("record")
    r.add_argument("--base", default="https://localhost:9443", help="where the app is being served")
    r.add_argument("--only", nargs="*", default=[], help="record only these scenes")
    a = steps.add_parser("audition")
    a.add_argument("--base", default="https://localhost:9443", help="where the app is being served")
    steps.add_parser("cards")
    steps.add_parser("edit")
    args = parser.parse_args()
    if args.step == "prepare":
        prepare(args.near.expanduser(), args.far.expanduser())
    elif args.step == "audition":
        audition(args.base)
    elif args.step == "record":
        record(args.base, args.only)
    elif args.step == "cards":
        from cards import render_cards  # scripts/video/cards.py
        from edit import CREDITS

        render_cards(VIDEO / "cards", CREDITS)
    elif args.step == "edit":
        from edit import cut  # scripts/video/edit.py

        cut(VIDEO)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    shutil.which("ffmpeg") or sys.exit("needs ffmpeg")
    main()
