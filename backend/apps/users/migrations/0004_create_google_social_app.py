"""
Ensure Google, Yandex and VK social apps exist in the DB with real credentials.
Reads client_id/secret from SOCIALACCOUNT_PROVIDERS settings (which reads
from env vars) so the DB record matches what the provider actually uses.
Updates existing records so credential changes in env vars are reflected.
"""
from django.conf import settings
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

    providers_config = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {})

    providers = [
        ('google', 'Google'),
        ('yandex', 'Yandex'),
        ('vk',     'VK'),
    ]
    for provider_id, name in providers:
        app_cfg    = providers_config.get(provider_id, {}).get('APP', {})
        client_id  = app_cfg.get('client_id') or ''
        secret     = app_cfg.get('secret') or ''

        # Skip creating a DB record if we have no real credentials — allauth
        # will use the settings APP config directly and the URL still works.
        if not client_id:
            continue

        app, created = SocialApp.objects.using(db).get_or_create(
            provider=provider_id,
            defaults={'name': name, 'client_id': client_id, 'secret': secret},
        )
        if not created:
            # Always sync credentials from env vars
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


def remove_social_apps(apps, schema_editor):
    # Intentionally a no-op — don't delete real provider records on rollback
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_add_experience_years_to_user'),
        ('socialaccount', '0001_initial'),
        ('sites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_social_apps, remove_social_apps),
    ]
