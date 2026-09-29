# Inviting speakers

This guide is for organizers. It shows how to invite someone to speak, how to
follow what happens to the invitation, and what the speaker sees on their side.
The speaker-facing version is in the [speaker guide](speakers.md).

You need an organizer account (a staff or superuser account) and the speaker
module has to be switched on for the edition. If you do not see **Sessions**
and **Presenters** under **Speakers** in the **Organize** sidebar, ask the tech
lead. **Proposals** only appears while the edition is taking proposals, see
[Speakers who propose](#speakers-who-propose).

<video controls preload="metadata" width="100%" src="/assets/videos/organizer-invite-speakers.mp4">
  Your browser does not support embedded video. The steps are written out below.
</video>

*Recording: an organizer creates a workshop, adds a presenter and sends the
invitation.*

## The idea

An invitation ties a **person** (a presenter) to a **session**, or to the
conference in general. You can do the whole thing from the presenter's page:

1. Create the session, if it does not exist yet.
2. Add the presenter, with their email address.
3. Send the invitation, with an optional personal note.

The speaker accepts from the email. Accepting is their confirmation: their
checklist is created, they get a welcome email, and the session becomes
**Confirmed**. If the session needs several presenters (a panel with a
panelist and a moderator, for example), it becomes Confirmed once every
required presenter has accepted. There is no separate confirmation step for you
to chase.

## Steps

### 1. Create the session

1. Sign in and open **Organize**.
2. Under **Speakers**, choose **Sessions**, then **New session**.
3. Choose the **Type** (Talk, Workshop, Panel, PyJam performance and so on).
   The type sets the default length and whether the session is live or
   pre-recorded, and decides which checklist template the speaker gets.
4. Give it a **Title** and a **Summary**. Everything else can wait: the speaker
   can fill in the outline, level and language themselves.
5. Choose **Save**. The session starts as a **Draft**.

If you only want to invite someone to the conference in general and decide on
the session later, skip this step and choose **The conference in general** in
step 3.

### 2. Add the presenter

1. On the session page, in the **Presenters** box, choose **New presenter**.
   (If the person is already in the portal as a presenter, pick them from the
   list and choose **Add** instead, then continue at step 3.)
2. Fill in:
    - **Display name** and **Email** (both required). The email is where the
      invitation and reminders go, so double check it.
    - **Pronouns** are optional. **Timezone** is required and starts as UTC, so
      set it if you know theirs: the speaker's due dates and reminders follow
      it. The speaker can change both.
    - **Liaison**: the organizer or volunteer who looks after this speaker.
      Liaisons see the presenters they look after. Team items that are
      assigned to the liaison show their name on the speaker's checklist; the
      others say "not yet assigned" until someone takes them.
3. Choose **Save**. You land on the presenter's page, which says **Not invited
   yet**.

### 3. Send the invitation

1. On the presenter's page, under **Send invitation**, choose **Invite to**:
   either a session or **The conference in general**.
2. **Role on a new session** is only needed when you are adding them to a
   session they are not on yet, and you want a role other than the session
   type's default, which is usually Presenter. The list is the roles the
   edition offers, such as Panelist, Moderator, Host or Performer. Leave it
   blank otherwise.
3. Write a **Personal message**. It appears highlighted in the email. A line
   or two about why you are inviting them goes a long way.
4. Check the **Email preview** underneath. It is the exact email the speaker
   will receive, wrapper and all. The link in the preview is a placeholder;
   the real one is personal to the speaker.
5. Choose **Send**.

You stay on the presenter's page with a confirmation that the invitation was
sent, and that the presenter was added to the session. Their status reads
**Invited on** the date it went out, **not yet accepted**.

## Following an invitation

The **Invitations** table at the bottom of the presenter's page shows, for each
invitation:

| Status | Meaning |
|---|---|
| **Not sent** | The invitation exists but has not gone out yet. |
| **Sent** | The email went out and has not been opened. |
| **Opened** | The speaker opened the invitation page. |
| **Accepted** | They accepted. The session is Confirmed and their checklist exists. |
| **Declined** | They declined. Nothing else happens; the session stays as it was. |
| **Expired** | The link is valid for 14 days and nobody used it. |
| **Cancelled** | You cancelled it. |

**Resend** sends a fresh link and is offered on every invitation that has not
been accepted, including expired, declined and cancelled ones. **Cancel** is
only offered while the invitation is waiting, and makes its link stop working.

The same page also has **Their to-dos** and **What we're preparing for them**,
one above the other: the speaker's checklist and the team's checklist for that
speaker. They are empty until the speaker accepts. After that this is where you
follow the speaker until the end of the conference. The **Checklists** board in
the sidebar shows the same thing across every speaker.

## What the speaker sees

After accepting, the speaker lands on a welcome page (username, name, Code of
Conduct and Terms of Service agreement, optional password) and then their
dashboard. See the [speaker guide](speakers.md#flow-2-we-invite-you) for
the walkthrough, and share it with speakers who ask "what happens next?".

## Speakers who propose

Some speakers reach us through the public **Propose a session** link instead of
an invitation. Proposals only work while the edition has them switched on: in
the Django admin, open the edition's **Speaker settings** and tick the
proposals switch under **Proposals**. The intro text on the same form appears
above the proposal form.

Proposals land in **Proposals** under **Speakers**, and a notice goes to the
organizers' email address from the same settings. There you can:

- **Approve**: the speaker is confirmed on the session and their checklist is
  created, as when an invitation is accepted. They get an email titled "Your
  session is in", with links to their session and checklist. They do not get
  the "Welcome aboard" email, which is sent only when an invitation is
  accepted.
- **Not this time**: the proposer gets a short note without a reason, and sees
  the proposal as "Not accepted". You can still approve it later if a slot
  opens up.

## Tips

- Invite from the presenter page rather than typing addresses into the email
  yourself. The link is signed, personal and expires, and the portal records
  when it was sent, opened and answered.
- One presenter can have several invitations, for example one for a workshop and a
  later one for a panel.
- Speakers who have volunteered before already have an account. If the
  invitation goes to the address on that account and they have verified it,
  accepting signs them in to it instead of creating a second one. Invite the
  address they use in the portal.
- When a speaker says nothing arrived, look at the **Invitations** table on their
  presenter page: it shows when each invitation was sent, opened and answered.
  Maintainers can also read every email the portal has sent under
  **Maintenance**, **Emails**; that page needs the maintainer permission, so a
  staff organizer may not see it.
