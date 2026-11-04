// Records each candidate take of the stand-in's lines as the phone page would: played into a MediaRecorder from a
// fake microphone, saved as the WebM the page would send. make_video.py then has the app's MMS hear each one.
//
//   NODE_PATH=data/video/node/node_modules node scripts/video/audition.js <app address> <takes.json>

const fs = require("fs");
const { chromium } = require("playwright");

async function record(page, wav) {
  const data = fs.readFileSync(wav).toString("base64");
  const b64 = await page.evaluate(async (d) => {
    const ctx = new AudioContext({ sampleRate: 48000 });
    const buffer = await ctx.decodeAudioData(await (await fetch(`data:audio/wav;base64,${d}`)).arrayBuffer());
    const out = ctx.createMediaStreamDestination();
    const line = ctx.createBufferSource();
    line.buffer = buffer;
    line.connect(out);
    const recorder = new MediaRecorder(out.stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    const stopped = new Promise((done) => (recorder.onstop = done));
    recorder.start();
    line.start(ctx.currentTime + 0.3); // as record.js plays it
    await new Promise((done) => setTimeout(done, 300 + buffer.duration * 1000 + 450));
    recorder.stop();
    await stopped;
    await ctx.close();
    const bytes = new Uint8Array(await new Blob(chunks).arrayBuffer());
    let text = "";
    for (const byte of bytes) text += String.fromCharCode(byte);
    return btoa(text);
  }, data);
  fs.writeFileSync(wav.replace(/\.wav$/, ".webm"), Buffer.from(b64, "base64"));
}

(async () => {
  const [base, list] = process.argv.slice(2);
  const takes = JSON.parse(fs.readFileSync(list, "utf8"));
  const browser = await chromium.launch();
  const pages = [];
  for (let i = 0; i < 6; i += 1) {
    const page = await browser.newPage({ ignoreHTTPSErrors: true });
    await page.goto(base);
    pages.push(page);
  }
  let next = 0;
  await Promise.all(pages.map(async (page) => {
    while (next < takes.length) await record(page, takes[next++]);
  }));
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
