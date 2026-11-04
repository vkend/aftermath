"""The demo video's pictures that aren't recordings: title, numbers, diagram, architecture, results, close, credits,
the phone's frame, and the captions beside it. Each is an HTML page rendered to PNG by scripts/video/render.js.

The numbers on the cards come from their sources (named on each card) and from today's evals (NUMBERS, which a file
data/video/numbers.json can override). Fonts: Noto Sans and Noto Sans Devanagari (SIL Open Font License), in
data/video/fonts.
"""

import html
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "data" / "video"
W, H = 1920, 1080
SCREEN = (110, 56, 900, 1100)  # the phone's screen on the frame: left, top, width, and a height that runs off the bottom
SCALE = SCREEN[2] / 786  # the recording (786 px wide, the page at 2×) to the screen
WINDOW = round((H - SCREEN[1]) / SCALE)  # how much of the recording's 1704 px height shows at once
PANEL = (1090, 96, 770, 920)  # the panel beside the phone: left, top, width, height
TONES = {"emergency": "var(--red)", "danger": "var(--red)", "warning": "var(--amber)", "info": "var(--blue)",
         "check": "var(--muted)"}

STYLE = """
@font-face { font-family: "Noto Sans"; src: url("FONTS/NotoSans.ttf"); font-weight: 100 900; }
@font-face { font-family: "Noto Sans Devanagari"; src: url("FONTS/NotoSansDevanagari.ttf"); font-weight: 100 900; }
:root { --bg: #0f1419; --panel: #18202a; --ink: #f2efe8; --muted: #a7b0bb; --blue: #8ec5ff; --red: #ff8a80;
  --amber: #ffc266; --line: #2c3743; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: WIDTHpx; height: HEIGHTpx; overflow: hidden; }
body { background: BACKGROUND; color: var(--ink); font-family: "Noto Sans", "Noto Sans Devanagari", sans-serif; }
.hi { font-family: "Noto Sans Devanagari", "Noto Sans", sans-serif; }
.kicker { font-size: 24px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--amber); font-weight: 600; }
.source { font-size: 22px; color: var(--muted); }
.red { color: var(--red); } .blue { color: var(--blue); } .amber { color: var(--amber); } .muted { color: var(--muted); }
"""

NUMBERS = {
    "doors_oct29": [[10, 10.0], [10, 10.0], [15, 15.1], [20, 20.4], [25, 25.8], [30, 30.2]],  # tape, app (ft)
    "fleurs": {"hi": {"wer": 18.2, "cer": 5.9}, "en": {"wer": 10.8, "cer": 5.0}, "sentences": 50},
    "fleurs_vt": {"hi": {"wer": 10.5, "cer": 5.3}, "en": {"wer": 5.8, "cer": 3.7}},  # Muse Voice Transcribe
    "tests": 839,
    "unclear": "0 of 120",
    "datasets": None,  # filled from the public door datasets (P1b)
}


def numbers() -> dict:
    extra = VIDEO / "numbers.json"
    return {**NUMBERS, **(json.loads(extra.read_text()) if extra.exists() else {})}


def page(body: str, width: int = W, height: int = H, background: str = "var(--bg)", script: str = "") -> str:
    style = (STYLE.replace("FONTS", str(VIDEO / "fonts")).replace("WIDTH", str(width))
             .replace("HEIGHT", str(height)).replace("BACKGROUND", background))
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{style}</style></head>"
            f"<body>{body}<script>{script}</script></body></html>")


def render(jobs: list[dict], folder: Path) -> None:
    """Each job's HTML written to folder/html and rendered to its PNG (or frames)."""
    from make_video import node_modules  # scripts/video/make_video.py

    (folder / "html").mkdir(parents=True, exist_ok=True)
    for job in jobs:
        file = folder / "html" / f"{job['name']}.html"
        file.write_text(job.pop("page"), encoding="utf-8")
        job.update(html=str(file), out=str(folder / (job["name"] if job.get("frames") else f"{job['name']}.png")))
        job.setdefault("width", W)
        job.setdefault("height", H)
    listing = folder / "html" / "jobs.json"
    listing.write_text(json.dumps(jobs))
    subprocess.run(["node", str(Path(__file__).with_name("render.js")), str(listing)], check=True,
                   env={"NODE_PATH": str(node_modules()), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"})


def e(text: str) -> str:
    return html.escape(text)


def title() -> str:
    return page("""<div style="position:absolute; left:140px; top:250px; width:1640px">
      <div style="font-size:150px; font-weight:800; letter-spacing:-0.02em">Aftermath</div>
      <div style="font-size:50px; margin-top:20px">A phone coach for the days after a storm cuts the power.</div>
      <div style="font-size:36px; margin-top:28px; color:var(--muted); line-height:1.4">From one photo it measures how
        far the generator is from the door, and checks it against CDC guidance, in Hindi and English.</div></div>
      <div style="position:absolute; left:140px; bottom:110px; font-size:28px; color:var(--muted); line-height:1.6">
        Built during the hackathon, Oct 26 – Nov 4, 2026<br>
        Meta models: SAM 3.1 · Muse Glimmer · Muse Spark · Muse Voice Transcribe · MMS</div>""")


def figure(big: str, text: str, source: str, label: str = "") -> str:
    """A number over b-roll: a dark box at the lower left, and a label at the top saying what the b-roll shows."""
    tag = (f"<div style='position:absolute; left:90px; top:70px; padding:12px 22px; font-size:30px; font-weight:600; "
           f"background:rgba(12,16,21,0.78); border-radius:8px'>{e(label)}</div>") if label else ""
    return page(f"""{tag}<div style="position:absolute; left:90px; bottom:90px; width:980px; padding:40px 48px;
      background:rgba(12,16,21,0.86); border-left:8px solid var(--amber); border-radius:10px">
      <div style="font-size:120px; font-weight:800; line-height:1">{e(big)}</div>
      <div style="font-size:40px; margin-top:16px; line-height:1.3">{e(text)}</div>
      <div class="source" style="margin-top:18px">{e(source)}</div></div>""", background="transparent")


def words(kicker: str, lines: list[str], source: str = "") -> str:
    """A text card: a few large lines."""
    body = "".join(f"<div style='font-size:64px; font-weight:700; line-height:1.25; margin-top:28px'>{line}</div>"
                   for line in lines)
    return page(f"""<div style="position:absolute; left:160px; top:220px; width:1600px">
      <div class="kicker">{e(kicker)}</div>{body}
      <div class="source" style="margin-top:44px; font-size:26px">{e(source)}</div></div>""")


DIAGRAM = """
const FT = 36, DOOR = 470, Y = 660;  // 1 ft = 36 px; the door's x; the line from it
function draw(t) {
  const ease = (x) => x < 0 ? 0 : x > 1 ? 1 : x * x * (3 - 2 * x);
  const ft = 9 + 21 * ease((t - 1.6) / 2.4);
  const x = DOOR + ft * FT;
  document.getElementById("gen").setAttribute("transform", `translate(${x - 38}, ${Y - 30})`);
  document.getElementById("sight").setAttribute("x1", x - 40);
  const near = ft < 17, done = ft >= 29.9;
  const label = document.getElementById("label");
  label.textContent = done ? "30 ft: meets the guidance" : near ? "9 ft: too close" : `${ft.toFixed(0)} ft`;
  label.setAttribute("x", x);
  label.setAttribute("fill", near ? "#ff8a80" : done ? "#8ec5ff" : "#f2efe8");
}
"""


def diagram() -> str:
    """Top down: the house, its door, the CDC's 20 ft and the generator moved from 9 ft to 30 ft."""
    door, y, ft = 470, 660, 36
    r, tilt = 20 * ft, 0.42  # the CDC's 20 ft, drawn as an arc 0.42 radians either side of the line
    marks = "".join(f"<line x1='{door + n * ft}' y1='{y + 70}' x2='{door + n * ft}' y2='{y + 84}' stroke='#5b6876'/>"
                    f"<text x='{door + n * ft}' y='{y + 112}' fill='#a7b0bb' font-size='22' text-anchor='middle'>{n}</text>"
                    for n in range(0, 31, 5))
    svg = f"""<svg width="{W}" height="{H}" style="position:absolute; left:0; top:0">
      <rect x="110" y="{y - 260}" width="{door - 110}" height="520" fill="#1d2630" stroke="#5b6876"
        stroke-width="4"/>
      <text x="{(110 + door) / 2}" y="{y + 12}" fill="#a7b0bb" font-size="34" text-anchor="middle">house</text>
      <rect x="{door - 8}" y="{y - 50}" width="16" height="100" fill="#f2efe8"/>
      <text x="{door - 24}" y="{y - 64}" fill="#f2efe8" font-size="26" text-anchor="end">door</text>
      <path d="M {door + r * math.cos(tilt):.0f} {y - r * math.sin(tilt):.0f} A {r} {r} 0 0 1
        {door + r * math.cos(tilt):.0f} {y + r * math.sin(tilt):.0f}" fill="none" stroke="#ffc266" stroke-width="4"
        stroke-dasharray="14 12"/>
      <text x="{door + r * math.cos(tilt) + 14:.0f}" y="{y - r * math.sin(tilt) + 30:.0f}" fill="#ffc266"
        font-size="28">CDC: more than 20 ft</text>
      <line x1="{door}" y1="{y + 70}" x2="{door + 30 * ft}" y2="{y + 70}" stroke="#5b6876" stroke-width="3"/>
      {marks}
      <text x="{door + 15 * ft}" y="{y + 150}" fill="#a7b0bb" font-size="24" text-anchor="middle">feet from the door</text>
      <line id="sight" x1="0" y1="{y}" x2="{door + 12}" y2="{y}" stroke="#8ec5ff" stroke-width="3"
        stroke-dasharray="6 8"/>
      <g id="gen"><rect width="76" height="60" rx="10" fill="#e8b632" stroke="#7a5d10" stroke-width="3"/>
        <rect x="12" y="14" width="30" height="20" rx="3" fill="#7a5d10"/></g>
      <text id="label" x="0" y="{y - 60}" font-size="40" font-weight="700" text-anchor="middle"></text>
    </svg>"""
    head = """<div style="position:absolute; left:150px; top:90px; width:1700px">
      <div class="kicker">How it measures</div>
      <div style="font-size:52px; font-weight:700; margin-top:14px">Stand where the generator is. Photograph the
        door.</div>
      <div style="font-size:30px; color:var(--muted); margin-top:12px">The photo's lens and a door's usual height
        (6 ft 8 in) give the distance. The verdict uses the low end of its ±6% range.</div></div>"""
    return page(head + svg, script=DIAGRAM)


ARCHITECTURE = [
    ("Phone page", "mic · camera · Hindi, English, Spanish", 120, 180),
    ("Speech in", "MMS on the laptop, or Muse Voice Transcribe (API)", 520, 120),
    ("Reader", "Muse Glimmer on the laptop, or Muse Spark (API): fixed facts, never advice", 520, 300),
    ("Door photo", "SAM 3.1 finds the door; lens + 80 in door = distance ±6%", 520, 520),
    ("Rules in code", "every line quotes CDC, CPSC, NIST or Ready.gov; unclear answers never clear a danger", 1080, 300),
    ("Speech out", "MMS-TTS, numbers made speakable", 1080, 560),
    ("Check-in", "overnight reminder; plain-English summary for family", 1080, 760),
]


def architecture() -> str:
    boxes = "".join(f"""<div style="position:absolute; left:{x}px; top:{y}px; width:{460 if x > 200 else 300}px;
      padding:22px 26px; background:var(--panel); border:2px solid {'#ffc266' if name == 'Rules in code' else
      'var(--line)'}; border-radius:14px"><div style="font-size:34px; font-weight:700">{e(name)}</div>
      <div style="font-size:24px; color:var(--muted); margin-top:8px; line-height:1.35">{e(text)}</div></div>"""
                    for name, text, x, y in ARCHITECTURE)
    arrows = """<svg width="1920" height="1080" style="position:absolute; left:0; top:0">
      <defs><marker id="a" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
        <path d="M0,0 L12,6 L0,12 z" fill="#5b6876"/></marker></defs>
      <g stroke="#5b6876" stroke-width="4" fill="none" marker-end="url(#a)">
        <path d="M 420 250 L 512 190"/><path d="M 420 300 L 512 590"/>
        <path d="M 750 250 L 750 292"/><path d="M 980 380 L 1072 380"/><path d="M 980 600 L 1072 420"/>
        <path d="M 1310 470 L 1310 552"/><path d="M 1310 680 L 1310 752"/>
      </g></svg>"""
    foot = """<div style="position:absolute; left:120px; top:930px; font-size:30px; color:var(--muted)">
      Runs fully on one laptop with Muse Glimmer, no internet needed. The model reads; the rules decide.</div>
      <div style="position:absolute; left:120px; top:70px" class="kicker">How it works</div>"""
    return page(arrows + boxes + foot)


def scans() -> list[tuple[float, float, str]]:
    """The public scans' clean doors as (truth ft, app ft, set), from scripts/eval_doors.py's results."""
    file = ROOT / "data" / "evals" / "doors" / "results-app.json"
    if not file.exists():
        return []
    return [(r["truth_ft"], r["feet"], r["set"]) for r in json.loads(file.read_text())
            if r.get("matched") and r["category"].startswith("clean") and r.get("error_80in") is not None]


def results() -> str:
    n = numbers()
    left, top, size = 150, 250, 560  # the chart: truth against the app's reading, 0–35 ft

    def at(ft: float) -> float:
        return size * ft / 35

    colours = {"tape": "#8ec5ff", "diode": "#ffc266", "hypersim": "#a7b0bb"}
    points = [(tape, app, "tape") for tape, app in n["doors_oct29"]] + scans()
    dots = "".join(f"<circle cx='{left + at(truth)}' cy='{top + size - at(app)}' r='9' fill='{colours[kind]}' "
                   f"fill-opacity='0.9'/>" for truth, app, kind in points)
    grid = "".join(f"<line x1='{left}' y1='{top + size - at(v)}' x2='{left + size}' y2='{top + size - at(v)}' "
                   f"stroke='#2c3743'/><text x='{left - 16}' y='{top + size - at(v) + 8}' fill='#a7b0bb' "
                   f"font-size='22' text-anchor='end'>{v}</text><text x='{left + at(v)}' y='{top + size + 36}' "
                   f"fill='#a7b0bb' font-size='22' text-anchor='middle'>{v}</text>" for v in range(0, 36, 10))
    band = (f"<polygon points='{left},{top + size} {left + size},{top + size - at(35 * 1.06)} "
            f"{left + size},{top + size - at(35 * 0.94)}' fill='rgba(142,197,255,0.12)'/>")
    key = "".join(f"<circle cx='{left + 20}' cy='{top + 24 + 34 * i}' r='9' fill='{colours[kind]}'/><text "
                  f"x='{left + 40}' y='{top + 32 + 34 * i}' fill='#a7b0bb' font-size='22'>{label}</text>"
                  for i, (kind, label) in enumerate([("tape", "our door on a tape"), ("diode", "DIODE: real, laser"),
                                                     ("hypersim", "Hypersim: synthetic")]))
    chart = f"""<svg width="{W}" height="{H}" style="position:absolute; left:0; top:0">{grid}{band}
      <line x1="{left}" y1="{top + size}" x2="{left + size}" y2="{top}" stroke="#5b6876" stroke-dasharray="6 6"/>
      {dots}{key}<text x="{left + size / 2}" y="{top + size + 80}" fill="#a7b0bb" font-size="24"
      text-anchor="middle">true distance (ft)</text><text x="{left - 70}" y="{top + size / 2}" fill="#a7b0bb"
      font-size="24" text-anchor="middle" transform="rotate(-90 {left - 70} {top + size / 2})">the app (ft)</text></svg>"""
    fleurs, vt = n["fleurs"], n["fleurs_vt"]
    items = [
        "<b>Our door on a tape</b>: 6 photos within +3%, every band right.",
        "<b>Public scans</b>: real doors (DIODE, laser depth) within 2% given their true height; with the assumed "
        "6 ft 8 in, 4–7% short (the safe side).",
        "<b>Its blind spot</b>: a door partly hidden reads too far, so a warning that can mean that holds the verdict "
        "at borderline. Of 31 door views in scans and renders, one 16 ft away had “met the CDC's guidance”: now none "
        "does, and 5 right verdicts are borderline.",
        f"<b>Speech</b> (FLEURS, read sentences), Hindi words wrong: MMS on the laptop {fleurs['hi']['wer']:.1f}%, "
        f"Muse Voice Transcribe {vt['hi']['wer']:.1f}% (English {fleurs['en']['wer']:.1f}% and {vt['en']['wer']:.1f}%)."
        " <span class='muted'>A best case: little about short answers outdoors.</span>",
        "<b>Rating plates</b> (15 real labels): printed values read right, Muse Glimmer 50 of 62, Muse Spark 57. "
        "The app's checks caught Spark's two misreadings; Glimmer guessed none of the missing values.",
        f"<b>{n['unclear']}</b> unclear Hindi answers cleared a danger. <b>{n['tests']}</b> tests.",
    ]
    right = (f"<div style='position:absolute; left:830px; top:200px; width:1000px'>"
             + "".join(f"<div style='font-size:27px; line-height:1.32; margin-top:{0 if i == 0 else 22}px'>{item}"
                       f"</div>" for i, item in enumerate(items)) + "</div>"
             """<div style="position:absolute; left:150px; top:90px"><div class="kicker">Does it work?</div>
      <div style="font-size:52px; font-weight:700; margin-top:10px">Measured, and tested</div></div>""")
    return page(chart + right)


def close() -> str:
    return page("""<div style="position:absolute; left:160px; top:300px; width:1600px">
      <div style="font-size:84px; font-weight:800">It never says “safe”.</div>
      <div style="font-size:54px; margin-top:26px; line-height:1.3">It measures, cites the guidance, and asks.</div>
      <div style="font-size:34px; margin-top:70px; color:var(--blue)">github.com/vkend/aftermath</div>
      <div style="font-size:26px; margin-top:14px; color:var(--muted)">Code under the MIT licence · Meta models under
        their own terms</div></div>""")


def credits(lines: list[str]) -> str:
    items = "".join(f"<div style='margin-top:10px'>{e(line)}</div>" for line in lines)
    return page(f"""<div style="position:absolute; left:140px; top:90px; width:1640px; font-size:23px;
      line-height:1.35; color:var(--muted)"><div class="kicker" style="margin-bottom:18px">Credits</div>{items}</div>""")


def frame() -> str:
    """The phone around the screen recording, running off the bottom of the picture: everything but the screen, which
    stays transparent."""
    x, y, w, h = SCREEN
    return page(f"""<div style="position:absolute; left:{x}px; top:{y}px; width:{w}px; height:{h}px;
      border-radius:58px; box-shadow: 0 0 0 18px #05070a, 0 0 0 20px #3a4552, 0 0 0 4000px #0f1419"></div>""",
                background="transparent")


def together(text: str) -> str:
    """A number and its unit kept on one line ("30 ft", "0.9 s")."""
    return re.sub(r"(\d) (ft|feet|m|s)\b", "\\1\u00a0\\2", text)


def caption(kicker: str, who: str = "", english: str = "", note: str = "", verdict: tuple = ()) -> str:
    """The panel beside the phone: what's happening, the verdict the phone shows (big, in its band's colour: label,
    distance, tone), who's speaking, and what they say in English."""
    x, y, w, h = PANEL
    english, note = together(english), together(note)
    parts = [f"<div class='kicker'>{e(kicker)}</div>"] if kicker else []
    if verdict:
        label, distance, tone = verdict
        parts.append(f"<div style='font-size:70px; font-weight:800; line-height:1.06; margin-top:30px; "
                     f"text-transform:uppercase; color:{TONES[tone]}'>{e(label)}</div>")
        if distance:
            parts.append(f"<div style='font-size:60px; font-weight:700; margin-top:8px; color:{TONES[tone]}'>"
                         f"{e(distance)}</div>")
    if who:
        parts.append(f"<div style='font-size:24px; letter-spacing:.12em; text-transform:uppercase; margin-top:50px; "
                     f"color:{'var(--blue)' if who == 'Coach' else 'var(--muted)'}'>{e(who)}</div>")
    if english:
        parts.append(f"<div style='font-size:46px; font-weight:600; line-height:1.28; margin-top:12px'>{e(english)}"
                     "</div>")
    if note:
        parts.append(f"<div style='font-size:29px; color:var(--muted); margin-top:38px; line-height:1.35'>{e(note)}"
                     "</div>")
    return page(f"<div style='position:absolute; left:{x}px; top:{y}px; width:{w}px; height:{h}px'>{''.join(parts)}"
                "</div>", background="transparent")


def render_cards(folder: Path, credit_lines: list[str]) -> None:
    jobs = [
        {"name": "title", "page": title()},
        {"name": "n-deaths", "page": figure("1,332", "people killed by carbon monoxide from portable generators in "
                                            "the US, 2004–2021", "CPSC, 88 FR 24346 (2023)")},
        {"name": "n-days", "page": figure("89%", "of disaster carbon monoxide deaths came within three days",
                                          "Iqbal et al., American Journal of Public Health, 2012 (CDC)",
                                          "Florida at night, before and after Hurricane Ian (NASA)")},
        {"name": "n-language", "page": figure("59%", "of carbon monoxide cases at one Houston children's hospital "
                                              "in the 2021 Texas freeze preferred a language other than English",
                                              "Portillo et al. 2024")},
        {"name": "rule", "page": words("The advice", [
            "“Operate your generator outdoors more than 20 feet from windows, doors, and vents.”",
            "<span class='muted'>Nobody can see 20 feet. And many people never hear it in their language.</span>"],
            "CDC, carbon monoxide basics")},
        {"name": "nist", "page": words("Outside isn't enough", [
            "Up to half of nonfatal poisonings in the 2004–05 hurricane seasons involved a generator outdoors, "
            "but within 7 feet of the home."], "NIST")},
        {"name": "diagram", "page": diagram(), "frames": 150, "fps": 30},
        {"name": "architecture", "page": architecture()},
        {"name": "results", "page": results()},
        {"name": "close", "page": close()},
        {"name": "credits", "page": credits(credit_lines)},
        {"name": "frame", "page": frame(), "transparent": True},
    ]
    for job in jobs:
        if job["name"].startswith("n-"):
            job["transparent"] = True
    render(jobs, folder)
