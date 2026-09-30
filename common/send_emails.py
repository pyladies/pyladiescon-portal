"""The one door every email the portal sends goes through, and its record.

``send_email`` renders a Markdown template, delivers it, and leaves one
``SentEmail`` row saying what went where (design §13.1, task 2.23). The
record is written here rather than in each app so a person's trail is
whole: a volunteer's or a sponsor contact's mail is recorded by the same
line as a speaker's.
"""

import re

from allauth.account.models import EmailAddress

from .markdown_emails import deliver_markdown_email, render_markdown_email
from .models import SentEmail, SentEmailStatus

# What replaces a secret in the stored body. The invitation's accept link
# signs its reader in as the presenter, so the record must say it was there
# without being able to use it.
WITHHELD = "[link withheld: it signs the reader in]"

# Shapes of credential that are never stored, whatever the sender passed in
# ``secrets``: a worker still running yesterday's code, or a new caller that
# did not know, is not a reason for a live sign-in link to reach the trail.
# Apps register theirs at startup (``speakers.apps``), because this module
# imports none of them.
CREDENTIAL_PATTERNS = []


def register_credential_pattern(regex):
    """Withhold every match of ``regex`` from stored bodies, from now on."""
    if regex not in (pattern.pattern for pattern in CREDENTIAL_PATTERNS):
        CREDENTIAL_PATTERNS.append(re.compile(regex))


def withhold(text, pattern):
    """``text`` with every match of ``pattern`` (compiled) replaced.

    A Markdown link or autolink built around the match goes with it, title
    and all, so the reader sees the sentence it was, not a link to the
    placeholder.
    """
    inner = f"(?:{pattern.pattern})"
    text = re.sub(
        r"\[([^\]]*)\]\(<?" + inner + r'>?(?:\s+"[^"]*")?\)',
        lambda match: f"{match.group(1)} {WITHHELD}",
        text,
    )
    text = re.sub("<" + inner + ">", WITHHELD, text)
    return pattern.sub(WITHHELD, text)


def withhold_credentials(text):
    """``text`` with every registered credential shape replaced."""
    for pattern in CREDENTIAL_PATTERNS:
        text = withhold(text, pattern)
    return text


# Context keys whose ids say what an email was about. They go in the digest
# whether or not the email was sent to them: the organizers' copy of a
# proposal is about the proposer without being theirs.
DIGEST_KEYS = ("presenter", "session", "invitation", "proposal", "item", "profile")


def send_email(
    subject,
    recipient_list,
    *,
    markdown_template,
    context=None,
    conference=None,
    user=None,
    presenter=None,
    session=None,
    secrets=(),
    reply_to=None,
):
    """Send an email from a Markdown template and record it.

    Callers pass what they know about whom it is for through ``user``,
    ``presenter``, ``session`` and ``conference``; what they leave out is
    read from the context where the context makes it certain (see
    ``describe``), so an unchanged caller still leaves a record, just a
    thinner one. Strings in ``secrets`` (an accept link that doubles as a
    sign-in) go out in the email and are replaced by ``WITHHELD`` in the
    stored body, because the trail is read by people who are not the
    recipient. A send that raises leaves a ``FAILED`` record with the
    error and no body, then raises on: the caller decides what a failed
    send means for its own work.

    Args:
        subject: Email subject line
        recipient_list: List of recipient email addresses
        markdown_template: Path to Markdown template (required)
        context: Template context dictionary
        reply_to: Addresses replies go to, instead of ``DEFAULT_FROM_EMAIL``;
            never a recipient, so never a copy. The caller supplies it, so
            ``common`` imports nothing from the apps.
    """
    context = context or {}
    markdown_content, html_content, text_content = render_markdown_email(
        markdown_template, context
    )
    record = describe(
        subject,
        recipient_list,
        markdown_template,
        context,
        conference=conference,
        user=user,
        presenter=presenter,
        session=session,
    )
    try:
        deliver_markdown_email(
            subject, recipient_list, html_content, text_content, reply_to=reply_to
        )
    except Exception as exc:
        record.status = SentEmailStatus.FAILED
        record.error = f"{type(exc).__name__}: {exc}"[:2000]
        record.save()
        raise
    for secret in secrets:
        if secret:
            markdown_content = withhold(markdown_content, re.compile(re.escape(secret)))
    record.body_md = withhold_credentials(markdown_content)
    record.save()
    return record


def describe(
    subject,
    recipient_list,
    markdown_template,
    context,
    *,
    conference=None,
    user=None,
    presenter=None,
    session=None,
):
    """An unsaved record of the send: who it went to, and what it was about.

    Ownership is read from the context only where the address proves it: a
    ``presenter`` or ``user`` in the context is the recipient when the email
    went to exactly their address, and nobody's otherwise, because the
    organizers' notice about a proposal carries the proposer in its context
    and must never show up in the proposer's own trail. Failing that, an
    address that allauth has verified as exactly one active account's is
    that account's: an assignee's digest carries items in its context, not
    the assignee. The edition and the session are about the email, not its
    reader, so they are taken as found.
    """
    recipients = [address for address in recipient_list if address]
    sole = recipients[0].strip().lower() if len(recipients) == 1 else None

    def is_recipient(candidate):
        address = getattr(candidate, "email", "") or ""
        return sole is not None and address.strip().lower() == sole

    if presenter is None:
        found = _model(context.get("presenter"), "speakers.Presenter")
        if is_recipient(found):
            presenter = found
    if user is None:
        found = _model(context.get("user"), "auth.User")
        if is_recipient(found):
            user = found
    if user is None:
        profile = context.get("profile")
        found = _model(getattr(profile, "user", None), "auth.User")
        if is_recipient(found):
            user = found
    if user is None and sole is not None:
        user = _verified_owner(sole)
    if session is None:
        session = _model(context.get("session"), "speakers.Session")
    if conference is None:
        conference = _model(context.get("conference"), "portal.Conference")
    if conference is None:
        for about in (session, presenter, context.get("profile")):
            conference = _model(getattr(about, "conference", None), "portal.Conference")
            if conference is not None:
                break

    digest = {}
    for key in DIGEST_KEYS:
        pk = getattr(context.get(key), "pk", None)
        if pk is not None:
            digest[key] = pk

    return SentEmail(
        conference=conference,
        user=user,
        presenter=presenter,
        session=session,
        to=", ".join(recipients),
        subject=subject[:500],
        template=markdown_template,
        context_digest=digest,
    )


def _verified_owner(address):
    """The one active account allauth has verified ``address`` for, or None.

    The presenter row's address is never enough (an organizer types it in
    before anyone has proven it), but a verified allauth address is proof.
    Two accounts verified for the same address is nobody's.
    """
    owners = list(
        EmailAddress.objects.filter(
            email__iexact=address, verified=True, user__is_active=True
        ).select_related("user")[:2]
    )
    return owners[0].user if len(owners) == 1 else None


def _model(value, label):
    """``value`` when it is a saved instance of the model ``label``, else None.

    Checked by label rather than by import so this module, which every app
    imports, imports none of them.
    """
    meta = getattr(value, "_meta", None)
    if meta is None or meta.label != label or value.pk is None:
        return None
    return value
