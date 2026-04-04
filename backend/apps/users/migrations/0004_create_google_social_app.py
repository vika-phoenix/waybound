"""
Ensure Google, Yandex and VK social apps exist in the DB.
allauth requires a SocialApp record for each provider when credentials
are stored in settings (APP config). Without a DB record the
/accounts/<provider>/login/ URLs return 404.
"""
from django.db import migrations


def create_social_apps(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')
    db = schema_editor.connection.alias

    try:
        site = Site.objects.using(db).get(pk=1)
    except Site.DoesNotExist:
        site = Site.objects.using(db).first()
    if not site:
        return

    providers = [
        ('google',  'Google'),
        ('yandex',  'Yandex'),
        ('vk',      'VK'),
    ]
    for provider_id, name in providers:
        app, created = SocialApp.objects.using(db).get_or_create(
            provider=provider_id,
            defaults={'name': name, 'client_id': 'placeholder', 'secret': ''},
        )
        # Make sure the site is linked
        if site not in app.sites.using(db).all():
            app.sites.add(site)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_add_experience_years_to_user'),
        ('socialaccount', '0001_initial'),
        ('sites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_social_apps, migrations.RunPython.noop),
    ]
