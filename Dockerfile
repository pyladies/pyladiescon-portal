FROM python:3.14-bookworm AS base
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir /code

WORKDIR /code

RUN pip --no-cache-dir --disable-pip-version-check install --upgrade pip setuptools wheel

COPY requirements-app.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-app.txt

# ffmpeg brings ffprobe, which the media worker uses to measure videos and
# take thumbnail frames, and pulls the audio out for transcription.
RUN apt-get update && apt-get install -y gettext flite sox ffmpeg

# Machine transcription (design §8.8): with WHISPER_MODEL set, the library
# goes in and the model is downloaded into /opt/whisper in this layer, before
# the code is copied, so a code-only build reuses it and the worker never
# downloads at run time. It defaults to "small" so a platform that cannot pass
# build arguments (cabotage) still ships an image with an engine; compose
# overrides it to empty for the dev images, and an empty value means no
# transcription in the image.
ARG WHISPER_MODEL="small"
COPY requirements-media.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$WHISPER_MODEL" ]; then \
        pip install -r requirements-media.txt && \
        python -c "from faster_whisper import download_model; download_model('$WHISPER_MODEL', '/opt/whisper/$WHISPER_MODEL')"; \
    fi


###############################################################################
#  Build our development container
###############################################################################
FROM base AS dev

ARG USER_ID
ARG GROUP_ID

RUN groupadd -o -g $GROUP_ID -r usergrp
RUN useradd -o -m -u $USER_ID -g $GROUP_ID user
RUN chown user /code

COPY requirements-dev.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-dev.txt

RUN chown -R user /usr/local/lib/python3.14/site-packages

USER user
ENV PATH="${PATH}:/home/user/.local/bin"


###############################################################################
#  Build our production container
###############################################################################
FROM base

RUN  chown -R nobody /usr/local/lib/python3.14/site-packages

COPY . /code/

RUN \
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1] \
    DJANGO_SECRET_KEY=deadbeefcafe \
    DATABASE_URL=postgres://localhost:5432/db \
    DJANGO_SETTINGS_MODULE=portal.settings \
    python manage.py collectstatic --noinput --clear

