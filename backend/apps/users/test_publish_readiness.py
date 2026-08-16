"""
Finding the guides who cannot publish yet.

Name, bio and photo became requirements after accounts already existed, so
there are guides who will meet them for the first time as a rejection they did
not expect. The admin column exists to find those before they do.

It restates the checks rather than importing them, because a staff screen
should keep working if the tour module changes shape — so this holds the two
copies to each other.
"""
from decimal import Decimal

from django.test import TestCase

from apps.tours.models import Tour
from apps.users.admin import _publish_blockers
from apps.users.models import User


class PublishBlockersTest(TestCase):

    def _guide(self, **over):
        data = dict(email='g@example.com', password='x', role=User.Role.OPERATOR,
                    first_name='Nino', last_name='Beridze',
                    bio='Fifteen years in Svaneti.', avatar='avatars/g.jpg',
                    is_verified=True)
        data.update(over)
        return User.objects.create_user(**data)

    def test_a_complete_guide_is_clear(self):
        self.assertEqual(_publish_blockers(self._guide()), [])

    def test_each_gap_is_named(self):
        self.assertIn('name', _publish_blockers(self._guide(first_name='', last_name='')))
        self.assertIn('bio', _publish_blockers(self._guide(email='b@x.com', bio='')))
        self.assertIn('photo', _publish_blockers(self._guide(email='c@x.com', avatar='')))
        self.assertIn('ID check', _publish_blockers(self._guide(email='d@x.com',
                                                                is_verified=False)))

    def test_a_traveller_is_not_judged_by_guide_requirements(self):
        traveller = User.objects.create_user(email='t@example.com', password='x')
        self.assertEqual(_publish_blockers(traveller), [])

    def test_it_agrees_with_what_actually_blocks_publishing(self):
        """
        The admin restates the rules, so drifting apart would mean the screen
        clears a guide the API then rejects.
        """
        from apps.tours.views import incomplete_tour_fields

        guide = self._guide(first_name='', last_name='', bio='', avatar='')
        tour = Tour.objects.create(operator=guide, title='Ushba', country='Georgia',
                                   destination='Mestia', price_adult=Decimal('500'),
                                   currency='USD', max_group=8)
        blocking = ' '.join(incomplete_tour_fields(tour)).lower()
        shown = _publish_blockers(guide)
        # The two screens word the same requirement differently — the admin is
        # a terse column, the API message is what a guide reads — so match them
        # by what they mean rather than by their wording.
        for admin_label, api_phrase in (('name', 'your name'),
                                        ('bio', 'about you'),
                                        ('photo', 'profile photo')):
            with self.subTest(requirement=admin_label):
                self.assertIn(api_phrase, blocking)
                self.assertIn(admin_label, shown)
