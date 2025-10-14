# Generated manually to mark existing tables as migrated

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_parsingtask_sources'),
    ]

    operations = [
        # This is a fake migration to mark existing tables as migrated
        # The tables already exist in the database from previous migrations
        migrations.RunSQL(
            "SELECT 1;",  # No-op SQL
            reverse_sql="SELECT 1;"
        ),
    ]
