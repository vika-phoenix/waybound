"""
management command: create_staff_roles
--------------------------------------
Creates (or updates) the three predefined staff Groups and their permissions.
Run after every deploy:

    python manage.py create_staff_roles

Roles
-----
Bookings Manager
    - View + change bookings and enquiry messages
    - View tours (read-only — can see which tour a booking is for)
    - View users (read-only — can see who booked)

Content Reviewer
    - View + change + delete tours, departure dates, and all tour inlines
    - View + change reviews (approve / reject)
    - View bookings (read-only — context only)

Support Staff
    - View-only across bookings, tours, users, reviews
    - Change (reply to) enquiry messages
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


def _perms(*codenames):
    """Return a list of Permission objects matching the given codenames."""
    return list(Permission.objects.filter(codename__in=codenames))


class Command(BaseCommand):
    help = 'Create or update predefined staff roles (Groups + Permissions).'

    def handle(self, *args, **options):
        self._create_bookings_manager()
        self._create_content_reviewer()
        self._create_support_staff()
        self.stdout.write(self.style.SUCCESS('Staff roles created / updated successfully.'))

    # ── Role definitions ──────────────────────────────────────────────────

    def _create_bookings_manager(self):
        group, _ = Group.objects.get_or_create(name='Bookings Manager')
        perms = _perms(
            # Bookings
            'view_booking', 'change_booking',
            # Enquiry messages
            'view_enquirymessage', 'change_enquirymessage',
            # Tours — view only (context for bookings)
            'view_tour', 'view_departuredate',
            # Users — view only (see who booked)
            'view_user',
        )
        group.permissions.set(perms)
        self.stdout.write(f'  [OK] Bookings Manager  ({len(perms)} permissions)')

    def _create_content_reviewer(self):
        group, _ = Group.objects.get_or_create(name='Content Reviewer')
        perms = _perms(
            # Tours — full CRUD on content
            'view_tour', 'change_tour', 'delete_tour',
            'view_departuredate', 'change_departuredate', 'add_departuredate', 'delete_departuredate',
            'view_dayitinerary', 'change_dayitinerary', 'add_dayitinerary', 'delete_dayitinerary',
            'view_stayblock', 'change_stayblock', 'add_stayblock', 'delete_stayblock',
            'view_cancelperiod', 'change_cancelperiod', 'add_cancelperiod', 'delete_cancelperiod',
            'view_tourphoto', 'change_tourphoto', 'add_tourphoto', 'delete_tourphoto',
            'view_tourfaq', 'change_tourfaq', 'add_tourfaq', 'delete_tourfaq',
            # Reviews — approve / reject
            'view_tourreview', 'change_tourreview',
            # Bookings — read-only context
            'view_booking',
        )
        group.permissions.set(perms)
        self.stdout.write(f'  [OK] Content Reviewer  ({len(perms)} permissions)')

    def _create_support_staff(self):
        group, _ = Group.objects.get_or_create(name='Support Staff')
        perms = _perms(
            # Bookings — view only
            'view_booking',
            # Enquiries — view + reply
            'view_enquirymessage', 'change_enquirymessage',
            # Tours — view only
            'view_tour', 'view_departuredate',
            # Users — view only
            'view_user',
            # Reviews — view only
            'view_tourreview',
        )
        group.permissions.set(perms)
        self.stdout.write(f'  [OK] Support Staff     ({len(perms)} permissions)')
