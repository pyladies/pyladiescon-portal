release: python manage.py createcachetable && python manage.py migrate
web: gunicorn -c config/gunicorn.conf.py portal.wsgi:application --log-file -
worker: celery -A portal worker --loglevel=info
