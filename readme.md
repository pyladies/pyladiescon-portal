# PyLadiesCon Web Portal

# Local Dev setup

Requirements: Have these installed first before continuing further.

- Python 3.13
- Postgres 16.8
- GitHub CLI (optional, but recommended) https://cli.github.com/
- Direnv (https://direnv.net/)


## Starting the local env

1. Clone the repo. If using GitHub CLI, run:

```
gh repo clone pyladies/pyladiescon-portal
```

2. Set up virtual environments:

```
python3 -m venv .env
source .env/bin/activate
```

3. Install dependencies. Be sure you are in the virtual environment.

```
(.env) python3 -m pip install -r requirements-dev.txt
```

4. Create the postgres db:

```
createdb -U postgres pyladiescon_db_dev
```

### Local dev setup

1. Create an `.envrc` file, add the following to the file (adjust the values):

```
export DEBUG=1
export SECRET_KEY=abc123
export DJANGO_ALLOWED_HOSTS=localhost
export SQL_ENGINE=django.db.backends.postgresql
export SQL_DATABASE=pyladiescon_db_dev
export SQL_USER=postgres
export SQL_PASSWORD=admin
export SQL_HOST=localhost
export SQL_PORT=5432
export DATABASE=postgres
export DJANGO_SETTINGS_MODULE=portal.settings
```

2. Load the environment using direnv:
```
(.env) direnv allow
```

3. Run the migrations:

```
(.env) python manage.py migrate
```

4. Start the local environment:

```
(.env) python manage.py runserver
```

5. Open the browser and go to `http://localhost:8000/` to see the app running.

6. Run the tests:

```
(.env) python manage.py test
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

