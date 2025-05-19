---
title: Contributing
description: Contributing to PyLadiesCon Portal
---

# Contributing Guide

## Where and How to get started

Find an issue in our [repo](https://github.com/pyladies/pyladiescon-portal) to get started. You can also create a new issue or [start a discussion item](https://github.com/pyladies/pyladiescon-portal/discussions) on GitHub.

## Setup

To start working with the code, refer to our [setup guide](https://pyladiescon-portal-docs.netlify.app/developer/setup/).

Ask questions in the **[#portal_dev](https://discord.gg/X6fcufjb)** channel of our Discord comunity.

## Running Tests

Tests are run using [pytest](https://docs.pytest.org/en/latest/).

To run the tests:

```bash
make test
```

## Test coverage

We aim for 100% test coverage. The coverage report is generated after running the tests, and can be viewed in the `htmlcov` directory.

## Code style and linting

Run ``make reformat`` and ``make check`` prior to committing your code.
There is a CI that checks for code style and linting issues.

PRs will not be merged if there is any CI failures.

## Documentation Preview on Pull Requests

A documentation preview is generated for each pull request using Netlify. This allows us to preview
the docs changes before merging the PR.
