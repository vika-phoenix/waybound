import sys
import os
from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bookings'
    verbose_name = 'Bookings'

    def ready(self):
        # Skip management commands that don't need the scheduler
        skip = {'makemigrations', 'migrate', 'collectstatic', 'shell',
                'test', 'createsuperuser', 'showmigrations', 'sqlmigrate'}
        if set(sys.argv) & skip:
            return

        # In dev, Django's autoreloader runs two processes.
        # RUN_MAIN=true is set only in the child (real server) process — avoid double-start.
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return

        # In production (gunicorn), multiple workers each call ready().
        # Only start the scheduler once using an env flag to avoid duplicate job warnings.
        if os.environ.get('SCHEDULER_STARTED') == '1':
            return
        os.environ['SCHEDULER_STARTED'] = '1'

        from .scheduler import start_scheduler
        start_scheduler()
