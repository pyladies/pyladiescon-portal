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

## Add transalations and new languages

To create translations/localization we use the Django itself. You can create translations both with Docker and without Docker.

### Translating content

Translation files live inside the `locale/` folder.

For each language there's a subfolder for example `pt_BR` for Portuguese from Brazil.

In each language folder there are two files:

1. `.mo`: file with the compiled translation
2. `.po`: file containing the strings to be translated - this is the file you'll edit to translate the words.

To update the translation for your preferred language:

1. Follow the [development setup guide](https://pyladiescon-portal-docs.netlify.app/developer/setup).
1. Then open the `.po` file for the language you want to translate and find the phrase you want to translate.

For example, in the file `locale/pt_BR/LC_MESSAGES/django.po` there's the following phrase:

```
#: templates/portal/index.html:21
msgid ""
"Sign up to volunteer with us! Fill in your Volunteer profile and we'll get "
"you set up."
msgstr ""
```

To show it in Portuguese you add the translation into the `msgstr` like this:

```
#: templates/portal/index.html:21
msgid ""
"Sign up to volunteer with us! Fill in your Volunteer profile and we'll get "
"you set up."
msgstr "Inscreva-se para ser voluntária conosco! Preencha seu perfil de Voluntária e nós vamos te cadastrar."
```

### Creating new languages translation files

To create new translations files for different languages you must:

1. Update the `LANGUAGE` variable in `portal/settings.py`

```python
# ...
LANGUAGES = (
    ("pt-br", "Português"),
    ("en-us", "English"),
)
```

2. Then you should run the `makemessages` command:
    1. With Docker:
        ```
        make create_translations LANG=<locale-code>
        ```

        For example for Brazilian Portuguese:

        ```
        make create_translations LANG=pt_BR
        ```

    2. Without Docker:
        ```
        python manage.py makemessages -l <locale-code>
        ```

        For example for Brazilian Portuguese:

        ```
        python manage.py makemessages -l pt_BR
        ```

Note that for the creation of new languages we use ISO/IEC 15897 for formatting the language tag.

3. Translate a couple of messages in the generated `.po` file;

4. Then complile the translations:
    1. With Docker:
    ```
    make compile_translations
    ```

    2. Without Docker:
    ```
    python manage.py compilemessages
    ```


Run your server if it isn't running yet and you'll should see the new language in the language selector.


### Missing translation strings

**What if you don't see a phrase to translate in the .po file?**

You probaly need to find that phrase in the HTML files inside the `templates` folder and add a tag `translate` into it like so:

```html
<p>
  {% translate "Sign up %}
</p>
```

Then run the creation command again.
