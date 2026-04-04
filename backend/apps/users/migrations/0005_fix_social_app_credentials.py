"""
Migration 0004 created SocialApp DB records with client_id='placeholder'.
Now that APP config has been removed from SOCIALACCOUNT_PROVIDERS settings
(to avoid allauth 0.62 MultipleObjectsReturned), the DB records must carry
the real credentials.  This migration reads them from env vars and updates
any existing placeholder records.
"""
from django.conf import settings
from django.db import migrations


def fix_social_app_credentials(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')
    db = schema_editor.connection.alias

    try:
        site = Site.objects.using(db).get(pk=1)
    except Site.DoesNotExist:
        site = Site.objects.using(db).first()
    if not site:
        return

    from decouple import config as env_config

    provider_env = {
        'google': ('GOOGLE_CLIENT_ID',  'GOOGLE_CLIENT_SECRET'),
        'yandex': ('YANDEX_CLIENT_ID',  'YANDEX_CLIENT_SECRET'),
        'vk':     ('VK_CLIENT_ID',      'VK_CLIENT_SECRET'),
    }
    provider_names = {'google': 'Google', 'yandex': 'Yandex', 'vk': 'VK'}

    for provider_id, (id_key, secret_key) in provider_env.items():
        client_id = env_config(id_key, default='')
        secret    = env_config(secret_key, default='')

        if not client_id:
            continue

        app, created = SocialApp.objects.using(db).get_or_create(
            provider=provider_id,
            defaults={'name': provider_names[provider_id], 'client_id': client_id, 'secret': secret},
        )
        if not created:
            updated = False
            if app.client_id != client_id:
                app.client_id = client_id
                updated = True
            if app.secret != secret:
                app.secret = secret
                updated = True
            if updated:
                app.save(update_fields=['client_id', 'secret'])

        if site not in app.sites.using(db).all():
            app.sites.add(site)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_create_google_social_app'),
    ]

    operations = [
        migrations.RunPython(fix_social_app_credentials, noop),
    ]
