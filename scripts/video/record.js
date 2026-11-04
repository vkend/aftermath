// Screen recordings of the real phone page for the demo video, through the running app and its models.
//
//   NODE_PATH=data/video/node/node_modules node scripts/video/record.js <app address> <shots.json> <out folder>
//
// make_video.py writes shots.json (the scenes and their steps) and runs this. Headless Chromium shows the page at
// iPhone size: 393×852, drawn at 2× by zooming the page in a 786×1704 window (its screencast draws at 1× whatever the
// device's pixel ratio). The page's player is muted, because headless Chromium won't play sound unasked and nothing
// would hear it; the coach's audio is saved instead. The stand-in person's lines are played into a fake microphone,
// which the page
// records with its own MediaRecorder and sends to the app, as it would a person's voice. Each scene gets a folder:
// frames/ (the screen as Chromium drew it, with frames.json giving each frame's time), and events.json (every tap,
// recording and reply, with the reply's text, the verdict it showed and its audio, saved as reply-NN.wav).

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

// getUserMedia gives a stream that plays the next line set by __aftermathSay, a moment after recording starts.
const FAKE_MIC = `(() => {
  document.addEventListener("DOMContentLoaded", () => {
    document.documentElement.style.zoom = "2";
    document.getElementById("player").muted = true;
  });
  // Each reply from the app, handed to the recorder as the page gets it (without the photo's outline: too big to
  // pass, and the card screenshot shows it).
  const realFetch = window.fetch;
  window.fetch = async (...args) => {
    const response = await realFetch(...args);
    const route = new URL(response.url).pathname;
    if (route.startsWith("/api/") && args[1] && args[1].method === "POST") {
      response.clone().json().then((data) => {
        delete data.outline;
        window.__aftermathReply(route, response.status, data);
      }).catch(() => {});
    }
    return response;
  };
  let next = null, context = null;
  const audio = () => (context = context || new AudioContext({ sampleRate: 48000 }));
  window.__aftermathSay = async (url) => {
    next = await audio().decodeAudioData(await (await fetch(url)).arrayBuffer());
    return next.duration;
  };
  navigator.mediaDevices.getUserMedia = async () => {
    const ctx = audio();
    await ctx.resume();
    const out = ctx.createMediaStreamDestination();
    if (next) {
      const line = ctx.createBufferSource();
      line.buffer = next;
      line.connect(out);
      line.start(ctx.currentTime + 0.3);
      next = null;
    }
    return out.stream;
  };
  // A ring where the page is tapped, so the video shows what was pressed.
  window.__mark = (x, y) => {
    const ring = document.createElement("div");
    ring.style.cssText = "position:fixed;width:46px;height:46px;border-radius:50%;pointer-events:none;z-index:9999;" +
      "background:rgba(31,78,121,.28);border:3px solid rgba(31,78,121,.85);transition:opacity .6s,transform .6s;" +
      "left:" + (x / 2 - 23) + "px;top:" + (y / 2 - 23) + "px";  // the page is zoomed 2×
    document.body.appendChild(ring);
    requestAnimationFrame(() => requestAnimationFrame(() => { ring.style.transform = "scale(1.5)"; ring.style.opacity = "0"; }));
    setTimeout(() => ring.remove(), 700);
  };
})();`;

const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) " +
  "Version/18.6 Mobile/15E148 Safari/604.1";
const REPLIES = { "#begin": true, "#check-now": true, "#tap-yes": true, "#tap-no": true };

async function scene(browser, base, work, spec, out) {
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(path.join(out, "frames"), { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 786, height: 1704 }, deviceScaleFactor: 1, isMobile: false, hasTouch: true,
    ignoreHTTPSErrors: true, userAgent: IPHONE, colorScheme: "light",
  });
  await context.addInitScript(FAKE_MIC);
  const page = await context.newPage();
  const events = [], frames = [], replies = [];
  const now = () => Date.now() / 1000;
  const log = (kind, more = {}) => events.push({ t: now(), kind, ...more });
  page.on("console", (m) => m.type() === "error" && log("console-error", { text: m.text() }));
  await page.exposeBinding("__aftermathReply", (source, route, status, data) => {
    const n = String(replies.length + 1).padStart(2, "0");
    let audio = null;
    if (data.audio) {
      audio = `reply-${n}.wav`;
      fs.writeFileSync(path.join(out, audio), Buffer.from(data.audio.split(",")[1], "base64"));
    }
    const reply = { route, status, heard: data.heard, text: data.text,
      said: data.said, more: Boolean(data.more), placement: data.placement, level: data.level, verdict: data.verdict,
      door: data.door, tap: data.tap, language: data.language, audio };
    replies.push(reply);
    log("reply", reply);
  });

  const cdp = await context.newCDPSession(page);
  let frame = 0;
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    frame += 1;
    const file = `${String(frame).padStart(6, "0")}.jpg`;
    fs.writeFileSync(path.join(out, "frames", file), Buffer.from(data, "base64"));
    frames.push({ t: metadata.timestamp, file });
    await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });

  // Where the parts of the page are on the screen (in the window's pixels: the page is drawn at 2×), so the edit can
  // frame the card, the reply or the buttons.
  const PARTS = { verdict: "#verdict", head: "#verdict .head", action: "#action", choices: "#choices",
    outline: "#outline", reply: "#reply", call: "#call", talk: "#talk", status: "#status", banner: "#checkin-banner",
    summary: "#summary-details", tonight: "#tonight" };
  async function where() {
    const out = {};
    for (const [key, selector] of Object.entries(PARTS)) {
      const box = await page.locator(selector).first().boundingBox().catch(() => null);
      if (box) out[key] = { y: Math.round(box.y), h: Math.round(box.height) };
    }
    return out;
  }

  async function nextReply(from) {
    const deadline = Date.now() + 150000;
    while (Date.now() < deadline) {
      const done = replies.slice(from).find((r) => !r.more);
      if (done) {
        await page.waitForFunction(() => !document.querySelector("#status").textContent, null, { timeout: 60000 });
        await page.waitForTimeout(1000); // the page's own smooth scroll to the verdict
        const n = String(replies.indexOf(done) + 1).padStart(2, "0");
        log("shown", { reply: replies.indexOf(done) + 1, card: `card-${n}.png`, where: await where() });
        if (await page.locator("#verdict").isVisible()) {
          await page.locator("#verdict").screenshot({ path: path.join(out, `card-${n}.png`) });
        }
        return done;
      }
      await page.waitForTimeout(100);
    }
    const status = await page.textContent("#status");
    throw new Error(`${spec.name}: no reply after ${from} (status "${status}", last ${JSON.stringify(replies.at(-1))})`);
  }

  async function tap(selector, click = true) {  // without click: only the ring (a photo comes from the camera)
    const target = page.locator(selector);
    await target.scrollIntoViewIfNeeded();
    const box = await target.boundingBox();
    await page.evaluate(([x, y]) => window.__mark(x, y), [box.x + box.width / 2, box.y + box.height / 2]);
    await page.waitForTimeout(150);
    log("tap", { selector, where: await where() });
    if (click) await target.click();
  }

  await page.goto(`${base}/${spec.language ? `?language=${spec.language}` : ""}`);
  await page.waitForFunction(() => !document.querySelector("#begin").disabled);
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92 });
  await page.waitForTimeout(600);
  log("start");
  try {
  for (const step of spec.steps) {
    if (!step.rest) console.log(`  ${spec.name}: ${JSON.stringify(step)} (reply ${replies.length})`);
    if (step.tap) {
      const from = replies.length;
      await tap(step.tap);
      if (REPLIES[step.tap]) await nextReply(from);
    } else if (step.say) {
      const wav = fs.readFileSync(path.join(work, "voices", `${step.say}.wav`)).toString("base64");
      const seconds = await page.evaluate((d) => window.__aftermathSay(`data:audio/wav;base64,${d}`), wav);
      const from = replies.length;
      await tap("#talk");
      log("voice", { line: step.say, file: `${step.say}.wav`, seconds, starts: 0.3 });
      await page.waitForTimeout(300 + seconds * 1000 + 450);
      await tap("#talk");
      log("sent", { line: step.say });
      await nextReply(from);
    } else if (step.photo) {
      const from = replies.length;
      await tap("#door-label", false);
      log("photo", { file: step.photo });
      await page.setInputFiles("#door", path.join(work, step.photo));
      await nextReply(from);
    } else if (step.summary) {
      await page.evaluate(() => {
        const details = document.querySelector("#summary-details");
        details.open = true;
        details.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      await page.waitForTimeout(800);
      log("summary", { text: await page.textContent("#summary-text"), where: await where() });
    } else if (step.rest) {
      await page.waitForTimeout(step.rest);
    }
  }
  log("end");
  } finally {  // saved even when a step fails, to see where
    await cdp.send("Page.stopScreencast").catch(() => {});
    fs.writeFileSync(path.join(out, "frames.json"), JSON.stringify(frames));
    fs.writeFileSync(path.join(out, "events.json"), JSON.stringify(events, null, 1));
    await context.close();
  }
  const heard = replies.filter((r) => r.heard !== undefined).map((r) => `«${r.heard}»`).join(" ");
  console.log(`${spec.name}: ${frames.length} frames, ${replies.length} replies; heard ${heard || "nothing"}; ` +
    `ends on "${replies.at(-1)?.placement}"`);
}

(async () => {
  const [base, shotsFile, outDir] = process.argv.slice(2);
  const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
  const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
  try {
    for (const spec of shots.scenes) {
      if (shots.only.length && !shots.only.includes(spec.name)) continue;
      await scene(browser, base, shots.work, spec, path.join(outDir, spec.name));
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
