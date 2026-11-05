// The organizer makes the program public: the Publishing page's ticks,
// preview, share material and the master switch. Runs after
// rec-schedule-confirm.js on the same database. Timed to the narration in
// "schedule-part-3.m4a" (137.5 s). See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-schedule-publish";
const END = Number(process.env.SCHEDULE_PUBLISH_END) || 137.5;

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);
  // The public API answers with Cache-Control max-age=300, so the "Public
  // now" look at the internal program would be served again from the
  // browser's cache after Make public. The take shows the server's state.
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  const tick = async (title) => {
    const box = page.locator(`label.list-group-item:has-text("${title}") input[type="checkbox"]`).first();
    await L.click(page, box, { pause: 500 });
  };
  const wheel = async (dy) => {
    await page.mouse.wheel(0, dy);
    await L.sleep(400);
  };

  await page.goto(S + "/accounts/login/");
  await clock.at(3.4, "caption 1");
  await cap("Making the program public, part 3 of 3: sign in as an organizer");
  await clock.at(6.0, "username");
  await clock.type(page, 'input[name="login"]', "admin_user", 8.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 10.0);
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });
  await clock.at(12.0, "publishing");
  await page.goto(S + "/speakers/schedule/publishing/");

  await clock.at(16.0, "caption 2");
  await cap("2. The program is internal until you say otherwise; the website shows 'Program coming soon'");

  await clock.at(34.0, "caption rail");
  await cap("Organize, then Publishing in the sidebar");
  await clock.at(35.5, "rail");
  await L.click(page, 'a[href="/speakers/schedule/publishing/"]', { pause: 300 });

  await clock.at(38.3, "caption 3");
  await cap("3. Publish: tick the sessions to make public once they are on the confirmed schedule; breaks and keynotes need no tick");
  await clock.at(41.0, "tick 1");
  await tick("Pandas Are Bears: A Zoology Workshop");
  await clock.at(43.5, "tick 2");
  await tick("Duck Typing the Blues");
  // Down the list of sessions, ticked and not yet tickable alike.
  await clock.at(46.0, "scroll publish 1");
  await wheel(220);
  await clock.at(50.0, "scroll publish 2");
  await wheel(220);
  await clock.at(54.5, "save");
  await L.click(page, 'button:has-text("Save")', { pause: 400 });

  await clock.at(57.1, "caption 4");
  await cap("4. Preview: the website's own widget, showing the draft before anything is public");
  await clock.at(58.0, "preview");
  await L.click(page, 'a.nav-link:has-text("Preview")', { pause: 400 });
  await page.locator("[data-pyladiescon-widget] *").first().waitFor({ timeout: 15000 }).catch(() => {});
  // Down through the day, so more than the first slot is seen.
  await clock.at(61.0, "scroll preview 1");
  await wheel(260);
  await clock.at(64.0, "scroll preview 2");
  await wheel(300);
  await clock.at(67.0, "scroll preview 3");
  await wheel(300);
  await clock.at(70.0, "public now");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await L.sleep(500);
  await L.click(page, 'a.btn:has-text("Public now")', { pause: 400 });
  await clock.at(73.0, "draft again");
  await L.click(page, 'a.btn:has-text("Draft")', { pause: 400 });

  await clock.at(75.2, "caption 5");
  await cap("5. Share: the widget code, the websites allowed to show it, an iframe, the data feeds, and the preview token for the site build");
  await clock.at(76.5, "share");
  await L.click(page, 'a.nav-link:has-text("Share")', { pause: 400 });
  await clock.at(80.0, "scroll 1");
  await wheel(350);
  await clock.at(86.0, "scroll 2");
  await wheel(350);
  await clock.at(91.0, "scroll 3");
  await wheel(350);
  await clock.at(96.0, "scroll 4");
  await wheel(400);

  await clock.at(102.5, "caption 6");
  await cap("6. Make public when it is ready; 'Take back to internal' undoes it at any time");
  await clock.at(103.0, "scroll top");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await L.sleep(600);
  await clock.at(105.0, "make public");
  await L.click(page, 'button:has-text("Make public")', { pause: 400 });
  await page.locator('.badge:has-text("Public")').waitFor();

  await clock.at(106.5, "caption 7");
  await cap("7. Visitors see the ticked sessions and the program items now; a new tick goes live at once");
  await clock.at(108.0, "preview again");
  await L.click(page, 'a.nav-link:has-text("Preview")', { pause: 400 });
  await page.locator("[data-pyladiescon-widget] *").first().waitFor({ timeout: 15000 }).catch(() => {});
  await clock.at(111.0, "scroll public 1");
  await wheel(260);
  await clock.at(114.0, "scroll public 2");
  await wheel(300);

  await clock.at(122.6, "caption 8");
  await cap("Done: the grid built, confirmed for the speakers, and published to the world");
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
