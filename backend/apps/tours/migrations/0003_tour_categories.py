"""
Migration: add categories JSONField to Tour + backfill from existing category.
"""
from django.db import migrations, models


def backfill_categories(apps, schema_editor):
    Tour = apps.get_model('tours', 'Tour')
    for tour in Tour.objects.all():
        if tour.category and not tour.categories:
            tour.categories = [tour.category]
            tour.save(update_fields=['categories'])


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0002_tour_extra_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='tour',
            name='categories',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Multi-select list of category strings',
            ),
        ),
        migrations.RunPython(backfill_categories, migrations.RunPython.noop),
    ]
