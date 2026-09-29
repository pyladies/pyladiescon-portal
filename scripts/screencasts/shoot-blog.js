// Screenshots for the speaker portal announcement post, on the screencast data.
// Run with: SCRIPT=shoot-blog.js scripts/screencasts/run.sh script
// Writes PNGs into $SHOTS (default scripts/screencasts/out/shots).
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");
const L = require("./lib");

const OUT = process.env.SHOTS || path.join(__dirname, "out", "shots");
const S = L.CONFIG.base;
const WIDTH = 1040;

async function context(browser) {
  return browser.newContext({ viewport: { width: WIDTH, height: 900 }, deviceScaleFactor: 2, locale: "en-US" });
}

async function login(page, username) {
  await page.goto(S + "/accounts/login/");
  await page.fill('input[name="login"]', username);
  await page.fill('input[name="password"]', L.CONFIG.password);
  await page.click('button:has-text("Sign In")');
  await page.waitForURL((url) => !url.pathname.startsWith("/accounts/login"));
}

// Screenshot a vertical band of the main column: from the top of `from` to the bottom of `to`.
async function band(page, from, to, file, { pad = 16, padBottom = pad, left = null } = {}) {
  const a = await page.locator(from).first().boundingBox();
  if (left === null) left = Math.max(0, a.x - 24);
  const b = await page.locator(to).first().boundingBox();
  const y = Math.max(0, a.y + (await page.evaluate(() => window.scrollY)) - pad);
  const bottom = b.y + b.height + (await page.evaluate(() => window.scrollY)) + padBottom;
  await page.screenshot({
    path: path.join(OUT, file),
    fullPage: true,
    clip: { x: left, y, width: WIDTH - left, height: bottom - y },
  });
  console.log("wrote", file);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: L.CONFIG.chrome, headless: true });

  // Organizer sets up the session and invites the presenter.
  const admin = await (await context(browser)).newPage();
  await login(admin, "admin_user");
  await admin.goto(S + "/speakers/sessions/new/");
  await admin.selectOption('select[name="kind"]', { label: "Workshop" });
  await admin.fill('input[name="title"]', "Hands-on Testing for Data Pipelines");
  await admin.fill('textarea[name="summary_md"]', "A hands-on workshop on testing data pipelines: small fixtures, contract checks, and what to watch in production.");
  await admin.click('button:has-text("Save")');
  await admin.waitForLoadState();
  await admin.goto(S + "/speakers/presenters/new/");
  await admin.fill('input[name="display_name"]', "Priya Raman");
  await admin.fill('input[name="email"]', "priya.raman@example.com");
  await admin.fill('input[name="pronouns"]', "she/her");
  await admin.selectOption('select[name="liaison"]', { label: "Lena Organizer" });
  await admin.selectOption('select[name="timezone"]', "Asia/Kolkata");
  await admin.click('button:has-text("Save")');
  await admin.waitForLoadState();
  const invite = 'form[id^="invite-form"]';
  await admin.selectOption(`${invite} select[name="session"]`, { label: "Hands-on Testing for Data Pipelines (Workshop)" });
  await admin.fill(`${invite} textarea`, "We loved your work on testing pipelines and would love to have you at PyLadiesCon 2026.");
  await admin.click(`${invite} button:has-text("Send")`);
  await admin.waitForLoadState();

  // The presenter accepts from the email.
  const mails = await (await fetch(L.CONFIG.maildev + "/email")).json();
  const mail = mails.filter((m) => m.to[0].address === "priya.raman@example.com" && /invited/.test(m.subject)).pop();
  const link = /https?:\/\/[^\s"<>)]+\/speakers\/invitations\/[^\s"<>)]+/.exec(mail.html)[0];
  const spk = await (await context(browser)).newPage();
  await spk.goto(link);
  await spk.click('button:has-text("Accept")');
  await spk.waitForLoadState();
  const first = spk.locator('input[name="first_name"]');
  if (!(await first.inputValue())) await first.fill("Priya");
  const last = spk.locator('input[name="last_name"]');
  if (!(await last.inputValue())) await last.fill("Raman");
  await spk.check('input[name="coc_agreement"]');
  await spk.check('input[name="tos_agreement"]');
  await spk.click('button:has-text("Continue to my dashboard")');
  await spk.waitForURL(/\/speakers\/me\/$/);

  // Fill the profile, so bio and headshot count as done.
  await spk.goto(S + "/speakers/me/profile/");
  await spk.fill('textarea[name="bio_md"]', "Priya builds and tests data pipelines for a health charity. She mentors new Pythonistas and writes about boring, reliable data engineering.");
  await spk.setInputFiles('input[name="headshot"]', L.CONFIG.headshot);
  await spk.fill('input[name="location"]', "Chennai, India");
  await band(spk, 'label:has-text("Bluesky username")', 'button:has-text("Save profile")', "2026-speaker-portal-profile-privacy.png");
  await spk.click('button:has-text("Save profile")');
  await spk.waitForLoadState();

  await spk.goto(S + "/speakers/me/");
  await band(spk, 'h1:has-text("Welcome")', 'a:has-text("Open my checklist")', "2026-speaker-portal-dashboard.png");

  await spk.goto(S + "/speakers/me/checklist/");
  // Keep the first rows of each list, so both lists fit in one picture.
  const kept = await spk.evaluate(() => {
    let hidden = 0;
    for (const card of document.querySelectorAll(".card")) {
      const rows = [...card.querySelectorAll(".list-group-item")];
      rows.slice(4).forEach((row) => {
        row.style.display = "none";
        hidden += 1;
      });
    }
    return hidden;
  });
  console.log("hid rows:", kept);
  await band(spk, 'h1:has-text("My speaker checklist")', "text=/Discord channel and speaker role assigned/", "2026-speaker-portal-checklist.png", { padBottom: 60 });

  // A returning volunteer starts a proposal (not sent).
  const vol = await (await context(browser)).newPage();
  await login(vol, "vol_maya");
  await vol.goto(S + "/speakers/propose/");
  await vol.fill('input[name="you-display_name"]', "Maya Okafor");
  await vol.fill('textarea[name="you-bio_md"]', "Maya volunteered with the PyLadiesCon 2025 design team and teaches Python to first-time programmers.");
  await vol.selectOption('select[name="you-timezone"]', "America/Toronto");
  await vol.check('input[name="session-kind"] >> nth=0');
  await vol.fill('input[name="session-title"]', "Build Your First Data Pipeline");
  await vol.fill('textarea[name="session-summary_md"]', "A hands-on workshop: build a small, testable data pipeline with plain Python and pandas, aimed at people who have never shipped one.");
  await band(vol, 'button:has-text("Your session")', 'textarea[name="session-summary_md"]', "2026-speaker-portal-propose-form.png");

  await browser.close();
})().catch((e) => {
  console.error("FAILED", String(e).slice(0, 800));
  process.exit(1);
});
