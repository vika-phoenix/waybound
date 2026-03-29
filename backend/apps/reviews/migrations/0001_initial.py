from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bookings', '0001_initial'),
        ('tours', '0002_tour_extra_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TourReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('title', models.CharField(blank=True, max_length=200)),
                ('body', models.TextField()),
                ('operator_reply', models.TextField(blank=True)),
                ('replied_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending moderation'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviews', to='bookings.booking')),
                ('tour', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='tours.tour')),
                ('tourist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['tour', 'status'], name='reviews_tou_tour_id_status_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='tourreview',
            constraint=models.UniqueConstraint(fields=['tourist', 'tour'], name='unique_tourist_tour_review'),
        ),
    ]
