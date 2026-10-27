# Building the schedule

This guide is for organizers. It shows how to build the conference program
on the schedule grid, how to confirm it so the speakers see it, and how to
publish it to the world. The speaker-facing side is in the
[speaker guide](speakers.md).

You need an organizer account and the speaker module has to be switched on
for the edition. **Schedule** and **Publishing** appear under **Speakers** in
the **Organize** sidebar for organizers only; a liaison does not see them.

## The idea

The schedule has three audiences, and the portal keeps them apart:

1. **Build.** The grid under **Schedule** is the organizers' draft. Drag
   sessions around for as long as you like; nobody else sees it.
2. **Confirm.** **Confirm schedule** takes a snapshot of the whole grid for
   the speakers. This is when a session becomes **Scheduled**, its checklist
   opens the slot items, and each affected speaker gets one email. Nothing is
   public yet.
3. **Publish.** The **Publishing** page makes the program public: the website
   shows the sessions you have ticked, the calendar feed fills, and the data
   feeds answer.

Each step is a short video below, all three on practice data.

## Before you start: rooms

The grid needs rooms to place sessions in. For an online edition a room is
usually a Discord channel; for a venue, a stage or a room. Rooms are added
in the admin: open your account menu at the top right, choose **Admin
Area**, then **Rooms** under **Speaker portal**, and **Add room**. Give it a
name and the edition; pick its **Kind** (Stage, Voice, Text or Forum) and,
for a Discord room, add the channel's address and id if you have them. Until
a room exists, the grid only has the all-rooms lane.

A room you no longer use can be marked inactive instead of deleted; it stays
as a lane marked "retired" while anything is still placed in it.

## Build the grid

*[Video: Building the schedule. Embedded here once it is on YouTube.]*

*Recording: an organizer adds a room, drags sessions onto the grid, creates a
break, catches a double-booked presenter and views the day in a presenter's
timezone. Practice data.*

Open **Organize**, then **Schedule**. The grid has one tab per conference
day, the rooms across the top with an **All rooms** lane first, and
15-minute steps down the side. The grid is trimmed to the program, an hour
either side; **Show the whole day** opens it up. Everything confirmed and not
yet placed waits in the **Unscheduled** list on the right, with its type,
length and status.

### Placing and moving

- **Drag** a session from the Unscheduled list onto a cell. It takes the
  length its session has. A session whose type spans every room (an opening,
  a break) lands on the all-rooms lane as a band across the row.
- **Click an empty cell** to open a small panel for that time and room: pick
  an unscheduled session, or create a new program item right there.
- **Drag a card** to move it; drop it on an empty cell. **Pull the bottom
  edge** of a card to change its length.
- **The pencil** on any card, or the calendar icon on an Unscheduled row,
  opens a form instead: room, day, start time in UTC and minutes, then
  **Place**. **Remove** on a placed card takes it off the grid.
- **Program items** (an opening, break, social, closing) need no speaker. The
  **+ Program item** box in the sidebar creates one, born confirmed, that
  appears in the Unscheduled list ready to drag; the cell panel creates and
  places one in a single step.

!!! note "Slots are 15 minutes or longer"
    A slot runs between 15 minutes and a day, in whole quarter hours. A
    session type with a shorter default length (a 5-minute lightning talk,
    for example) cannot be placed until its session's length is raised to 15.

### What the grid refuses, and what it only warns about

- **Two sessions in one room at the same time** are refused, and so is a
  session under a band that spans every room. Two bands may share a time
  only when both are program items, such as a break and an announcement.
- **A presenter in two places at once** is allowed, because a moderator
  moving between rooms is legitimate, but both cards show a warning naming
  the other session. Fix it by moving one of them.
- **A draft or invited session** can go on the grid as a pencil mark: its
  card is dotted and reads "Pencilled in, publishes once confirmed". It stays
  out of everything the speakers see until everyone on it has accepted, then
  the next confirmation picks it up.

### Seeing the day as others will

- **Show times in** switches the whole grid to another timezone: your
  browser's (the default), UTC, the edition's, or that of any presenter on
  the grid, by name. Everything is
  stored in UTC; the switcher only relabels. Use it to catch the three a.m.
  slot before anyone is told about it.
- **Wide** gives the grid the whole screen, like a spreadsheet, and **Exit
  wide** brings the sidebar back. **Density** goes from Comfortable to
  Compact to **Fit the screen**, which puts the whole day on one screen.
  **All days** shows every day under each other.
- **Preview as public** opens the Publishing page's preview, the website's
  own view of the confirmed program.

**Unschedule all** takes every session of the current day off the grid.
Published sessions keep their slot.

## Confirm the schedule

*[Video: Confirming the schedule for the speakers. Embedded here once it is
on YouTube.]*

*Recording: the organizer confirms the grid, moves a session afterwards, and
the recording switches to a speaker's email and schedule page. Practice
data.*

A dashed border on a card means the speakers have not been told about it,
and the **Confirm schedule** button counts how many cards differ from what
they last saw. When the day holds together, choose it. The popover says what
will change for the speakers: how many sessions are placed, moved or taken
off. **Email the affected speakers** is ticked by default; untick it for a
silent fix, such as a typo in a time nobody has seen yet.

Confirming is one action for the whole edition, never per day, so the
speakers never see half a schedule. In one go it:

- takes a snapshot of every placed session, which is what the speakers'
  schedule pages, their session pages, the calendar feeds and the public
  program read from then on;
- moves each newly placed **Confirmed** session to **Scheduled**, which locks
  its title and opens the slot items on its checklists;
- returns a session taken off the grid to **Confirmed**, and marks a
  cancelled session as cancelled on the speakers' side;
- sends one email per affected presenter who has accepted, listing their
  sessions and times in their own timezone, with a link to their schedule
  page. Presenters whose sessions did not change hear nothing, and an invited
  co-presenter who has not accepted is never emailed.

You can keep working afterwards. A later move stays on the grid, dashed,
until the next confirmation, so you can shuffle for days without narrating
every change.

### What the speaker sees

- **The email**, titled "The conference schedule was updated", lists their
  sessions with day, time and room in their timezone.
- **Their Schedule page** (under **Speaking**) shows the confirmed schedule
  in their timezone with their own sessions marked. A session that is not
  public yet carries a **Not yet public** badge and is visible only to them.
- **Add to calendar** on each of their sessions, and **Subscribe in your
  calendar** for the whole schedule, give them a feed that follows every
  later confirmation by itself.

## Publish the program

*[Video: Making the program public. Embedded here once it is on YouTube.]*

*Recording: the organizer ticks sessions, previews the website's widget,
looks through the sharing material and makes the program public. Practice
data.*

Open **Organize**, then **Publishing**. The line under the title is the
edition's master switch: **Internal** means the website shows "Program coming
soon" and nothing about a session or a speaker is public. Three tabs sit
under it.

### Publish

Tick the sessions that may go public, then **Save**. A session can be ticked
once it is on the confirmed schedule; a row that says **Not on the confirmed
schedule yet** waits for the next confirmation. Breaks, keynotes and the
other program items need no tick: they appear with the schedule itself. A
presenter's bio and photo go public only through a ticked session, and only
if they have not opted out on their profile.

### Preview

The website's own widget, right here in the portal. **Draft** shows
everything on the confirmed schedule, ticked or not, as the website team
will see it with the preview token; **Public now** shows what a visitor
sees today. Changes on the grid appear here after the next confirmation.

### Share

Everything the website team needs:

| Section | What it is |
|---|---|
| **Website widget** | One snippet per view (schedule, sessions, speakers) to paste where the program should appear. Times show in each visitor's timezone. |
| **Websites allowed to show the program** | Browsers only let the widget read the program on the websites listed here. A portal admin edits the list; the page links to it. Until a website is listed, the widget shows nothing anywhere. |
| **Embed with an iframe** | For a website that cannot add a script tag. No allowed-website entry is needed for this. |
| **Data feeds** | The same public program as data: sessions, speakers and the schedule by day as JSON, and the calendar feed as `.ics`. Each follows the switches above. |
| **Preview token** | For whoever builds the website before launch. Added to a widget or a data feed, it shows the draft, everything on the confirmed schedule whether ticked or not. It has no expiry, stops working once the program is public, and **Make a new token** stops every earlier one. |

### Make public

When the program is ready, choose **Make public**. From then on the website
shows the ticked sessions and the program items, the calendar feed and the
data feeds answer, and a session you tick later goes live at once. **Take
back to internal** undoes it at any time. Visitors who loaded the program in
the five minutes before a change may see the old version until their
browser's copy expires.

## Calendars and data

- **Calendar feed.** The Share tab's `.ics` address is the whole public
  program, meant to be subscribed to rather than downloaded: a session that
  moves at the next confirmation updates in every subscribed calendar, and a
  cancelled one is carried as cancelled. It accepts `?sessions=a,b,c` for a
  selection, and `?kind=` and `?room=` filters. Each session also has its own
  feed, and each speaker a private one that includes their unpublished
  sessions.
- **JSON.** Sessions, speakers and the schedule by day, for anyone building
  their own page. Empty while the program is internal, unless the preview
  token is added.
- **No spreadsheet export** of the schedule exists today. The Presenters page
  has a CSV and a photo package of the people, and the Checklists board has
  its own CSV.

## Tips

- Place the opening, breaks and closing first; they give the day its shape,
  and sessions cannot cross them.
- Keep the timezone switcher on the presenter you are placing. The grid
  stores UTC and the speakers read their own zone, so a time that looks fine
  in UTC can be the middle of the night for them.
- Confirm when a day holds together, not after every move. Every
  confirmation with the email ticked sends a message to each affected
  speaker.
- A session whose speaker has not accepted yet can still be pencilled in.
  The grid keeps the plan; the speakers hear about it once they have
  confirmed and you confirm again.
- Give the website team the preview token early. They can build the whole
  site against the draft and switch to the live program by removing the
  token.

## If something does not work

| What you see | What it means and what to do |
|---|---|
| No **Schedule** or **Publishing** in the sidebar | They are for organizers (staff or superuser), not liaisons. If the whole **Speakers** group is missing, the module is off for the edition; ask the tech lead. |
| Only the **All rooms** lane | No room is recorded for the edition yet. Add rooms in the admin, under **Speaker portal**, **Rooms**. |
| A session is not in the Unscheduled list | Only confirmed, draft and invited sessions can be placed. A proposal waiting for an answer, or a cancelled session, cannot. |
| A drop is refused | The time is taken in that room, or the slot would cross a band that spans every room. Pick another cell, or move the other card first. |
| "A slot runs between 15 minutes and a day" | The session is shorter than one grid step. Raise its length on the session page, or in the pencil form. |
| The card is dotted | The session is a draft or still invited. It publishes to the speakers once everyone on it has accepted and you confirm again. |
| The card is dashed | The speakers have not been told about this placement or move yet. Confirm the schedule when ready. |
| A speaker says their session is wrong or missing | Their page shows the last confirmed snapshot, not the grid. Confirm the schedule, with the email ticked so they hear about it. |
| A session cannot be ticked on Publishing | It is not on the confirmed schedule. Place it and confirm first. |
| The website still says "Program coming soon" | The program is internal; choose **Make public**. If it was just made public, a visitor's browser may hold the old answer for up to five minutes. |
| The widget shows nothing on the website | The website is not in the allowed list on the Share tab. Ask a portal admin to add it, or use the iframe. |

For anything else, see [Getting help](speakers.md#getting-help).
