// Draws the v2 video's frames with scripts/video/stage.html: each worker page renders its share of the frames.
//
//   NODE_PATH=data/video/node/node_modules node scripts/video/render2.js <timeline.json> <out folder> [workers] [only]
//
// Frames are JPEG, numbered from 00000.jpg at 30 fps. With "only" (a comma list of seconds), just those frames are
// drawn, as still-<seconds>.png, to look at a moment without rendering the whole film.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const timeline = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const out = process.argv[3];
  const workers = Number(process.argv[4] || 6);
  const only = process.argv[5] ? process.argv[5].split(",").map(Number) : null;
  fs.mkdirSync(out, { recursive: true });
  const fps = 30;
  const total = Math.round(timeline.total * fps);
  const browser = await chromium.launch();
  const started = Date.now();
  try {
    const open = async () => {
      const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
      await page.goto(`file://${path.resolve(__dirname, "stage.html")}`);
      await page.evaluate((tl) => window.setup(tl), timeline);
      return page;
    };
    if (only) {
      const page = await open();
      for (const seconds of only) {
        await page.evaluate((t) => window.draw(t), seconds);
        await page.screenshot({ path: path.join(out, `still-${seconds.toFixed(2)}.png`) });
      }
      return;
    }
    let done = 0;
    const chunk = Math.ceil(total / workers);
    await Promise.all([...Array(workers).keys()].map(async (w) => {
      const page = await open();
      for (let i = w * chunk; i < Math.min(total, (w + 1) * chunk); i += 1) {
        await page.evaluate((t) => window.draw(t), i / fps);
        await page.screenshot({ path: path.join(out, `${String(i).padStart(5, "0")}.jpg`), type: "jpeg", quality: 93 });
        done += 1;
        if (done % 600 === 0) console.log(`${done}/${total} frames, ${((Date.now() - started) / 1000).toFixed(0)} s`);
      }
    }));
    console.log(`${total} frames in ${((Date.now() - started) / 1000).toFixed(0)} s`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
