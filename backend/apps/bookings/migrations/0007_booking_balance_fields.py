from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0006_booking_cancel_policy_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='balance_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='booking',
            name='balance_payment_id',
            field=models.CharField(blank=True, default='', help_text='YooKassa payment UUID for balance', max_length=64),
        ),
        migrations.AddField(
            model_name='booking',
            name='balance_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')],
                default='pending',
                max_length=12,
            ),
        ),
    ]
