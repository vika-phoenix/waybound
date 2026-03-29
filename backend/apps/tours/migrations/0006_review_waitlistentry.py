"""
0006_review_waitlistentry.py

Creates the two tables that 0005 missed because tours_savedtour already existed.
"""
from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0005_savedtour_review_waitlistentry'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ])),
                ('title', models.CharField(blank=True, max_length=120)),
                ('body', models.TextField()),
                ('operator_reply', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tour', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tour_reviews',
                    to='tours.tour',
                )),
                ('tourist', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tour_reviews',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('tour', 'tourist')},
            },
        ),
        migrations.CreateModel(
            name='WaitlistEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254)),
                ('departure_label', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tour', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='waitlist',
                    to='tours.tour',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('tour', 'email', 'departure_label')},
            },
        ),
    ]
