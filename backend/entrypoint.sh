#!/bin/bash
set -e

# Если не root, перезапускаем скрипт через gosu
if [ "$(id -u)" = "0" ]; then
    # Запускаем подготовку от root
    echo "🔧 Настройка прав доступа..."
    mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static
    chown -R appuser:appuser /app/media
    chmod -R 775 /app/media

    # Подготавливаем сокетную директорию X11 для Xvfb (иначе под appuser будет euid != 0)
    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix
    
    # Переключаемся на appuser и запускаем основной скрипт
    exec gosu appuser "$0" "$@"
    exit $?
fi

# Основной код выполняется от appuser
echo "🚀 Запуск AutoParts Backend..."

# Проверяем права доступа
echo "🔍 Проверка прав доступа..."
ls -la /app/media/

# Ждем готовности базы данных
echo "⏳ Ожидание готовности базы данных..."
max_attempts=120
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if python3 manage.py check --database default 2>/dev/null; then
        echo "✅ База данных готова!"
        break
    fi
    echo "Попытка $((attempt + 1))/$max_attempts..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "💥 Ошибка: Не удалось подключиться к базе данных"
    exit 1
fi

# Выполняем миграции
echo "🔄 Выполнение миграций..."
max_migrate_attempts=20
migrate_attempt=0
until python3 manage.py migrate --noinput; do
    migrate_attempt=$((migrate_attempt + 1))
    if [ $migrate_attempt -ge $max_migrate_attempts ]; then
        echo "❌ Миграции не удалось применить после $max_migrate_attempts попыток"
        exit 1
    fi
    echo "⚠️ Миграции не применились (DB еще поднимается?), повтор через 5 секунд... ($migrate_attempt/$max_migrate_attempts)"
    sleep 5
done

# Защита: если в базе остался дефолтный admin/admin — отключаем или меняем пароль.
# Это закрывает дыру даже если пользователь был создан ранее.
python3 manage.py shell -c "
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.getenv('ADMIN_USERNAME', 'admin')
disable_default = os.getenv('DISABLE_DEFAULT_ADMIN', '1').strip().lower() in ('1','true','yes','on')
new_password = os.getenv('ADMIN_PASSWORD', 'admin2')
force_set = os.getenv('FORCE_ADMIN_PASSWORD', '0').strip().lower() in ('1','true','yes','on')

try:
    u = User.objects.filter(username=username).first()
    if not u:
        print('ℹ️ Default-admin check: user not found')
    else:
        if u.check_password('admin'):
            if new_password:
                u.set_password(new_password)
                u.is_active = True
                u.save(update_fields=['password','is_active'])
                print('✅ Default-admin check: insecure password replaced from ADMIN_PASSWORD')
            elif disable_default:
                u.set_unusable_password()
                u.is_active = False
                u.save(update_fields=['password','is_active'])
                print('✅ Default-admin check: insecure admin disabled (set unusable password + inactive)')
            else:
                print('⚠️ Default-admin check: insecure admin/admin still enabled (DISABLE_DEFAULT_ADMIN=0)')
        elif force_set and new_password:
            u.set_password(new_password)
            u.is_active = True
            u.save(update_fields=['password','is_active'])
            print('✅ Default-admin check: admin password force-updated from ADMIN_PASSWORD')
        else:
            print('ℹ️ Default-admin check: admin password is not default')
except Exception as e:
    print(f'⚠️ Default-admin check error: {e}')
"

# Создаем суперпользователя только по явному флагу (без дефолтного admin/admin)
if [ "${CREATE_SUPERUSER:-0}" = "1" ]; then
    echo "👤 Создание суперпользователя (CREATE_SUPERUSER=1)..."
    python3 manage.py shell -c "
from django.contrib.auth.models import User
import os
username = os.getenv('ADMIN_USERNAME', 'admin')
email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
password = os.getenv('ADMIN_PASSWORD', 'admin2')
if not password:
    print('❌ ADMIN_PASSWORD пустой — суперпользователь не создан')
else:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        print('✅ Суперпользователь создан')
    else:
        print('ℹ️ Суперпользователь уже существует')
"
else
    echo "ℹ️ CREATE_SUPERUSER=0 — пропускаем создание суперпользователя"
fi

# Запускаем Xvfb
echo "🖥️ Запуск Xvfb..."
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Запускаем приложение
echo "🚀 Запуск приложения..."
exec "$@"