from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_fake_platform_found_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_pricelistitem "
                        "ADD COLUMN IF NOT EXISTS created_at timestamp with time zone NOT NULL DEFAULT NOW();"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='pricelistitem',
                    name='created_at',
                    field=models.DateTimeField(auto_now_add=True),
                ),
            ],
        ),
    ]


