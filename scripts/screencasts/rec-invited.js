const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-invited";

const ctxRef = {};
(async () => {
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "priya.raman@example.com" && /invited/.test(m.subject)).pop();
  const link = /https?:\/\/[^\s"<>)]+\/speakers\/invitations\/[^\s"<>)]+/.exec(mail.html)[0];

  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const cap = (t) => L.caption(page, t);
  const beat = (ms = 1800) => L.sleep(ms);

  await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
  await beat(800);
  await cap("1. The invitation arrives by email from the organizers");
  await beat(4000);
  await cap("Click the button in the email (or paste the address into your browser)");
  await beat(2500);
  await page.goto(link);
  await beat(500);

  await cap("2. The invitation page: what you are being invited to, and a note from the organizer");
  await beat(3500);
  await cap("Accepting signs you in and creates your speaker account. No password needed yet");
  await L.click(page, 'button:has-text("Accept")', { pause: 1800 });

  await cap("3. Welcome: check your name, and agree to the Code of Conduct and Terms of Service");
  await beat(2500);
  const first = page.locator('input[name="first_name"]');
  if (!(await first.inputValue())) await L.type(page, first, "Priya");
  const last = page.locator('input[name="last_name"]');
  if (!(await last.inputValue())) await L.type(page, last, "Raman");
  await L.click(page, 'input[name="coc_agreement"]');
  await L.click(page, 'input[name="tos_agreement"]');
  await cap("A password is optional. Leave it blank to sign in with an emailed code next time");
  await page.locator('input[name="password1"]').scrollIntoViewIfNeeded();
  await beat(3200);
  await L.click(page, 'button:has-text("Continue to my dashboard")', { pause: 1800 });

  await cap("4. Your dashboard: your session, its status, and what needs your attention");
  await beat(4200);
  await cap("5. Fill in your speaker profile: bio, photo and where you are");
  await L.click(page, 'a:has-text("Update speaker profile")', { pause: 1400 });
  await L.type(page, 'textarea[name="bio_md"]', "Priya builds and tests data pipelines for a health charity. She mentors new Pythonistas and writes about boring, reliable data engineering.");
  const file = page.locator('input[name="headshot"]');
  await file.scrollIntoViewIfNeeded();
  await beat(400);
  await file.setInputFiles(L.CONFIG.headshot);
  await L.type(page, 'input[name="location"]', "Chennai, India");
  await cap("The headshot is optional but attendees see it next to your session");
  await beat(2200);
  await L.click(page, 'button:has-text("Save profile")', { pause: 2000 });

  await cap("6. Your checklist: what you do, and what the team is doing for you");
  await L.click(page, 'a:has-text("My speaker checklist")', { pause: 1500 });
  await beat(2800);
  await cap("Items that say 'ticks itself' complete when you do the thing, like saving your bio and photo");
  await page.evaluate(() => window.scrollTo(0, 0));
  await beat(3800);
  await cap("Tick items you do yourself, and see the team's side under 'What we're preparing for you'");
  await page.waitForURL(/checklist/);
  await page.getByText(/preparing for you/i).first().scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => page.evaluate(() => window.scrollTo(0, 900)));
  await beat(4200);
  await cap("7. Your session: check the title and summary the way it will appear on the schedule");
  await page.evaluate(() => window.scrollTo(0, 0));
  await L.click(page, 'a:has-text("My sessions")', { pause: 1600 });
  await beat(3000);
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
