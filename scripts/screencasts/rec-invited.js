// Timed to the narration in speaker-invited-flow-audio-recording.m4a (86.9 s): the
// times below are when the narrator says each step. See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-invited";
const END = Number(process.env.INVITED_END) || 88.0;

const ctxRef = {};
(async () => {
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "priya.raman@example.com" && /invited/.test(m.subject)).pop();
  const link = /https?:\/\/[^\s"<>)]+\/speakers\/invitations\/[^\s"<>)]+/.exec(mail.html)[0];

  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);

  await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
  await clock.at(2.0, "caption 1");
  await cap("1. The invitation arrives by email from the organizers");
  await clock.at(12.2, "caption button");
  await cap("Click the button in the email (or paste the address into your browser)");
  await clock.at(17.0, "open link");
  await page.goto(link);

  await clock.at(19.5, "caption 2");
  await cap("2. The invitation page: what you are being invited to, and a note from the organizer");
  await clock.at(23.1, "caption accept");
  await cap("Accept, or Decline if you cannot make it. Accepting signs you in and creates your speaker account");
  await clock.at(25.4, "click accept");
  await L.click(page, 'button:has-text("Accept")', { pause: 200 });

  await clock.at(32.2, "caption 3");
  await cap("3. Welcome: check your name, and agree to the Code of Conduct and Terms of Service");
  const first = page.locator('input[name="first_name"]');
  if (!(await first.inputValue())) await L.type(page, first, "Priya");
  const last = page.locator('input[name="last_name"]');
  if (!(await last.inputValue())) await L.type(page, last, "Raman");
  await clock.at(34.6, "agree CoC");
  await L.click(page, 'input[name="coc_agreement"]', { pause: 200 });
  await clock.at(36.2, "agree ToS");
  await L.click(page, 'input[name="tos_agreement"]', { pause: 200 });
  await clock.at(38.6, "caption password");
  await cap("A password is optional. Leave it blank to sign in with an emailed code next time");
  await page.locator('input[name="password1"]').scrollIntoViewIfNeeded();
  await clock.at(43.4, "continue");
  await L.click(page, 'button:has-text("Continue to my dashboard")', { pause: 200 });

  await clock.at(44.5, "caption 4");
  await cap("4. Your dashboard: your session, its status, and what needs your attention");
  await clock.at(50.3, "caption 5");
  await cap("5. Fill in your speaker profile: bio, photo and where you are");
  await clock.at(50.6, "click update profile");
  await L.click(page, 'a:has-text("Update speaker profile")', { pause: 200 });
  await clock.type(
    page,
    'textarea[name="bio_md"]',
    "Priya builds and tests data pipelines for a health charity. She mentors new Pythonistas and writes about boring, reliable data engineering.",
    54.6,
  );
  const file = page.locator('input[name="headshot"]');
  await file.scrollIntoViewIfNeeded();
  await clock.at(55.0, "headshot");
  await file.setInputFiles(L.CONFIG.headshot);
  await clock.type(page, 'input[name="location"]', "Chennai, India", 56.9);
  await clock.at(57.1, "caption headshot");
  await cap("The headshot is optional but attendees see it next to your session");
  await clock.at(59.3, "save");
  await L.click(page, 'button:has-text("Save profile")', { pause: 200 });

  await clock.at(60.5, "caption 6");
  await cap("6. Your checklist: what you do, and what the team is doing for you");
  await clock.at(60.7, "open checklist");
  await L.click(page, 'a:has-text("My speaker checklist")', { pause: 200 });
  await page.waitForURL(/checklist/);
  await page.evaluate(() => window.scrollTo(0, 0));
  await clock.at(68.2, "caption team side");
  await cap("Below is what the team is doing to prepare your session, and who on the team has each item");
  await page.getByText(/preparing for you/i).first().scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => page.evaluate(() => window.scrollTo(0, 900)));
  await clock.at(73.5, "caption sessions");
  await cap("7. Your session: check the title and summary the way it will appear on the schedule");
  await page.evaluate(() => window.scrollTo(0, 0));
  await clock.at(73.8, "open sessions");
  await L.click(page, 'a:has-text("My sessions")', { pause: 200 });
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
