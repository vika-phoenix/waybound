"""
apps/tours/migrations/0004_propertyphoto.py
Adds PropertyPhoto model — photos per accommodation (StayBlock) row.
"""
from django.db import migrations, models
import django.db.models.deletion
import apps.tours.models


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0003_tour_categories'),
    ]

    operations = [
        migrations.CreateModel(
            name='PropertyPhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to=apps.tours.models.stay_photo_path)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('caption', models.CharField(blank=True, max_length=200)),
                ('stay', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='photos',
                    to='tours.stayblock',
                )),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
