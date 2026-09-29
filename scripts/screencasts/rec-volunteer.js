const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-volunteer";

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const cap = (t) => L.caption(page, t);
  const beat = (ms = 1800) => L.sleep(ms);

  await page.goto(S + "/");
  await cap("1. Start from the portal home page and choose Propose a session");
  await beat(2500);
  await L.click(page, 'a:has-text("Propose a session")', { pause: 1500 });

  await cap("2. You already have an account from volunteering last year: sign in with it");
  await beat(3500);
  await L.click(page, 'a:has-text("Sign in to the one I have")', { pause: 1500 });
  await L.type(page, 'input[name="login"]', "vol_maya");
  await L.type(page, 'input[name="password"]', L.CONFIG.password);
  await cap("Forgot your password? Use 'Send me a sign-in code' instead");
  await beat(2200);
  await L.click(page, 'button:has-text("Sign In")', { pause: 1800 });

  await cap("3. About you: this is what would go on the schedule if your session is accepted");
  await beat(2500);
  await L.type(page, 'input[name="you-display_name"]', "Maya Okafor");
  await L.type(page, 'input[name="you-pronouns"]', "she/her");
  await L.type(page, 'textarea[name="you-bio_md"]', "Maya volunteered with the PyLadiesCon 2025 design team. She builds data pipelines for a public library network and teaches Python to first-time programmers.");
  await L.type(page, 'input[name="you-location"]', "Toronto, Canada");
  await L.choose(page, 'select[name="you-timezone"]', "America/Toronto");

  await cap("4. Your session: pick the kind of session, then give it a title and a summary");
  await L.click(page, 'label:has-text("Talk ·")', { pause: 900 });
  await L.type(page, 'input[name="session-title"]', "Your First Data Pipeline in 30 Minutes");
  await L.type(page, 'textarea[name="session-summary_md"]', "A gentle tour of building a small, testable data pipeline with plain Python and pandas, aimed at people who have never shipped one.");
  await cap("The outline, prerequisites and audience are optional: a title and two sentences is enough to start");
  await L.type(page, 'textarea[name="session-outline_md"]', "Five minutes on why pipelines break, then three worked examples, then questions.");
  await L.click(page, 'label:has-text("Beginner")', { pause: 900 });
  await L.type(page, 'input[name="session-language"]', "en");

  await cap("5. Send the proposal");
  await L.click(page, 'button:has-text("Send the proposal")', { pause: 2200 });

  await cap("Your proposal is now Pending review. You can edit it or withdraw it while you wait");
  await beat(4500);
  await cap("You also get a confirmation email, and another when the organizers answer");
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "maya@example.com" && /proposal/i.test(m.subject)).pop();
  if (mail) {
    await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
    await beat(4500);
  }
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
