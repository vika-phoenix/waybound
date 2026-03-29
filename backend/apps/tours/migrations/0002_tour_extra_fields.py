from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tour',
            name='language',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='tour',
            name='min_age',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tour',
            name='max_age',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tour',
            name='is_private',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tour',
            name='video_url',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='tour',
            name='getting_there',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='tour',
            name='organiser_note',
            field=models.TextField(blank=True, default=''),
        ),
    ]
