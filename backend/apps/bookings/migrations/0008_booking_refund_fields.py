from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0007_booking_balance_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='refund_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10,
                                      help_text='Refund amount in tour currency'),
        ),
        migrations.AddField(
            model_name='booking',
            name='refund_status',
            field=models.CharField(
                max_length=12, default='none',
                choices=[('none','None'),('pending','Pending'),('issued','Issued'),('manual','Manual transfer')],
            ),
        ),
    ]
