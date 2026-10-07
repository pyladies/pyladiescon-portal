// The performer uploads her first video. Timed to the narration in
// "how to upload your video.m4a", with the 3 s of dead air after
// "you can give it a title" cut out (131.3 s): the times below are when the
// narrator says each step. See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const SESSION = process.env.SCREENCAST_SESSION_TITLE || "Duck Typing the Blues";
const OUT = process.argv[2] || "video-upload";
const END = Number(process.env.UPLOAD_END) || 131.3;
const FILE = L.path.join(__dirname, "out", "media", "performance.mp4");

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);

  await page.goto(S + "/accounts/login/");
  await clock.at(1.5, "caption 1");
  await cap("1. PyJam, chapter highlights and other pre-recorded sessions: how to send us your video");
  await clock.at(14.3, "caption sign in");
  await cap("Sign in with your speaker account");
  await clock.at(15.3, "username");
  await clock.type(page, 'input[name="login"]', "maria_performer", 16.8);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 17.8);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });

  await clock.at(18.3, "caption 2");
  await cap("2. Open Speaking, then My sessions, and choose your session");
  await page.goto(S + "/speakers/me/");
  await clock.at(20.2, "my sessions");
  await L.click(page, 'a:has-text("My sessions")', { pause: 200 });
  await clock.at(22.3, "open session");
  await L.click(page, `a:has-text("${SESSION}")`, { pause: 200 });

  await clock.at(24.0, "caption 3");
  await cap("3. Your session page: the 'Your video' tile says it is not uploaded yet, and shows the length limit");
  await clock.at(36.5, "caption 4");
  await cap("4. Choose Upload video; it opens the Files tab");
  await clock.at(37.5, "click upload video");
  await L.click(page, 'a:has-text("Upload video")', { pause: 400 });

  await clock.at(44.0, "caption 5");
  await cap("5. Pick your file (MP4 is best, MKV and MOV work too); a title is optional");
  const file = page.locator('#video input[data-role="file"]');
  await file.scrollIntoViewIfNeeded();
  await clock.at(45.5, "choose file");
  await L.click(page, '#video label[for^="upload-file"]', { pause: 150 }).catch(() => {});
  await file.setInputFiles(FILE);
  await clock.at(52.5, "title");
  await clock.type(page, '#video input[data-role="title"]', "take 1, acoustic set", 55.0);

  await clock.at(55.0, "caption 6");
  await cap("6. Choose Upload, and wait for it to finish");
  await clock.at(55.8, "click upload");
  await L.click(page, '#video button[data-role="start"]', { pause: 200 });
  // The panel reloads the page when the upload completes; the Files tab comes back by its hash.
  await page.waitForURL(/#files|#video/, { timeout: 60000 }).catch(() => {});
  await page.locator('#video .badge:has-text("v1")').first().waitFor({ timeout: 90000 });
  await page.locator("#video").scrollIntoViewIfNeeded();

  await clock.at(65.5, "caption 7");
  await cap("7. Done: version 1, with the length checked against the limit");
  await clock.at(77.5, "caption over");
  await cap("Over the limit? The bar turns red and the page asks for a shorter cut");
  await clock.at(88.0, "caption 8");
  await cap("8. On the checklist, 'Upload your performance video' has ticked itself, and the team is told");
  await clock.at(89.0, "checklist tab");
  await L.click(page, "#tab-checklist-link", { pause: 300 });
  await page.getByText("Upload your performance video").first().scrollIntoViewIfNeeded().catch(() => {});

  await clock.at(103.5, "caption 9");
  await cap("9. Once your video is in, the team starts on it: 'What we're preparing for your video'");
  await clock.at(109.0, "scroll to video list");
  await page.getByText(/preparing for your video/i).first().scrollIntoViewIfNeeded().catch(() => {});
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
