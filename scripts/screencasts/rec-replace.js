// The performer sends a take that is over the length limit, sees the error,
// replaces it with a shorter cut, then deletes her video. Runs after
// rec-upload.js on the same database. Timed to the narration in
// "reuploading and deleting file.m4a" (121.4 s). See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const SESSION = process.env.SCREENCAST_SESSION_TITLE || "Duck Typing the Blues";
const OUT = process.argv[2] || "video-replace";
const END = Number(process.env.REPLACE_END) || 121.4;
const LONG = L.path.join(__dirname, "out", "media", "performance-long.mp4");
const SHORT = L.path.join(__dirname, "out", "media", "performance-take2.mp4");

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);
  const file = () => page.locator('#video input[data-role="file"]');
  const upload = async (path, version) => {
    await file().scrollIntoViewIfNeeded();
    await file().setInputFiles(path);
    await L.click(page, '#video button[data-role="start"]', { pause: 200 });
    await page.locator(`#video .badge:has-text("v${version}")`).first().waitFor({ timeout: 180000 });
    await page.locator("#video").scrollIntoViewIfNeeded();
  };

  await page.goto(S + "/accounts/login/");
  await clock.at(2.5, "caption 1");
  await cap("1. Want to send a different video? Open your session and choose Replace video");
  await clock.at(21.5, "username");
  await clock.type(page, 'input[name="login"]', "maria_performer", 23.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 24.0);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });
  await page.goto(S + "/speakers/me/sessions/");
  await clock.at(24.8, "open session");
  await L.click(page, `a:has-text("${SESSION}")`, { pause: 200 });
  await clock.at(26.0, "replace video");
  await L.click(page, 'a:has-text("Replace video")', { pause: 400 });

  await clock.at(27.3, "caption 2");
  await cap("2. Pick the new file, choose Upload, and wait for it to finish");
  await clock.at(28.5, "upload the long take");
  await upload(LONG, 2);

  await clock.at(40.0, "caption 3");
  await cap("3. Over the limit: the bar turns red and the page asks for a shorter cut");
  await clock.at(45.5, "show tile");
  await page.evaluate(() => window.scrollTo(0, 0));

  await clock.at(49.0, "caption 4");
  await cap("4. Trim it, then Replace video again with the shorter cut. The newest version is the one that counts");
  await clock.at(51.0, "upload the short take");
  await upload(SHORT, 3);

  await clock.at(61.5, "caption 5");
  await cap("5. Within the limit: green. Earlier versions are listed underneath");
  await clock.at(67.0, "open earlier versions");
  await L.click(page, '#video summary:has-text("earlier version")', { pause: 300 });

  await clock.at(76.5, "caption 6");
  await cap("6. Don't want to share it anymore? Delete my video removes every version from our systems and storage");
  await clock.at(78.5, "click delete");
  await L.click(page, 'button:has-text("Delete my video")', { pause: 600 });
  const name = await page.locator("#media-delete-modal [data-role=name]").textContent();
  await clock.at(94.0, "caption copy");
  await cap("It can't be undone, so download a copy first");
  await clock.at(102.0, "caption type name");
  await cap("The portal asks you to type the file's name to confirm");
  await clock.at(108.5, "type name");
  await clock.type(page, "#media-delete-confirm", name.trim(), 113.5);
  await clock.at(115.3, "confirm");
  await L.click(page, '#media-delete-modal button[data-role="submit"]', { pause: 300 });
  await page.waitForLoadState("networkidle").catch(() => {});

  await clock.at(116.8, "caption 7");
  await cap("7. Gone: the tile says 'Not uploaded yet' again, until your next upload");
  await page.evaluate(() => window.scrollTo(0, 0));
  await clock.at(END - 1.5);
  await cap("");
  await clock.at(END, "end");

  const video = page.video();
  await context.close();
  console.log("video", await video.path());
  await browser.close();
})().catch(async (e) => {
  console.error("FAILED", String(e).slice(0, 600));
  if (ctxRef.c) await ctxRef.c.close();
  process.exit(1);
});
