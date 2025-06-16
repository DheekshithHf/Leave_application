# Generated migration for adding document thread tracking field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leave', '0002_add_used_fields_to_leavebalance'),
    ]

    operations = [
        migrations.AddField(
            model_name='leaverequest',
            name='document_thread_ts',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]