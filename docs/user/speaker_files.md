# Your video and files

This guide is for speakers whose session is pre-recorded: a PyJam
performance, a PyLadies chapter highlight video, or any other session we
broadcast from a recording. It covers how to send us your video through the
portal, what happens to it afterwards, and how to find the files the team
shares back with you, such as the poster for your session, a transcript, or
the final cut of your video.

It assumes you are already on the program and know your way around your
speaker dashboard. If not, start with the [Speakers guide](speakers.md).

!!! note "Where everything lives"
    Everything in this guide happens on your **session page**: open
    **Speaking**, then **My sessions**, and choose your session. The page has
    three tabs: **Overview**, **Checklist** and **Files**. Your video and the
    team's files are on **Files**. If you do not see a Files tab, see
    [If something does not work](#if-something-does-not-work).

## Upload your video

*[Video: Upload your performance video. Embedded here once it is on
YouTube.]*

*Recording: a PyJam performer signs in, opens her session and uploads her
video. A chapter highlight video goes up the same way. Practice data.*

### Before you start

- Check the format, and the length for your kind of session, in the
  [Video guide](https://conference.pyladies.com/docs/speakers/video_guide/)
  on the conference site; it also has recording tips and equipment advice.
  The portal accepts the usual video formats: MP4 is best, MKV, MOV and WebM
  work too. A slide deck with recorded audio is not a video; export it as one
  first.
- Your session page shows the **length limit** for your kind of session: a
  PyJam performance and a chapter highlight have different limits, and the
  page shows yours. The portal measures your video after the upload and tells
  you if it is over.
- Big files are fine. The video goes straight to our storage in pieces, not
  through the portal's web server, so a file of several gigabytes uploads as
  well as a small one. A dropped connection does not lose what was sent.
- Watch your recording once before you send it. The
  [checklist in the Video guide](https://conference.pyladies.com/docs/speakers/video_guide/#before-you-submit)
  is a good last check.

### Steps

1. Open your session page. The **Your video** tile at the top says **Not
   uploaded yet**, and the Files tab shows the limit.
2. Choose **Upload video**. It opens the **Files** tab at the **Your video**
   card.
3. Choose **File** and pick the video on your computer.
4. **Title** is optional. It is a note for you and the team ("take 2, quieter
   room"), not the title of your session.
5. Choose **Upload**. The bar shows how much has gone up, and the line under
   it shows how many pieces are in flight. Keep the tab open until it says
   **Uploaded: version 1**; the page then reloads itself.

!!! tip "If your connection drops"
    Nothing is lost. When you come back to the page, a note says you have an
    unfinished upload of that file. Choose the **same file again** and
    **Upload**, and it continues from where it stopped. An upload that nothing
    finishes is dropped after two days, and you simply start again.

### What you see afterwards

- The **Your video** card shows **v1**, the file name, its size and when it
  arrived, with a **Preview** fold that plays it in the page and a
  **Download** link.
- The **length** is measured within a moment of the upload (longer if the
  team's media worker is busy) and shown as a bar against the limit: green
  within it, red when over. If it is over, the card says so and asks for a
  shorter cut: upload a new version (below). If the length could not be
  measured, the card says the team will look; you do not need to do anything.
- On the **Checklist** tab, the upload item (**Upload your performance
  video** for performers, or the equivalent for your kind of session) has
  ticked itself.
- Your liaison, the organizer looking after you, gets an email the moment
  your upload completes, so you do not need to tell anyone.

## Send a new take, or remove your video

*[Video: Send a new take, or remove your video. Embedded here once it is on
YouTube.]*

*Recording: the performer replaces her video with a second take, then deletes
it. Practice data.*

**A different video.** You have uploaded your video, but now want to send a
different one: the first was too long, or too short, or you forgot to mention
something. Whatever the reason, you can always upload a newer video. Choose
**Replace video** at the top of your session page, pick the new file and
choose **Upload**. The new file becomes **v2**, and the team always works from
your newest version, so there is nothing else to tell us. Earlier versions are
folded under the card, with a download link each, in case you want one back.
You can replace your video as often as you like up to the submission deadline.

**Over the limit.** If the length bar is red, your video is longer than the
limit for your kind of session, and the page asks for a shorter cut. Trim it
and upload it the same way; the newest version is the one that counts.

**Removing it.** If you simply decide you do not want to share this video with
us anymore, you can delete it. You have full control over the files you submit
to us. The card has a **Delete my video** button. It removes **every version**
you uploaded, from the portal and from storage, and cannot be undone, so make
sure you have downloaded a copy first; the portal asks you to type the file's
name as shown before the button works. The button is shown while every version
of the video is your own upload; if the team has uploaded a version on your
behalf, ask your liaison to remove it. While the portal is still transcribing
a video, the delete waits until that is done.

## What happens to your video

Once your video is in, the third list on your checklist, **What we're
preparing for your video**, follows the team's work on it. The items are the
team's, not yours; you can watch them move, and see who on the team is on
each one:

- recording the MC's intro and outro;
- reviewing the audio and video quality, and checking the length;
- transcribing, then reviewing the transcript;
- translating, one item per language we publish in;
- adding the title card and assembling the final cut;
- publishing to YouTube, scheduled for your slot.

Some of these tick themselves when the matching file lands, so the list moves
without anyone pressing a button.

!!! note "Transcription stays in-house"
    When the edition has it switched on, the portal makes a first draft of the
    transcript itself, and a person on the team reviews it. The draft is made
    with [Whisper](https://github.com/openai/whisper), the open source speech
    recognition model, run through
    [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with the
    `small` model on PyLadiesCon's own worker. Your recording is not sent to
    an outside transcription service, and no third-party account is involved.
    The card says so when this applies to your video, and a transcript made
    this way carries a **machine draft** badge until a person has reviewed it.

## Files from the team

*[Video: Files from the team. Embedded here once it is on YouTube.]*

*Recording: the performer finds the poster, transcript and final cut the team
shared, previews them, and approves the final cut. Practice data.*

The team sends files to you the same way you send yours: through your session
page, not as email attachments or links in a chat. What they share depends on
your session, and may include:

| File | What it is for |
|---|---|
| **Promo material** (square, landscape, vertical, a short video or a gif) | The poster and social cards for your session. Share them! |
| **Transcript**, **Translation** | The text of your video, for you to check, and in the languages we publish in. A transcript made by the portal's own tooling carries a **machine draft** badge until a person has reviewed it. |
| **Final cut** (processed video) | Your video with the title card, intro and outro, as it will go out. |
| **Title card**, **Thumbnail** | The still images used in and around the video. |
| **Other** | Anything else, with a title that says what it is. |

### Where to find them

On your session page, the **Files** tab shows a count of the files waiting for
you. Under **Files from the team** is the **newest version** of each file,
with its title, what kind of file it is, its version and when it was shared.
An older version the team has replaced is not listed, so what you see is
always what the team is working with.

- **Preview** opens the file in the page: a poster shows as an image, a video
  or audio file plays, and a transcript or captions file reads as text. Nothing
  is downloaded until you ask.
- **Download** fetches the file. The link is created when you click it and
  stops working a minute later, so download the file rather than bookmarking
  or forwarding the link; anyone you send it to would find it expired.

### How you hear about them

You do not have to keep checking the page. The portal sends you **one email a
day at most**: the same daily email that reminds you of to-dos coming due. When
the team has shared something new since you were last told, the email has a
section, **The team has shared new files with you**, listing each file by
session, and the subject says how many, for example "2 todos with deadlines
coming up and 3 new files from the team". When there is nothing due and
nothing new, there is no email.

The email lists the files and links to your session page; it does not attach
them or carry download links, for the reason above. Each file is announced
once. A file the team replaces with a new version is announced again, since it
is a new file.

### Approve the final cut

If your session is pre-recorded, your to-dos include **Approve the final
cut**. It shows as **Waiting**, with the note "we are still editing your
video", until the team shares the final cut with you. Then it opens, and the
email about the new file arrives in the same message as the reminder.

Watch the final cut from the **Files** tab. If you are happy for it to go out,
tick **Approve the final cut** on your checklist. If something needs fixing,
leave it unticked and tell our team what and where ("the name card at 0:12
has a typo"), by replying to any email from the portal or on Discord.

## Who can see your files

- Your video and the team's files live in private storage. There is no public
  link to any of them, and the portal hands out only short-lived links, on the
  click, to people allowed to fetch the file.
- Who is allowed: you, for your own video and whatever the team has shared with
  you; the organizers and your liaison, for everything on your session. Other
  speakers cannot see your files, and nothing on the Files tab is public.
- The team's reviewer notes on a file ("audio dips at 4:10") stay with the
  team. What you see is the file, its title and its version.
- Files are kept until someone deletes them, including if a session is
  cancelled, because a cancellation is often undone and a recording is hard to
  get back. If you want your video removed, delete it yourself as above, or
  ask us and we will.
- Your published video goes out the way the guide for your session says: on
  the PyLadies YouTube channel, after the conference, with its transcript.

## If something does not work

| What you see | What it means and what to do |
|---|---|
| No **Files** tab on your session page | Either the edition has not opened file uploads for speakers yet (we email everyone it affects when it does), or your session is still a proposal waiting for an answer. Proposals have no files. |
| No **Upload video** button | Only pre-recorded sessions have one. If yours should be pre-recorded and is not, tell your liaison. |
| "Choose a file first" | Pick the file before choosing Upload. |
| The file is refused when you choose Upload | It is not a video the portal recognises (check the extension), or it is larger than the portal allows. Export it again as MP4, or contact us if it is simply very large. |
| "Upload stopped" | Your connection dropped. Choose the same file again and Upload; it continues from where it stopped. |
| **Length not checked yet**, for a long time | The team's media worker has not got to it. It will. If the card says the length could not be checked, the team looks at it by hand. |
| The length is red | Your video is over the limit for your kind of session. Upload a shorter cut; the newest version is the one that counts. |
| You cannot use the upload at all | Reply to any email from the portal, or write to your liaison, and we will find another way to get your video. |

For anything else, see [Getting help](speakers.md#getting-help).
