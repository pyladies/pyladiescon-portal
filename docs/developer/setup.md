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

5. Run the tests:

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
