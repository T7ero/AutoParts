#!/bin/bash

echo "Исправление миграций на сервере..."

# Переходим в директорию проекта
cd ~/AutoParts

# Обновляем код
echo "Обновление кода..."
git pull

# Удаляем проблемную миграцию 0006
echo "Удаление проблемной миграции..."
rm -f backend/core/migrations/0006_competitor_part_article_pricelisttask_progress_and_more.py

# Создаем фиктивную миграцию 0006
echo "Создание фиктивной миграции 0006..."
cat > backend/core/migrations/0006_fake_existing_tables.py << 'EOF'
# Generated manually to mark existing tables as migrated

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_parsingtask_sources'),
    ]

    operations = [
        # This is a fake migration to mark existing tables as migrated
        migrations.RunSQL(
            "SELECT 1;",  # No-op SQL
            reverse_sql="SELECT 1;"
        ),
    ]
EOF

# Создаем миграцию для недостающих полей
echo "Создание миграции для недостающих полей..."
cat > backend/core/migrations/0007_add_missing_fields.py << 'EOF'
# Generated manually to add missing fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_fake_existing_tables'),
    ]

    operations = [
        # Add missing fields to existing models
        migrations.AddField(
            model_name='part',
            name='article',
            field=models.CharField(max_length=100, verbose_name='Артикул', blank=True, default=''),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='progress',
            field=models.IntegerField(default=0, verbose_name='Прогресс (%)'),
        ),
    ]
EOF

# Применяем фиктивную миграцию
echo "Применение фиктивной миграции..."
docker compose exec backend python manage.py migrate core 0006 --fake

# Применяем миграцию для недостающих полей
echo "Применение миграции для недостающих полей..."
docker compose exec backend python manage.py migrate core

# Перезапускаем контейнеры
echo "Перезапуск контейнеров..."
docker compose restart backend celery

echo "Исправление завершено!"
