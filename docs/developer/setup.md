---
title: Local Dev Environment Setup
description: Setting up the local development environment for PyLadiesCon Portal
---

# Local Dev setup

You can either folllow the setup with Docker or without Docker, the instructions are listed below.


## With Docker

To run locally Docker these are the steps.

### Requirements

Have these installed first before continuing further.

- Docker
- Docker compose
- GNU Make
- GitHub CLI (optional, but recommended) https://cli.github.com/

### Starting the local env

1. Fork the repo. See the GitHub docs for instructions on how to [Fork a repo](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

2. Clone your fork:

=== "GitHub CLI"

    ```sh
    gh repo clone <personal-account>/pyladiescon-portal
    ```

=== "Git"

    ```sh
    git clone <personal-account>/pyladiescon-portal.git
    ```

3. Start the local environment:

```sh
make serve
```

4. Open the browser and go to <http://localhost:8000/> to see the app running.

5. Set the site domain (see [Configure the site domain](#configure-the-site-domain)):

```sh
make manage set_site_domain localhost:8000
```

6. Run the tests:

```sh
make test
```

## Without Docker

To run locally _without_ Docker these are the steps.

### Requirements

Have these installed first before continuing further.

- Use Python 3.14+
- You can install [different versions of Python using pyenv](https://github.com/pyenv/pyenv).
- You'll also need PostgreSQL (you can find the instructions here).

### Starting the local env

1. Fork the repo. See the GitHub docs for instructions on how to [Fork a repo](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

2. Clone your fork:

=== "GitHub CLI"

    ```sh
    gh repo clone <personal-account>/pyladiescon-portal
    ```

=== "Git"

    ```sh
    git clone <personal-account>/pyladiescon-portal.git
    ```

### Install dependencies

Create a python environment and activate it:

=== "MacOS and Linux"

    ```sh
    python3 -m venv .env
    source .env/bin/activate
    ```

=== "Windows"

    ```
    python3 -m venv .env
    .env\Scripts\activate
    ```

Install dependencies for development:

```sh
pip install -r requirements-dev.txt
```

If you want to run the docs you'll also need some docs dependencies:

```sh
pip install -r requirements-docs.txt
```

### Postgres Setup

To run the application you'll need to have PostgreSQL running on your machine. Follow one of the guides below to install it:

<details><summary>Installation in MacOS</summary>

1. Install PostgreSQL

```sh
brew install postgresql
```

2. Run PostgreSQL

```sh
brew services start postgresql
```
</details>

<details>
<summary>Installation in Windows</summary>

<a href="https://www.postgresql.org/download/windows/">Download the installer from here</a> and follow the screen prompts

</details>

Now export the environment variable below:

=== "MacOS and Linux"

    ```sh
    export SQL_USER=<your-user>
    ```

=== "Windows"

    ```sh
    set SQL_USER=<your-user>
    ```

For example, Jess' username is "jesstemporal", so her command looks like this:

=== "MacOS and Linux"

    ```sh
    export SQL_USER=jesstemporal
    ```

=== "Windows"

    ```sh
    set SQL_USER=jesstemporal
    ```

### Applying Migrations

Now is time to create the database to store all the information:

```sh
python manage.py migrate
```

### Configure the site domain

Links inside emails (account verification, speaker invitations, checklist
reminders) are built from the domain stored in Django's
[sites framework](https://docs.djangoproject.com/en/stable/ref/contrib/sites/),
not from the request. A fresh database has the placeholder `example.com`, so
every emailed link points at the wrong host until you change it. Set it once
after the first `migrate`:

=== "With Docker"

    ```sh
    make manage set_site_domain localhost:8000
    ```

=== "Without Docker"

    ```sh
    python manage.py set_site_domain localhost:8000
    ```

The same value is editable in the admin under **Sites**. With `DEBUG` on,
speaker-portal links use `http://`; everywhere else they use `https://`.

### Run the server

Add the other enviroment variables:

=== "MacOS and Linux"

    ```sh
    export SECRET_KEY=deadbeefcafe
    export DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
    ```

=== "Windows"

    ```sh
    set SECRET_KEY=deadbeefcafe
    set DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
    ```

Then run the server:

```sh
python manage.py runserver
```

## Speaker media uploads (optional)

Performance videos go straight from the browser to a private bucket in
presigned multipart chunks (design §8.8). With no bucket configured the
upload endpoints answer 503 and everything else works, so most local work
needs none of this.

Once a video lands, a worker task measures it with `ffprobe` (the image
installs `ffmpeg`; rebuild it with `make` after pulling this change) on
the `media` Celery queue. The compose worker consumes both queues, so no
extra container is needed locally; production runs a separate
`worker-media` process (deployment guide). Without `ffprobe` the file row
says so and the video is still there. The tests never call the binary
unless they ask to: `tests/speakers/conftest.py` stubs it, and the one
test on a real fixture video (`tests/speakers/fixtures/two-seconds.mp4`)
is skipped when `ffprobe` is not installed.

### Against a DigitalOcean Space

Production uses DigitalOcean Spaces, and a local server can upload to a
Space of its own. Make one for development, separate from the public one
the image fields use, and keep it **private**: the portal never sets an
ACL on what it uploads, and reads it back only through presigned links.

1. In the DigitalOcean console create a Space (for example
   `pyladiescon-media-dev`) in a region such as `nyc3`, and turn *File
   Listing* off. Do not enable the CDN on it.
2. On the Space, add a CORS rule for the browser's direct uploads:
   origin `http://localhost:8000`, methods `PUT` and `GET`, allowed headers
   `*`, exposed header `ETag`.
3. Create a Spaces access key (API, Spaces Keys) scoped to that Space.
4. Give the `web`, `celery` and `beat` services the settings through a
   `compose.override.yml` next to `compose.yml` (ignored by git, so the
   keys stay on your machine):

```yaml
services:
  web:
    environment:
      SPEAKER_MEDIA_BUCKET: pyladiescon-media-dev
      AWS_S3_ENDPOINT_URL: https://nyc3.digitaloceanspaces.com
      AWS_S3_REGION_NAME: nyc3
      AWS_ACCESS_KEY_ID: <your Spaces key>
      AWS_SECRET_ACCESS_KEY: <your Spaces secret>
  celery:
    environment:
      SPEAKER_MEDIA_BUCKET: pyladiescon-media-dev
      AWS_S3_ENDPOINT_URL: https://nyc3.digitaloceanspaces.com
      AWS_S3_REGION_NAME: nyc3
      AWS_ACCESS_KEY_ID: <your Spaces key>
      AWS_SECRET_ACCESS_KEY: <your Spaces secret>
```

   Then `docker compose up -d --force-recreate web celery beat`. Leave
   `USE_SPACES` alone: it switches the image storage, which is a separate
   matter.

Until the upload panel (task 5.2) exists there is no browser path, so check
the wiring from a shell, which plays the browser's part with boto3:

```bash
docker compose exec web python manage.py shell -c "
from django.contrib.auth.models import User
from speakers.media import MediaBucket, start_upload, complete_upload
from speakers.models import Session
session = Session.objects.filter(conference__is_active=True).first()
user = User.objects.get(username='admin_user')
upload = start_upload(session=session, kind='RAW_VIDEO', language='', filename='check.bin', size_bytes=3, content_type='application/octet-stream', user=user)
bucket = MediaBucket.from_settings()
part = bucket.client.upload_part(Bucket=bucket.bucket, Key=upload.storage_key, UploadId=upload.upload_id, PartNumber=1, Body=b'ok!')
asset = complete_upload(upload, [{'number': 1, 'etag': part['ETag']}])
print(asset, asset.size_bytes, asset.download_url())
"
```

The printed link is presigned and opens the object for an hour; the same
address without the signature is refused, which is the private Space doing
its job.

### Against a MinIO container (no account needed)

The presigned URLs sign the host they are for, so the portal and the
browser have to reach the bucket at the same address. With the portal in
Docker that means running MinIO inside the `web` container's network
namespace, so both see it as `localhost:9000`. This `compose.override.yml`
does it:

```yaml
services:
  web:
    ports:
      - "9000:9000"
    environment:
      SPEAKER_MEDIA_BUCKET: speaker-media
      AWS_S3_ENDPOINT_URL: http://localhost:9000
      AWS_S3_REGION_NAME: us-east-1
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
  celery:
    environment:
      SPEAKER_MEDIA_BUCKET: speaker-media
      AWS_S3_ENDPOINT_URL: http://web:9000
      AWS_S3_REGION_NAME: us-east-1
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
  minio:
    image: minio/minio
    command: server /data
    network_mode: "service:web"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - miniodata:/data
volumes:
  miniodata:
```

Then `docker compose up -d --force-recreate web celery minio` and create
the bucket once:

```bash
docker compose exec web python -c "
import boto3, os
boto3.client('s3', endpoint_url=os.environ['AWS_S3_ENDPOINT_URL'],
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin',
    region_name='us-east-1').create_bucket(Bucket='speaker-media')"
```

MinIO answers browser uploads from any origin and exposes the `ETag`
header, so no CORS rule is needed. Log in as a performer (the sample data's
`volunteer2` is on the PyJam session) and upload from the session page;
leaving the page mid-upload and choosing the same file again should
continue from the parts that already landed.

`SPEAKER_MEDIA_PART_SIZE`, `SPEAKER_MEDIA_MAX_BYTES`, `SPEAKER_MEDIA_URL_TTL`
(how long a presigned link lives, 3600 seconds by default) and
`SPEAKER_MEDIA_UPLOAD_TTL_HOURS` have sensible defaults in `portal/settings.py`.

## Generate Sample Data (Optional)

For local development and testing, you can generate sample data to populate your database with realistic test content. This command creates:

- **9 Users**: 1 admin, 1 staff member, 5 volunteers, and 2 sponsor contacts
- **8 PyLadies Chapters**: Chapters from different regions globally (San Francisco, NYC, London, Berlin, Tokyo, São Paulo, Lagos, Sydney)
- **7 Volunteer Roles**: Frontend Dev, Backend Dev, Content Writer, Social Media Manager, Designer, Reviewer, Event Coordinator
- **6 Teams**: Website, Social Media, Content, Design, Program Committee, Sponsorship
- **5 Volunteer Profiles**: With various application statuses (approved, pending, waitlisted, rejected)
- **5 Sponsorship Tiers**: Ranging from $2,500 to $25,000
- **5 Sponsorship Profiles**: With different progress statuses
- **5 Individual Donations**: Random amounts between $5 and $300

**Important**: This command only works when `DEBUG=True` in your settings to prevent accidental use in production environments.

=== "With Docker"

    ```sh
    make manage generate_sample_data
    ```

=== "Without Docker"

    ```sh
    python manage.py generate_sample_data
    ```

All generated users have the password: `password123`.

The command is idempotent, meaning you can run it multiple times without creating duplicate data.

### Speaker portal sample data

A second command fills the **active edition** with speaker-portal data so
every screen of the speaker module has something to show. It creates:

- **Edition setup**: switches the speaker module on, sets the conference dates
  when they are empty, seeds the default checklist templates, publishes the
  speaker, workshop and keynote guides and leaves a performer guide as a draft
- **4 Portal users**: 1 staff organizer (`organizer_lena`, the liaison for two
  presenters), 2 approved volunteers on teams (`vol_maya` on Design Team,
  `vol_kim` on Media Team), 1 pending volunteer (`vol_pending`)
- **7 Sessions**: a workshop and a keynote (scheduled on the first conference
  day), a panel and a pre-recorded PyJam performance (confirmed), a talk
  (draft), plus the opening (scheduled) and a coffee break
- **6 Presenters**, one per invitation state:
    - `ada@example.com`: accepted and onboarded workshop presenter, with
      checklist items that are done, skipped, overdue and due soon
    - `grace@example.com`: onboarded keynote presenter, second presenter on
      the workshop and panel moderator, so she gets both the keynote and the
      workshop guides
    - `dex@example.com`: invited panelist who has not accepted yet
    - `maria@example.com`: onboarded PyJam performer whose uploaded video is
      over the length limit, which blocks the video-length item
    - `sam@example.com`: talk presenter who has not been invited yet
    - `nina@example.com`: accepted host of the opening who has not been
      through the welcome page yet, so signing in as her shows that flow
- **Action items with deadlines**: one owned by Design Team, one assigned to
  a volunteer and overdue, one completed by a volunteer so the presenter can
  see who did it, and ad hoc items added by the organizer
- **Proposals**, with the edition taking them, one in each state:
    - `vol_rosa`: an approved volunteer who has also proposed a talk, still
      waiting for an answer, which is what "the same account does both"
      looks like
    - `prop_tess`: nothing but a portal account, her workshop approved, so
      she is on the program with a checklist
    - `prop_iris`: one turned down (organizers can still approve it later)
      and one she took back, which she can edit and send again

**Important**: like `generate_sample_data`, this only works when
`DEBUG=True`. It is idempotent: rerunning it updates the data in place. Run
it after [configuring the site domain](#configure-the-site-domain) so the
invitation and notification emails it sends link to `localhost:8000`.

=== "With Docker"

    ```sh
    make manage generate_speaker_sample_data
    ```

=== "Without Docker"

    ```sh
    python manage.py generate_speaker_sample_data
    ```

Pass `--conference <year or slug>` to target an edition other than the active
one.

**Signing in as each persona:**

- Organizer and volunteer accounts use the password `password123`. Sign in
  as `vol_maya` and open **My volunteering tasks** under **My volunteering**
  to see the items assigned to her and to Design Team.
- Presenter accounts were created through the invitation flow and have no
  password yet. Use **Send me a sign-in code** on the login page with the
  presenter's email address; the code arrives in
  [maildev](howto.md) at <http://localhost:1080> (Docker) or in the server terminal. Once signed in, the
  speaker dashboard offers to set a password.
- The organizer side of the speaker portal lives under **Organize →
  Speakers**; the speaker side is the **Speaking** entry in the top menu.
- Proposer accounts (`prop_tess`, `prop_iris`, `vol_rosa`) use
  `password123` as well. Their proposals are under **My proposals**;
  the organizers' queue is **Organize → Speakers → Proposals**, and each
  proposed session can also be answered from the session page itself.

## Documentation Setup

The documentation is built using [MKDocs](https://www.mkdocs.org/) and markdown.

### Local docs setup

1. Create and activate a virtual environment:

=== "MacOS and Linux"

    ```sh
    python3 -m venv venv
    source .env/bin/activate
    ```

=== "Windows"

    ```
    python3 -m venv venv
    .env\Scripts\activate
    ```

2. Install docs requirements:

```sh
pip install -r requirements-docs.txt
```

3. Run the docs server:

```sh
mkdocs serve -a localhost:8888
```

4. Open the browser and go to <http://localhost:8888/> to see the docs running.

### Docs Troubleshooting

### Cairo library was not found

If you see the error `Cairo library was not found`, try the following instructions:

1. [MKDocs material image processing Docs](https://squidfunk.github.io/mkdocs-material/plugins/requirements/image-processing/?h=cairo#troubleshooting).

2. Check if the `Cairo libraries` are listed in ```/opt/homebrew/lib``` folder. If not, follow the instructions [on this page](https://github.com/squidfunk/mkdocs-material/issues/5121).
