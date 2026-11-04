// Renders HTML pages to PNG for the demo video's cards, captions and diagram (ffmpeg here has no text filters).
//
//   NODE_PATH=data/video/node/node_modules node scripts/video/render.js <jobs.json>
//
// Each job: {html, out, width, height, transparent} for one picture, or with "frames": n and "fps", a sequence
// out/000.png… where the page's draw(t) is called with each frame's time in seconds.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const browser = await chromium.launch();
  try {
    for (const job of jobs) {
      const page = await browser.newPage({ viewport: { width: job.width, height: job.height } });
      await page.goto(`file://${path.resolve(job.html)}`);
      await page.evaluate(() => document.fonts.ready);
      if (job.frames) {
        fs.mkdirSync(job.out, { recursive: true });
        for (let i = 0; i < job.frames; i += 1) {
          await page.evaluate((t) => window.draw(t), i / job.fps);
          await page.screenshot({ path: path.join(job.out, `${String(i).padStart(3, "0")}.png`),
            omitBackground: Boolean(job.transparent) });
        }
      } else {
        await page.screenshot({ path: job.out, omitBackground: Boolean(job.transparent) });
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
