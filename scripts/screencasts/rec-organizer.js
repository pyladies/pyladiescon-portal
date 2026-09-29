const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-organizer";

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const cap = (t) => L.caption(page, t);
  const beat = (ms = 1600) => L.sleep(ms);

  await page.goto(S + "/accounts/login/");
  await cap("1. Sign in with your organizer account");
  await beat();
  await L.type(page, 'input[name="login"]', "admin_user");
  await L.type(page, 'input[name="password"]', L.CONFIG.password);
  await L.click(page, 'button:has-text("Sign In")', { pause: 1500 });

  await cap("2. Open Organize, then Sessions in the Speakers group");
  await beat();
  await L.click(page, 'a[href="/speakers/sessions/"]', { pause: 1200 }).catch(async () => {
    await page.goto(S + "/speakers/sessions/");
  });
  await beat(1000);

  await cap("3. Create the session you are inviting them to: New session");
  await L.click(page, 'a:has-text("New session")', { pause: 1200 });
  await L.choose(page, 'select[name="kind"]', "Talk");
  await L.type(page, 'input[name="title"]', "Testing Data Pipelines Without Tears");
  await L.type(page, 'textarea[name="summary_md"]', "Practical ways to test a data pipeline: small fixtures, contract checks, and what to watch in production.");
  await cap("Choose the type, give it a title and a summary, then Save");
  await beat();
  await L.click(page, 'button:has-text("Save")', { pause: 1800 });

  await cap("4. Add the person you are inviting: New presenter");
  await beat();
  await L.click(page, 'a:has-text("New presenter")', { pause: 1200 });
  await L.type(page, 'input[name="display_name"]', "Priya Raman");
  await L.type(page, 'input[name="email"]', "priya.raman@example.com");
  await L.type(page, 'input[name="pronouns"]', "she/her");
  await L.choose(page, 'select[name="liaison"]', "Lena Organizer");
  await L.choose(page, 'select[name="timezone"]', "Asia/Kolkata");
  await cap("The email address is where the invitation goes. Pick a liaison to look after them");
  await beat(2200);
  await L.click(page, 'button:has-text("Save")', { pause: 1800 });

  await cap("5. Send the invitation: choose the session and write a personal note");
  await beat();
  const invite = 'form[id^="invite-form"]';
  await L.choose(page, `${invite} select[name="session"]`, "Testing Data Pipelines Without Tears (Talk)");
  await L.type(page, `${invite} textarea`, "We loved your work on testing pipelines and would love to have you speak at PyLadiesCon 2026.");
  await page.locator(`${invite} textarea`).blur();
  await beat(2500);
  await cap("The preview shows exactly the email they will receive");
  await page.locator("text=EMAIL PREVIEW").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, 300));
  await beat(3200);
  await page.evaluate(() => window.scrollTo(0, 250));
  await beat(800);
  await cap("6. Click Send");
  await L.click(page, `${invite} button:has-text("Send")`, { pause: 2000 });

  await cap("Done: the invitation shows as Sent. You can resend or cancel it here");
  await page.evaluate(() => window.scrollTo(0, 0));
  await beat(3500);
  await cap("");

  const video = page.video();
  await context.close();
  console.log("video", await video.path());
  await browser.close();
})().catch(async (e) => {
  console.error("FAILED", String(e).slice(0, 600));
  if (ctxRef.c) await ctxRef.c.close();
  process.exit(1);
});
