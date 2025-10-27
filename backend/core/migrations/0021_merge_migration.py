from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_add_created_at_to_pricelistitem'),
        ('core', '0020_add_quantity_fields_client'),
    ]

    operations = [
        # Эта миграция объединяет изменения из 0020_add_quantity_fields_client
        # Поля уже добавлены в 0020, поэтому здесь ничего не делаем
    ]
