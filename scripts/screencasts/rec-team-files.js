// The performer hears about files the team shared, previews and downloads
// them, and approves the final cut. Runs after seed-team.py. Timed to the
// narration in "how files are shared with speakers.m4a" (91.1 s). See
// README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-team";
const END = Number(process.env.TEAM_END) || 91.1;

const ctxRef = {};
(async () => {
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "maria@example.com" && /new file/.test(m.subject)).pop();
  if (!mail) throw new Error("no digest email for maria@example.com in maildev; run seed-team.py first");
  const link = /https?:\/\/[^\s"<>)]+\/speakers\/me\/sessions\/[^\s"<>)]+/.exec(mail.html)[0];

  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);

  await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
  await clock.at(3.0, "caption 1");
  await cap("1. Files the team shares with you are announced in your regular email, with your to-dos");
  // maildev renders the message in an iframe; bring the files section into view while it is talked about.
  await clock.at(21.5, "scroll email");
  await page.frameLocator("iframe").getByText(/shared new files with you/).first()
    .scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
  await clock.at(28.5, "caption 2");
  await cap("2. The files are not attached: sign in, open your session, and go to the Files tab");
  await clock.at(31.5, "sign in");
  await page.goto(S + "/accounts/login/");
  await clock.type(page, 'input[name="login"]', "maria_performer", 34.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 35.3);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });
  await clock.at(36.5, "open session files");
  await page.goto(link);
  await page.locator("#team-files").waitFor({ timeout: 15000 });

  await clock.at(41.5, "caption 3");
  await cap("3. 'Files from the team': the newest version of each file, with its title and kind");
  await page.locator("#team-files").scrollIntoViewIfNeeded();
  await clock.at(50.3, "caption 4");
  await cap("4. Preview a file right here, or download it");
  await clock.at(51.5, "preview poster");
  await L.click(page, '#team-files li:has-text("Poster") summary:has-text("Preview")', { pause: 300 });
  await clock.at(56.5, "preview final cut");
  await L.click(page, '#team-files li:has-text("Final cut") summary:has-text("Preview")', { pause: 300 });
  const player = page.locator('#team-files li:has-text("Final cut") video');
  // Centre the player, and play it muted, so the preview is seen playing rather than as a 0:00 player.
  await player.evaluate((v) => { v.scrollIntoView({ block: "center" }); v.muted = true; return v.play().catch(() => {}); });

  await clock.at(61.3, "caption 5");
  await cap("5. Once the final cut is shared, a new to-do appears: 'Approve the final cut'. Tick it to approve");
  await clock.at(63.0, "checklist tab");
  await L.click(page, "#tab-checklist-link", { pause: 300 });
  const row = page.locator("li.checklist-row", { hasText: "Approve the final cut" }).first();
  await row.scrollIntoViewIfNeeded();
  await clock.at(71.5, "mark done");
  await L.click(page, row.locator('button[type="submit"]'), { pause: 400 });

  await clock.at(86.0, "caption 6");
  await cap("Thank you, and see you in December!");
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
