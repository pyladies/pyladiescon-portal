// Screenshots for the video-upload announcement post. Run with
// scripts/screencasts/run.sh shots-media, which runs this twice: once with
// SHOTS_STAGE=before on the fresh data (the tile before any upload), then
// after seed-team.py (the video card, the team's files, the checklist).
// Writes PNGs into $SHOTS (default scripts/screencasts/out/shots).
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");
const L = require("./lib");

const OUT = process.env.SHOTS || path.join(__dirname, "out", "shots");
const S = L.CONFIG.base;
const SESSION = process.env.SCREENCAST_SESSION_TITLE || "Duck Typing the Blues";
const WIDTH = 1040;

async function band(page, from, to, file, { pad = 16, padBottom = pad, left = null } = {}) {
  const a = await page.locator(from).first().boundingBox();
  if (left === null) left = Math.max(0, a.x - 24);
  const b = await page.locator(to).first().boundingBox();
  const y = Math.max(0, a.y + (await page.evaluate(() => window.scrollY)) - pad);
  const bottom = b.y + b.height + (await page.evaluate(() => window.scrollY)) + padBottom;
  await page.screenshot({
    path: path.join(OUT, file),
    fullPage: true,
    clip: { x: left, y, width: WIDTH - left, height: bottom - y },
  });
  console.log("wrote", file);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: L.CONFIG.chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: WIDTH, height: 900 }, deviceScaleFactor: 2, locale: "en-US" });
  const page = await context.newPage();
  await page.goto(S + "/accounts/login/");
  await page.fill('input[name="login"]', "maria_performer");
  await page.fill('input[name="password"]', L.CONFIG.password);
  await page.click('button:has-text("Sign In")');
  await page.waitForURL((url) => !url.pathname.startsWith("/accounts/login"));

  await page.goto(S + "/speakers/me/sessions/");
  await page.click(`a:has-text("${SESSION}")`);
  await page.waitForLoadState();
  // The strip with the video tile, above the tabs. Shot before seed-team.py
  // (SHOTS_STAGE=before), while the tile still says the video is not uploaded.
  if (process.env.SHOTS_STAGE === "before") {
    await band(page, "h1", "#glance", "2026-video-upload-tile.png");
    await browser.close();
    return;
  }
  // The Files tab: the performer's video card with the length bar and the upload panel.
  await page.click("#tab-files-link");
  await page.waitForTimeout(400);
  await band(page, "#video", "#video", "2026-video-upload-panel.png");
  // Files from the team: the list, previews closed.
  await band(page, "#team-files", "#team-files", "2026-video-team-files.png");
  // The checklist tab: the video list.
  await page.click("#tab-checklist-link");
  await page.waitForTimeout(400);
  await band(page, 'h2:has-text("Checklist for this session")', "#tab-checklist", "2026-video-checklist.png");
  await browser.close();
})().catch((e) => {
  console.error("FAILED", String(e).slice(0, 600));
  process.exit(1);
});
