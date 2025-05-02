FROM python:3.13-bookworm AS base
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir /code

WORKDIR /code

RUN pip --no-cache-dir --disable-pip-version-check install --upgrade pip setuptools wheel

COPY requirements-app.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-app.txt

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

RUN chown -R user /usr/local/lib/python3.13/site-packages

USER user
ENV PATH="${PATH}:/home/user/.local/bin"


###############################################################################
#  Build our production container
###############################################################################
FROM base

RUN  chown -R nobody /usr/local/lib/python3.13/site-packages

COPY . /code/

RUN \
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1] \
    DJANGO_SECRET_KEY=deadbeefcafe \
    DATABASE_URL=postgres://localhost:5432/db \
    DJANGO_SETTINGS_MODULE=portal.settings \
    python manage.py collectstatic --noinput
