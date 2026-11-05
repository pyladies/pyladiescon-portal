// The organizer builds a day of the program: a room in the admin, then the
// schedule grid. The Opening is already placed (seed-schedule.py), so the
// grid opens trimmed to the afternoon with the Unscheduled list in view.
// Timed to the narration in "scheduling-part-1.m4a" (239.5 s): the times
// below are when the narrator says each step. See README, "Narrated takes".
const L = require("./lib");
const S = L.CONFIG.base;
const OUT = process.argv[2] || "video-schedule-build";
const END = Number(process.env.SCHEDULE_BUILD_END) || 239.5;
const DAY = process.env.SCREENCAST_DAY || "2026-12-05";
const KEYNOTE = "There Should Be One Obvious Way to Keynote";
const WORKSHOP = "Pandas Are Bears: A Zoology Workshop";
const DRAFT_TALK = "My Code Works and Nobody Knows Why";
const PERFORMANCE = process.env.SCREENCAST_SESSION_TITLE || "Duck Typing the Blues";

const ctxRef = {};
(async () => {
  const launched = await L.launch({ record: OUT });
  ctxRef.c = launched.context;
  const { browser, context, page } = launched;
  const clock = L.startClock();
  const cap = (t) => L.caption(page, t);
  // A grid cell by UTC time and lane name ("All rooms", or a room).
  const cell = (time, lane) =>
    page.locator(`.schedule-cell[data-time="${DAY}T${time}:00+00:00"][data-room-name="${lane}"]`).first();
  // By the card's own title: a double-booking warning quotes the other
  // session's title, so a plain has-text would match the wrong card.
  const card = (title) => page.locator(`.schedule-card:has(.schedule-card-title:text-is("${title}"))`).first();
  const pending = (title) => page.locator(`.schedule-pending:has-text("${title}")`).first();
  // A <select> inside a popover, by its visible label, with the cursor on it.
  const chooseIn = async (loc, label) => {
    await loc.scrollIntoViewIfNeeded();
    const box = await loc.boundingBox();
    await L.moveTo(page, box.x + 60, box.y + box.height / 2);
    await page.evaluate(([a, b]) => window.__ripple && window.__ripple(a, b), [box.x + 60, box.y + box.height / 2]);
    await L.sleep(200);
    await loc.selectOption({ label });
    await L.sleep(500);
  };
  // The add-here panel opens below the clicked cell and is fixed to the
  // viewport, so bring the cell near the top first and it has room.
  const openCell = async (loc) => {
    await loc.evaluate((el) => {
      el.scrollIntoView({ block: "start" });
      window.scrollBy(0, -140);
    });
    await L.sleep(300);
    await L.click(page, loc, { pause: 400 });
    await page.locator("#schedule-cell-panel:not(.d-none)").waitFor();
  };

  await page.goto(S + "/accounts/login/");
  await clock.at(1.5, "caption 0");
  await cap("Building the schedule, part 1 of 3: the program grid");
  await clock.at(21.1, "caption 1");
  await cap("1. Sign in with your organizer account");
  await clock.at(24.0, "username");
  await clock.type(page, 'input[name="login"]', "admin_user", 26.0);
  await clock.type(page, 'input[name="password"]', L.CONFIG.password, 28.5);
  await clock.at(29.0, "sign in");
  await L.click(page, 'button:has-text("Sign In")', { pause: 200 });

  await clock.at(30.1, "caption 2");
  await cap("2. Rooms first: your account menu, Admin Area, then Rooms under Speaker portal, and Add room");
  await clock.at(44.6, "account menu");
  await L.click(page, 'a.dropdown-toggle:has-text("Welcome")', { pause: 500 });
  await clock.at(46.5, "admin area");
  await L.click(page, 'a.dropdown-item:has-text("Admin Area")', { pause: 300 });
  // Each click here loads a page: wait for it, or the next click lands on
  // the page before (the admin index has an Add link per model).
  await page.waitForURL(/\/admin\/$/);
  await clock.at(48.5, "rooms");
  await L.click(page, '#content-main a[href="/admin/speakers/room/"]', { pause: 300 });
  await page.waitForURL(/\/admin\/speakers\/room\/$/);
  await clock.at(50.5, "add room");
  await L.click(page, '.object-tools a.addlink', { pause: 300 });
  await page.waitForURL(/\/admin\/speakers\/room\/add\/$/);
  await clock.at(52.6, "conference");
  const conferenceValue = await page
    .locator('select[name="conference"] option')
    .evaluateAll((options) => (options.find((o) => /2026/.test(o.textContent)) || {}).value);
  const conferenceSelect = page.locator('select[name="conference"]');
  const cbox = await conferenceSelect.boundingBox();
  await L.moveTo(page, cbox.x + 60, cbox.y + cbox.height / 2);
  await conferenceSelect.selectOption(conferenceValue);
  await clock.at(54.0, "name");
  await clock.type(page, 'input[name="name"]', "Workshop room", 56.0);
  await clock.at(57.0, "save");
  await L.click(page, 'input[name="_save"]', { pause: 300 });

  await clock.at(58.5, "caption 3");
  await cap("3. Organize, then Schedule: rooms across, 15-minute steps down, the Opening already on as a band across every room");
  await clock.at(61.5, "schedule");
  await page.goto(S + "/speakers/schedule/?day=" + DAY);
  await page.locator(".schedule-grid").waitFor();

  await clock.at(96.3, "caption 4");
  await cap("4. Drag a session from Unscheduled into a room, at the quarter hour you want");
  await clock.at(97.5, "drag keynote");
  await L.drag(page, pending(KEYNOTE), cell("14:15", "Main stage"));
  await card(KEYNOTE).waitFor();

  await clock.at(101.0, "caption 5");
  await cap("5. Or click an empty cell and pick what goes there");
  await clock.at(102.5, "click cell");
  await openCell(cell("14:30", "Workshop room"));
  await clock.at(105.0, "pick workshop");
  await L.click(page, `#schedule-cell-panel .schedule-place-option:has-text("${WORKSHOP}")`, { pause: 300 });
  await card(WORKSHOP).waitFor();

  await clock.at(109.1, "caption 6");
  await cap("6. A presenter booked twice is a warning, never a block: Juno is in both");
  // Fails if no card warns: the caption would then point at nothing.
  const warned = page.locator(".schedule-warned").first();
  await warned.scrollIntoViewIfNeeded();
  const wbox = await warned.boundingBox();
  await L.moveTo(page, wbox.x + wbox.width - 40, wbox.y + 14);

  await clock.at(136.2, "caption 7");
  await cap("7. Drag a card to move it; its length comes along");
  await clock.at(137.5, "move workshop");
  // Onto an empty cell: a card covers its own footprint, so a drop inside it never reaches a cell.
  await L.drag(page, card(WORKSHOP), cell("16:00", "Workshop room"));
  await L.sleep(800);

  await clock.at(145.4, "caption 8");
  await cap("8. The pencil places or moves with a form instead: room, day, start and minutes");
  await clock.at(147.0, "open form");
  const jam = pending(PERFORMANCE);
  await L.click(page, jam.locator("summary"), { pause: 400 });
  const form = jam.locator("[data-slot-form]");
  await clock.at(149.0, "room");
  await chooseIn(form.locator('select[data-field="room"]'), "Main stage");
  await clock.at(151.0, "time");
  const timeField = form.locator('input[data-field="time"]');
  await L.click(page, timeField, { pause: 150 });
  await timeField.fill("15:15");
  await clock.at(153.0, "place");
  await L.click(page, form.locator('button[data-action="slot-apply"]'), { pause: 300 });
  await card(PERFORMANCE).waitFor();

  await clock.at(154.8, "caption 9");
  await cap("9. A break or social is a program item: add it from the sidebar, born confirmed, then drag it on");
  // The sidebar form rather than the cell panel: with this many unscheduled
  // sessions the panel runs past the bottom of a 640 px viewport.
  const itemForm = page.locator("form", { has: page.locator('button:has-text("Add to the program")') }).first();
  await clock.at(161.5, "kind");
  await chooseIn(itemForm.locator('select[name="kind"]'), "Break");
  await clock.type(page, itemForm.locator('input[name="title"]'), "Coffee break", 165.0);
  await clock.at(165.5, "add to the program");
  await L.click(page, itemForm.locator('button:has-text("Add to the program")'), { pause: 300 });
  await pending("Coffee break").waitFor();
  await clock.at(170.5, "drag break");
  await L.drag(page, pending("Coffee break"), cell("15:00", "All rooms"));
  await card("Coffee break").waitFor();

  await clock.at(176.0, "caption 10");
  await cap("10. A draft or invited session is pencilled in (dotted) and waits until its speakers confirm");
  await clock.at(178.0, "drag draft talk");
  await L.drag(page, pending(DRAFT_TALK), cell("15:30", "Main stage"));
  await card(DRAFT_TALK).waitFor();

  await clock.at(195.8, "caption 11");
  await cap("11. Show the grid in a presenter's timezone, to catch the 3 a.m. slot before anyone is told");
  await clock.at(199.0, "timezone");
  await L.choose(page, "#schedule-timezone", "America/New_York (Juno Kwargs)");

  await clock.at(217.6, "caption 12");
  await cap("12. Wide takes the whole screen, like a spreadsheet; Exit wide brings the menu back");
  await clock.at(219.5, "wide");
  await L.click(page, 'a:has-text("Wide")', { pause: 600 });
  await page.locator(".schedule-grid").waitFor();
  await clock.at(227.5, "exit wide");
  await L.click(page, 'a:has-text("Exit wide")', { pause: 600 });
  await page.locator(".schedule-grid").waitFor();

  await clock.at(230.6, "caption 13");
  await cap("Next, part 2: confirming the schedule for the speakers");
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
