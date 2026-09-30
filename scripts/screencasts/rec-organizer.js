// Timed to the narration in "organizer walkthrough.m4a" (79.2 s): the times
// below are when the narrator says each step. See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-organizer";
const END = Number(process.env.ORGANIZER_END) || 80.5;

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);

  await page.goto(S + "/accounts/login/");
  await clock.at(1.9, "caption 1");
  await cap("1. Sign in with your organizer account");
  await clock.at(8.6, "username");
  await clock.type(page, 'input[name="login"]', "admin_user", 10.6);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 12.6);
  await clock.at(13.0, "sign in");
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });

  await clock.at(13.8, "caption 2");
  await cap("2. Open Organize, then Sessions in the Speakers group");
  await clock.at(16.6, "click sessions");
  await L.click(page, 'a[href="/speakers/sessions/"]', { pause: 200 }).catch(async () => {
    await page.goto(S + "/speakers/sessions/");
  });

  await clock.at(19.0, "caption 3");
  await cap("3. Create the session you are inviting them to: New session");
  await clock.at(21.2, "click new session");
  await L.click(page, 'a:has-text("New session")', { pause: 200 });
  await clock.at(22.8, "choose type");
  await L.choose(page, 'select[name="kind"]', "Workshop");
  await clock.type(page, 'input[name="title"]', "Hands-on Testing for Data Pipelines", 25.7);
  await clock.type(
    page,
    'textarea[name="summary_md"]',
    "A hands-on workshop on testing data pipelines: small fixtures, contract checks, and what to watch in production.",
    28.3,
  );
  await clock.at(28.4, "caption save");
  await cap("Choose the type, give it a title and a summary, then Save");
  await clock.at(28.9, "click save");
  await L.click(page, 'button:has-text("Save")', { pause: 200 });

  await clock.at(32.4, "caption 4");
  await cap("4. Add the person you are inviting: New presenter");
  await clock.at(34.0, "click new presenter");
  await L.click(page, 'a:has-text("New presenter")', { pause: 200 });
  await clock.at(35.6, "name");
  await clock.type(page, 'input[name="display_name"]', "Priya Raman", 37.4);
  await clock.type(page, 'input[name="email"]', "priya.raman@example.com", 40.6);
  await clock.at(41.8, "caption email");
  await cap("The email address is where the invitation goes. Pick a liaison to look after them");
  await clock.at(43.0, "timezone");
  await L.choose(page, 'select[name="timezone"]', "Asia/Kolkata");
  await clock.at(45.6, "liaison");
  await L.choose(page, 'select[name="liaison"]', "Lena Organizer");
  await clock.at(48.4, "save presenter");
  await L.click(page, 'button:has-text("Save")', { pause: 200 });

  await clock.at(49.8, "caption 5");
  await cap("5. Send the invitation: choose the session and write a personal note");
  const invite = 'form[id^="invite-form"]';
  await clock.at(51.8, "choose session");
  await L.choose(page, `${invite} select[name="session"]`, "Hands-on Testing for Data Pipelines (Workshop)");
  await clock.at(54.9, "note");
  await clock.type(page, `${invite} textarea`, "We loved your work on testing pipelines and would love to have you speak at PyLadiesCon 2026.", 59.2);
  await page.locator(`${invite} textarea`).blur();
  await clock.at(59.5, "caption preview");
  await cap("The preview shows exactly the email they will receive");
  await page.locator("text=EMAIL PREVIEW").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, 300));
  await clock.at(62.2, "scroll back");
  await page.evaluate(() => window.scrollTo(0, 250));
  await cap("6. Click Send");
  await clock.at(62.9, "click send");
  await L.click(page, `${invite} button:has-text("Send")`, { pause: 200 });

  await clock.at(64.2, "caption done");
  await cap("Done: the invitation shows as Sent. You can resend or cancel it here");
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
