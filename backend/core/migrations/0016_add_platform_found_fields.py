from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_pricelistitem_missing_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Update DB schema conditionally; keep Django state consistent
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_pricelistitem "
                        "ADD COLUMN IF NOT EXISTS armtek_found boolean NOT NULL DEFAULT false;"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_pricelistitem "
                        "ADD COLUMN IF NOT EXISTS autopiter_found boolean NOT NULL DEFAULT false;"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_pricelistitem "
                        "ADD COLUMN IF NOT EXISTS emex_found boolean NOT NULL DEFAULT false;"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='pricelistitem',
                    name='armtek_found',
                    field=models.BooleanField(default=False, verbose_name='Найдено на Armtek'),
                ),
                migrations.AddField(
                    model_name='pricelistitem',
                    name='autopiter_found',
                    field=models.BooleanField(default=False, verbose_name='Найдено на Autopiter'),
                ),
                migrations.AddField(
                    model_name='pricelistitem',
                    name='emex_found',
                    field=models.BooleanField(default=False, verbose_name='Найдено на Emex'),
                ),
            ],
        ),
    ]
