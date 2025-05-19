---
title: Local Dev Environment Setup
description: Setting up the local development environment for PyLadiesCon Portal
---

# Local Dev setup

Requirements: Have these installed first before continuing further.

- Docker
- Docker compose
- GNU Make
- GitHub CLI (optional, but recommended) https://cli.github.com/


### Starting the local env

1. Fork the repo. See the GitHub docs for instructions on how to [Fork a repo](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

2. Clone your fork. If using GitHub CLI, run:

    ```
    gh repo clone <personal-account>/pyladiescon-portal
    ```

3. Start the local environment:

    ```
    make serve
    ```

4. Open the browser and go to <http://localhost:8000/> to see the app running.

5. Run the tests:

    ```
    make test
    ```

## Documentation Setup

The documentation is built using [MKDocs](https://www.mkdocs.org/) and markdown.

### Local docs setup

1. Create and activate a virtual environment:

    ```
    python3 -m venv venv
    ```
    
    ```
    source venv/bin/activate
    ```

2. Install docs requirements:

    ```
    pip install -r requirements-docs.txt
    ```

3. Run the docs server:

    ```
    mkdocs serve -a localhost:8888
    ```

4. Open the browser and go to <http://localhost:8888/> to see the docs running.

### Docs Troubleshooting

### Cairo library was not found

If you see the error `Cairo library was not found`, follow the instructions on [how to resolve it](https://squidfunk.github.io/mkdocs-material/plugins/requirements/image-processing/?h=cairo#troubleshooting).
