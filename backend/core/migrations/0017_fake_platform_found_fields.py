from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_add_platform_found_fields'),
    ]

    operations = [
        # Эта миграция ничего не делает, так как поля уже существуют в БД
        # Она нужна только для того, чтобы Django считал миграцию 0016 примененной
        migrations.RunSQL.noop,
    ]
