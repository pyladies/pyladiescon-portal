// Timed to the narration in speaker-invited-audio-recording.m4a (83.7 s): the
// times below are when the narrator says each step. See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-volunteer";
const END = Number(process.env.VOLUNTEER_END) || 84.5;

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);

  await page.goto(S + "/");
  await cap("1. Start from the portal home page and choose Propose a session");
  await clock.at(9.0, "click propose");
  await L.click(page, 'a:has-text("Propose a session")', { pause: 300 });

  await clock.at(12.8, "caption 2");
  await cap("2. You already have an account from volunteering last year: sign in with it");
  await clock.at(18.0, "click sign in link");
  await L.click(page, 'a:has-text("Sign in to the one I have")', { pause: 300 });
  await clock.at(21.5, "type username");
  await clock.type(page, 'input[name="login"]', "vol_maya", 24.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 26.5);
  await clock.at(26.9, "caption forgot");
  await cap("Forgot your password? Use 'Send me a sign-in code' instead");
  await clock.at(31.0, "click Sign In");
  await L.click(page, 'button:has-text("Sign In")', { pause: 300 });

  await clock.at(32.4, "caption 3");
  await cap("3. About you: this is what would go on the schedule if your session is accepted");
  await clock.at(33.0, "display name");
  await clock.type(page, 'input[name="you-display_name"]', "Maya Okafor", 34.2);
  await clock.type(page, 'input[name="you-pronouns"]', "she/her", 35.6);
  await clock.type(
    page,
    'textarea[name="you-bio_md"]',
    "Maya volunteered with the PyLadiesCon 2025 design team. She builds data pipelines for a public library network and teaches Python to first-time programmers.",
    39.3,
  );
  await clock.at(39.7, "location and timezone");
  await clock.type(page, 'input[name="you-location"]', "Toronto, Canada", 41.4);
  await L.choose(page, 'select[name="you-timezone"]', "America/Toronto");

  await clock.at(44.7, "caption 4");
  await cap("4. Your session: pick the kind of session, then give it a title and a summary");
  await clock.at(46.6, "kind");
  await L.click(page, 'label:has-text("Workshop ·")', { pause: 300 });
  await clock.at(49.6, "title");
  await clock.type(page, 'input[name="session-title"]', "Build Your First Data Pipeline", 51.2);
  await clock.at(52.0, "summary");
  await clock.type(
    page,
    'textarea[name="session-summary_md"]',
    "A hands-on workshop: build a small, testable data pipeline with plain Python and pandas, aimed at people who have never shipped one.",
    55.2,
  );
  await clock.at(56.1, "outline");
  await cap("The outline, prerequisites and audience are optional: a title and two sentences is enough to start");
  await clock.type(page, 'textarea[name="session-outline_md"]', "Five minutes on why pipelines break, then three worked examples, then questions.", 59.6);
  await clock.at(60.4, "level");
  await L.click(page, 'label:has-text("Beginner")', { pause: 200 });
  await clock.type(page, 'input[name="session-language"]', "en", 62.5);

  await clock.at(64.6, "caption 5");
  await cap("5. Send the proposal");
  await clock.at(65.4, "click send");
  await L.click(page, 'button:has-text("Send the proposal")', { pause: 200 });

  await clock.at(67.8, "caption pending");
  await cap("Your proposal is now Pending review. You can edit it or withdraw it while you wait");
  await clock.at(74.8, "email");
  await cap("You also get a confirmation email, and another when the organizers answer");
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "maya@example.com" && /proposal/i.test(m.subject)).pop();
  if (mail) await page.goto(L.CONFIG.maildev + "/#/email/" + mail.id);
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
