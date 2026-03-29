from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='enquirymessage',
            name='operator_reply',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='enquirymessage',
            name='replied_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
