// The organizer confirms the schedule for the speakers, moves something
// afterwards, and the take switches to a speaker: their email and their
// schedule page. Runs after rec-schedule-build.js on the same database.
// Timed to the narration in "schedule-part-2.m4a" (144.5 s). See README,
// "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-schedule-confirm";
const END = Number(process.env.SCHEDULE_CONFIRM_END) || 144.5;
const DAY = process.env.SCREENCAST_DAY || "2026-12-05";
const SPEAKER_EMAIL = "juno@example.com";

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);
  const cell = (time, lane) =>
    page.locator(`.schedule-cell[data-time="${DAY}T${time}:00+00:00"][data-room-name="${lane}"]`).first();
  // By the card's own title: a double-booking warning quotes the other
  // session's title, so a plain has-text would match the wrong card.
  const card = (title) => page.locator(`.schedule-card:has(.schedule-card-title:text-is("${title}"))`).first();

  await page.goto(S + "/accounts/login/");
  await clock.at(2.8, "caption 1");
  await cap("1. Sign in as an organizer and open Schedule");
  await clock.at(5.0, "username");
  await clock.type(page, 'input[name="login"]', "admin_user", 7.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 9.0);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });
  await clock.at(10.5, "schedule");
  await page.goto(S + "/speakers/schedule/?day=" + DAY);
  await page.locator(".schedule-grid").waitFor();

  await clock.at(16.7, "caption 2");
  await cap("2. The grid is a draft: dashed cards are not yet confirmed to the speakers, and the button counts them");

  await clock.at(39.6, "caption 3");
  await cap("3. Confirm schedule: placed, moved and taken off are counted; emailing the affected speakers is on by default");
  await clock.at(41.0, "open popover");
  await L.click(page, 'summary:has-text("Confirm schedule")', { pause: 400 });
  // The popover hangs below the button; scroll so it sits clear of the
  // caption bar, with the checkbox and the button in full view.
  await page.evaluate(() => window.scrollBy({ top: 180, behavior: "smooth" }));
  await L.sleep(700);
  await clock.at(54.0, "confirm");
  await L.click(page, '.schedule-card-popover button:has-text("Confirm schedule")', { pause: 300 });
  await page.locator(".alert-success").waitFor();

  await clock.at(58.3, "caption 4");
  await cap("4. Confirmed: these sessions are now Scheduled, their checklists open, and each affected speaker gets one email");

  await clock.at(80.2, "caption 5");
  await cap("5. Later changes stay on the grid, dashed, until the next confirmation");
  await clock.at(84.5, "move jam");
  await L.drag(page, card("Duck Typing the Blues"), cell("16:00", "Main stage"));
  await L.sleep(800);

  // Captions live in the page's sessionStorage, per origin: set them after
  // arriving on maildev, and again after coming back to the portal.
  await clock.at(93.5, "open email");
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails
    .filter((m) => m.to.some((to) => to.address === SPEAKER_EMAIL))
    .filter((m) => /schedule/i.test(m.subject))
    .pop() || mails.filter((m) => m.to.some((to) => to.address === SPEAKER_EMAIL)).pop();
  if (!mail) throw new Error("no schedule email to " + SPEAKER_EMAIL + " in maildev");
  await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
  await clock.at(94.3, "caption 6");
  await cap("6. What a speaker receives: their sessions, in their own timezone, with a link to their schedule");

  await clock.at(100.0, "sign in as speaker");
  await context.clearCookies();
  await page.goto(S + "/accounts/login/");
  await cap("7. Their Schedule page shows the confirmed schedule in their timezone; the moved session waits for the next confirmation");
  await clock.type(page, 'input[name="login"]', "juno_kwargs", 101.5);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 102.8);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });
  await page.goto(S + "/speakers/me/schedule/");

  await clock.at(123.1, "caption 8");
  await cap("8. Add to calendar per session, or subscribe to the whole schedule so moves follow automatically");
  await clock.at(124.5, "subscribe");
  await L.click(page, 'summary:has-text("Subscribe in your calendar")', { pause: 400 });

  await clock.at(136.0, "caption 9");
  await cap("Next, part 3: publishing the program");
  await clock.at(END - 1.5);
  await cap("");
  await clock.at(END, "end");

  const video = page.video();
  await context.close();
  console.log("video", await video.path());
  await browser.close();
})().catch(async (e) => {
  console.error("FAILED", String(e).slice(0, 800));
  if (ctxRef.c) await ctxRef.c.close();
  process.exit(1);
});
