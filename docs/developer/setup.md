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

2. Clone your fork. If using GitHub CLI, run:

```sh
gh repo clone <personal-account>/pyladiescon-portal
```

    ```
    git clone <personal-account>/pyladiescon-portal.git
    ```

3. Start the local environment:

```sh
make serve
```

4. Open the browser and go to <http://localhost:8000/> to see the app running.

5. Run the tests:

```sh
make test
```

## Without Docker

To run locally _without_ Docker these are the steps.

### Requirements

Have these installed first before continuing further.

- Use Python 3.13+
- You can install [different versions of Python using pyenv](https://github.com/pyenv/pyenv).
- You'll also need PostgreSQL (you can find the instructions here).

### Install dependencies

Create a python environment and activate it:

```sh
python3 -m venv .env
source .env/bin/activate  # or in Windows: .env\Scripts\activate
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

```sh
export SQL_USER=<your-user>  # or on Windows: set SQL_USER=<your-user>
```

For example, Jess username is "jesstemporal", so her command looks like this:

```sh
export SQL_USER=jesstemporal  # or on Windows: set SQL_USER=jesstemporal
```

### Applying Migrations

Now is time to create the database to store all the information:

```sh
python manage.py migrate
```

To run the server:

```sh
python manage.py runserver
```

## Documentation Setup

The documentation is built using [MKDocs](https://www.mkdocs.org/) and markdown.

### Local docs setup

1. Create and activate a virtual environment:

```sh
python3 -m venv venv
source venv/bin/activate
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
