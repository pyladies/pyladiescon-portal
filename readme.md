# PyLadiesCon Web Portal

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
(.env) make serve
```

3. Open the browser and go to `http://localhost:8000/` to see the app running.

4. Run the tests:

```
(.env) make test
```

## Set up your Account as a Staff user

1. Go to http://localhost:8000/accounts/login/
2. Go to the "Sign up" link
3. Fill in the email address, username, and password.
4. No email will be sent, everything is done locally.
5. Upon signing up, the terminal will show the verification code. Enter this code on the sign up form.
6. Your account is now verified.
7. On the terminal, go to Django shell:

```
(.env) python manage.py shell
```
8. Set your account as a staff and superuser:

```
from django.contrib.auth.models import User
user = User.objects.get(username='your_username') #use the username you created above
user.is_staff = True
user.is_superuser = True
user.save()
```

9. After that, restart the server. You can now access the /admin page.

