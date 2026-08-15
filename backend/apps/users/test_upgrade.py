"""
The traveller -> guide upgrade.

Two doors lead to a guide account and they used to lead to different places.
Signing up as a guide meant a long form and a tick on the Terms for Travel
Experts; upgrading meant one button, no questions, no agreement, and a landing
straight on the tour builder. These tests hold the two doors together.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User


class UpgradeToOperatorTests(TestCase):
    def setUp(self):
        self.url = reverse('upgrade-to-operator')
        self.user = User.objects.create_user(
            email='traveller@example.com', password='pw-for-testing-1',
            first_name='Nino', role=User.Role.TOURIST,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, **over):
        data = {'country': 'Georgia', 'phone': '+995 555 100 200',
                'bio': 'Ten years guiding in Svaneti.', 'accept_terms': True}
        data.update(over)
        return data

    def test_upgrade_records_the_terms_acceptance(self):
        res = self.client.post(self.url, self._payload(), format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.OPERATOR)
        self.assertIsNotNone(
            self.user.guide_terms_accepted_at,
            'a guide who agreed to the terms must leave a record of it')

    def test_upgrade_without_accepting_the_terms_is_refused(self):
        res = self.client.post(self.url, self._payload(accept_terms=False),
                               format='json')
        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.TOURIST,
                         'the account must not change when the terms are declined')
        self.assertIsNone(self.user.guide_terms_accepted_at)

    def test_upgrade_omitting_accept_terms_entirely_is_refused(self):
        """The old frontend posted {} — that must no longer be enough."""
        res = self.client.post(self.url, {}, format='json')
        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.TOURIST)

    def test_details_typed_into_the_form_overwrite_what_we_held(self):
        """
        The form is prefilled from the traveller profile, so a changed value is
        a correction. Filling blanks only would silently discard it.
        """
        self.user.country = 'Russia'
        self.user.phone = '+7 900 000 0000'
        self.user.bio = 'I like hiking.'
        self.user.save()

        self.client.post(self.url, self._payload(), format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.country, 'Georgia')
        self.assertEqual(self.user.phone, '+995 555 100 200')
        self.assertEqual(self.user.bio, 'Ten years guiding in Svaneti.')

    def test_company_name_is_folded_into_the_bio(self):
        self.client.post(self.url, self._payload(company_name='Svaneti Treks'),
                         format='json')
        self.user.refresh_from_db()
        self.assertIn('Svaneti Treks', self.user.bio)
        self.assertIn('Ten years guiding in Svaneti.', self.user.bio)

    def test_upgrade_does_not_grant_verification(self):
        self.client.post(self.url, self._payload(), format='json')
        self.user.refresh_from_db()
        self.assertFalse(
            self.user.is_verified,
            'an upgrade must not skip the ID check a fresh guide signup faces')

    def test_terms_timestamp_is_readable_on_me(self):
        self.client.post(self.url, self._payload(), format='json')
        res = self.client.get(reverse('me'))
        self.assertIsNotNone(res.data.get('guide_terms_accepted_at'))


class OperatorRegistrationTermsTests(TestCase):
    """The signup form has always shown the terms; now the server hears about it."""

    def setUp(self):
        self.url = reverse('register-operator')
        self.client = APIClient()

    def _payload(self, **over):
        data = {
            'email': 'guide@example.com',
            'password': 'pw-for-testing-1', 'password2': 'pw-for-testing-1',
            'first_name': 'Sandro', 'last_name': 'Beridze',
            'phone': '+995 555 111 222', 'country': 'Georgia',
            'bio': 'Mountain guide.', 'accept_terms': True,
        }
        data.update(over)
        return data

    def test_registration_stamps_the_acceptance(self):
        res = self.client.post(self.url, self._payload(), format='json')
        self.assertIn(res.status_code, (200, 201), res.data)
        user = User.objects.get(email='guide@example.com')
        self.assertEqual(user.role, User.Role.OPERATOR)
        self.assertIsNotNone(user.guide_terms_accepted_at)

    def test_registration_without_the_tick_is_refused(self):
        res = self.client.post(self.url, self._payload(accept_terms=False),
                               format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email='guide@example.com').exists())

    def test_registration_omitting_the_field_is_refused(self):
        payload = self._payload()
        payload.pop('accept_terms')
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email='guide@example.com').exists())


class UpgradeNameFieldsTest(TestCase):
    """
    The upgrade runs through the guide signup wizard, which asks for a name.
    Dropping it on the way through would let a guide correct their name on a
    form that silently ignored the correction.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='n@example.com', password='pw-for-testing-1',
            first_name='Nino', last_name='K', role=User.Role.TOURIST)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_name_changes_are_kept(self):
        self.client.post(reverse('upgrade-to-operator'), {
            'first_name': 'Nino', 'last_name': 'Kvaratskhelia',
            'country': 'Georgia', 'phone': '+995 555 1',
            'bio': 'Guide.', 'accept_terms': True,
        }, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, 'Kvaratskhelia')

    def test_a_blank_name_does_not_wipe_the_existing_one(self):
        self.client.post(reverse('upgrade-to-operator'), {
            'first_name': '', 'last_name': '',
            'country': 'Georgia', 'accept_terms': True,
        }, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Nino')
        self.assertEqual(self.user.last_name, 'K')

    def test_years_of_experience_is_kept(self):
        """The tour page has a line for it; the form used to drop the answer."""
        self.client.post(reverse('upgrade-to-operator'), {
            'country': 'Georgia', 'experience_years': '5-10 years',
            'accept_terms': True,
        }, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.experience_years, '5-10 years')


class ApplicationAnswersTest(TestCase):
    """
    Six questions the signup form has always asked and always discarded.

    They are application answers, not live profile truth: a tour carries its own
    categories and max_group, so treating tour_types and typical_group_size as
    current fact would put two contradictory answers on the record.
    """

    ANSWERS = {
        'languages': 'English, Russian, Georgian',
        'certifications': 'UIAA Mountain Guide, Wilderness First Aid',
        'tour_types': ['Mountain / Trekking', 'Photography'],
        'typical_group_size': '5-8 (small group)',
        'profile_link': 'https://tripadvisor.com/x',
        'referral_source': 'Instagram',
    }

    def setUp(self):
        self.client = APIClient()

    def test_registration_keeps_them(self):
        payload = {
            'email': 'sandro@example.com',
            'password': 'pw-for-testing-1', 'password2': 'pw-for-testing-1',
            'first_name': 'Sandro', 'country': 'Georgia',
            'experience_years': '5-10 years', 'accept_terms': True,
            **self.ANSWERS,
        }
        res = self.client.post(reverse('register-operator'), payload, format='json')
        self.assertIn(res.status_code, (200, 201), res.data)
        u = User.objects.get(email='sandro@example.com')
        for field, expected in self.ANSWERS.items():
            self.assertEqual(getattr(u, field), expected, field)

    def test_upgrading_keeps_them_too(self):
        """Both doors, or an upgraded guide is a thinner record than a new one."""
        user = User.objects.create_user(email='t@example.com', password='pw-for-testing-1',
                                        role=User.Role.TOURIST)
        self.client.force_authenticate(user)
        self.client.post(reverse('upgrade-to-operator'),
                         {'accept_terms': True, **self.ANSWERS}, format='json')
        user.refresh_from_db()
        for field, expected in self.ANSWERS.items():
            self.assertEqual(getattr(user, field), expected, field)

    def test_they_are_readable_on_me(self):
        user = User.objects.create_user(email='g@example.com', password='pw-for-testing-1',
                                        role=User.Role.OPERATOR, **self.ANSWERS)
        self.client.force_authenticate(user)
        res = self.client.get(reverse('me'))
        self.assertEqual(res.data['certifications'], self.ANSWERS['certifications'])
        self.assertEqual(res.data['tour_types'], self.ANSWERS['tour_types'])

    def test_referral_source_cannot_be_edited_afterwards(self):
        """A one-time attribution answer. Nobody has a reason to revise it."""
        user = User.objects.create_user(email='g@example.com', password='pw-for-testing-1',
                                        role=User.Role.OPERATOR, referral_source='Instagram')
        self.client.force_authenticate(user)
        self.client.patch(reverse('me'), {'referral_source': 'Google'}, format='json')
        user.refresh_from_db()
        self.assertEqual(user.referral_source, 'Instagram')

    def test_certifications_stay_a_claim_not_a_verification(self):
        user = User.objects.create_user(email='g@example.com', password='pw-for-testing-1',
                                        role=User.Role.TOURIST)
        self.client.force_authenticate(user)
        self.client.post(reverse('upgrade-to-operator'),
                         {'accept_terms': True, **self.ANSWERS}, format='json')
        user.refresh_from_db()
        self.assertFalse(user.is_verified,
                         'claiming a certification must not verify the account')
