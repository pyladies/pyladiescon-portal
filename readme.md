# PyLadiesCon Web Portal

PyLadiesCon online conference management tool.

:moneybag: Support the development of this project by [donating to PyLadiesCon](https://psfmember.org/civicrm/contribute/transact/?reset=1&id=53).

## About PyLadiesCon

✨ [PyLadiesCon](https://conference.pyladies.com) is an online conference for the global [PyLadies](https://pyladies.com) community.
Our conference began in 2023. During our conference, we host 24 hours of online engagement, talks, keynotes, panels, and workshops for our community members.
We strive of inclusivity and accessibility, providing talks in multiple-languages, and we take extra care in subtitling and translating our talks.
Our conference is free to attend, and attendees can optionally donate to our conference.

Being an online, multi-language, multi-timezone conference, we face unique and different challenges from other types of events and conferences.
Our organizers are all volunteers from different part of the world.
We have many communications and coordinations with our team of volunteers ahead of the conference, and less during the conference itself.

## Challenges in managing our online conference

🤕 Our organizing team collaborate with each other to manage our volunteers, our speakers, and our sponsors.
Each team also collaborate with our design and media team to produce promotional assets.
For the last 2 years, we manage a lot of our assets and information using spreadsheets and Google Forms.
However, managing and sharing data with various volunteers using spreadsheets have been challenging, and causing frustrations and confusions among our team of volunteers.

## What we're building: PyLadiesCon Web Portal

💻 This year, we are developing an online web portal for us to manage the behind the scenes work of our conference.
Instead of spreadsheets, we will be accepting volunteer sign ups and sponsorship sign ups through our web portal.
Our team leads will be assigning task and tracking team progress through the web portal.
We also want to build a conference dashboard to provide overview and statistics about our conference.

## PyLadiesCon Team

- Tech lead: [@Mariatta](https://github.com/mariatta)
- GSoC Mentors: [@Mariatta](https://github.com/mariatta), [@cmaureir](https://github.com/cmaureir)
- Conference core organizers: [@mjmolina](https://github.com/mjmolina), [@georgically](https://github.com/georgically), [@DennyPerez18](https://github.com/DennyPerez18), [@Mariatta](https://github.com/mariatta), [@cmaureir](https://github.com/cmaureir)

## Support PyLadiesCon

🫶 Support us by contributing to our project.

We have many contribution opportunities, including code, testing, and documentations. All forms of contributions are welcome and appreciated.

Check the Local Dev Setup section below to learn how to set this up on your local development environment and get started.

- Repo: https://github.com/pyladies/pyladiescon-portal
- Issues: https://github.com/pyladies/pyladiescon-portal/issues
- Project: https://github.com/orgs/pyladies/projects/11
- Milestone with due dates and goals: https://github.com/pyladies/pyladiescon-portal/milestones

[Donate to PyLadiesCon](https://psfmember.org/civicrm/contribute/transact/?reset=1&id=53).
In addition to developing this web portal, we have plans to further improve our conference by hiring more professional services, investing in tools and automations.
Your donations and sponsorship can help make our wishes a reality, so that we can focus on fulfilling the PyLadies mission of helping more women become active leaders
and participants in the Python open source community.


# Local Dev setup

Requirements: Have these installed first before continuing further.

- Docker
- Docker compose
- GNU Make
- GitHub CLI (optional, but recommended) https://cli.github.com/


## Starting the local env

1. Clone the repo. If using GitHub CLI, run:

```
gh repo clone pyladies/pyladiescon-portal
```

2. Start the local environment:

```
make serve
```

3. Open the browser and go to <http://localhost:8000/> to see the app running.

4. Run the tests:

```
make test
```

## Emails in local env

The docker compose development environment includes a
[maildev](https://maildev.github.io/maildev/)
instance for previewing emails locally.

It is accessible at <http://localhost:1080> and will show all emails sent by the application.

## Set up your Account as a Staff user

1. Go to <http://localhost:8000/accounts/login/>
2. Go to the "Sign up" link
3. Fill in the email address, username, and password.
4. Upon signing up, the confirmation email will be available at <http://localhost:1080/>. Enter this code on the sign up form.
5. Your account is now verified.
6. On the terminal, go to Django shell:

```
make manage shell
```
7. Set your account as a staff and superuser:

```
from django.contrib.auth.models import User
user = User.objects.get(username='your_username') #use the username you created above
user.is_staff = True
user.is_superuser = True
user.save()
```

8. You can now access the /admin page.

## Setup pre-commit for identify simple issues and standardize code formatting

Pyladiescon-portal uses a tool called [pre-commit](https://pre-commit.com/) to identify simple issues and standardize code formatting. It does this by installing a git hook that automatically runs a series of code linters prior to finalizing any git commit. To enable pre-commit, run:

```
pre-commit install
```

### Pre-commit automatically runs during the commit

With pre-commit installed as a git hook for verifying commits, the pre-commit hooks configured in `.pre-commit-config.yaml` for Pyladiescon-portal must all pass before the commit is successful. If there are any issues found with the commit, this will cause your commit to fail. Where possible, pre-commit will make the changes needed to correct the problems it has found. 

You can then re-add any files that were modified as a result of the pre-commit checks, and re-commit the change.