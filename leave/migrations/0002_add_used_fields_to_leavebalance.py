# Generated migration for adding used leave tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leave', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='leavebalance',
            name='casual_used',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='leavebalance',
            name='sick_used',
            field=models.IntegerField(default=0),
        ),
    ]