---
title: Dev Howto
description: How to docs
---

# Developer Howtos

## Viewing logs

To view the logs when running the app locally, run:

```
docker-compose logs -f
```

## Creating Migration Files

With docker:

```
make manage makemigrations
```

Without Docker

```
python manage.py makemigrations
```

## Running Migrations

With docker:

```
make manage migrate
```

Without Docker

```
python manage.py migrate
```

## Emails in local env

When you sign up you'll receive an email with a code to verify your account. In Development those emails don't leave your machine so here's the steps to get the code.

### With Docker

The docker compose development environment includes a
[maildev](https://maildev.github.io/maildev/)
instance for previewing emails locally.

It is accessible at <http://localhost:1080> and will show all emails sent by the application.

### Without Docker

Check your terminal, the email will be printed out for you.

## Set up your Account as a Staff user

1. Go to <http://localhost:8000/accounts/login/>
2. Go to the "Sign up" link
3. Fill in the email address, username, and password.
4. Upon signing up, the confirmation email will be available either at <http://localhost:1080/> (if you are running with Docker) or printed on the terminal (if you are running without Docker). Enter this code on the sign up form.
5. Your account is now verified.
6. On the terminal, go to Django shell:

With Docker:

```
make manage shell
```

Without Docker

```
python manage.py shell
```

7. Set your account as a staff and superuser:

```python
from django.contrib.auth.models import User
user = User.objects.get(username='your_username')  # use the username you created above
user.is_staff = True
user.is_superuser = True
user.save()
```

Then exit the console and re-run the server.

8. You can now access the `/admin` page at <http://localhost:8000/admin>.
