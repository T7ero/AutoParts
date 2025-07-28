# Исправление проблем с Git

## Проблема
```
Changes not staged for commit:
  modified:   .gitignore
  modified:   backend/Dockerfile
  deleted:    backend/Dockerfile.chromium
  deleted:    backend/Dockerfile.fixed
  modified:   backend/api/__pycache__/autopiter_parser.cpython-310.pyc
  modified:   backend/api/__pycache__/tasks.cpython-310.pyc
  modified:   backend/api/__pycache__/views.cpython-310.pyc
  modified:   backend/backend/__pycache__/settings.cpython-310.pyc

Untracked files:
  backend/Dockerfile.google
```

## Решение

### Шаг 1: Очистка кеша Python
```bash
# Удалить все неотслеживаемые файлы
git clean -fd

# Удалить .pyc файлы вручную
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
```

### Шаг 2: Обновить .gitignore
```bash
# Добавить исключения для Python кеша
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "backend/media/results/" >> .gitignore
echo "backend/media/uploads/" >> .gitignore
echo "pg_data/" >> .gitignore
```

### Шаг 3: Добавить нужные файлы
```bash
# Добавить обновленные файлы
git add .gitignore
git add backend/Dockerfile
git add docker-compose.yml
git add backend/api/autopiter_parser.py
git add *.md
git add init_db.sh
```

### Шаг 4: Зафиксировать изменения
```bash
git commit -m "Fix Docker build and database issues"
```

## Быстрое решение

```bash
# Очистить все
git clean -fd

# Обновить .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "backend/media/results/" >> .gitignore
echo "backend/media/uploads/" >> .gitignore
echo "pg_data/" >> .gitignore

# Добавить файлы
git add .gitignore backend/Dockerfile docker-compose.yml backend/api/autopiter_parser.py *.md init_db.sh

# Зафиксировать
git commit -m "Fix Docker build and database issues"
```

## Проверка результата

```bash
git status
```

Ожидаемый результат:
```
On branch main
Your branch is ahead of 'origin/main' by 1 commit.

nothing to commit, working tree clean
```

## Дополнительные команды

### Просмотр изменений
```bash
git diff
```

### Отмена изменений
```bash
git restore <file>
```

### Просмотр истории
```bash
git log --oneline -5
```

### Отправка изменений
```bash
git push
```

## Профилактика

### 1. Настройка .gitignore
Убедитесь, что в .gitignore включены:
- `__pycache__/`
- `*.pyc`
- `backend/media/results/`
- `backend/media/uploads/`
- `pg_data/`

### 2. Регулярная очистка
```bash
# Очистка перед коммитом
git clean -fd
```

### 3. Проверка статуса
```bash
# Регулярно проверяйте статус
git status
```

## Если проблемы продолжаются

### 1. Принудительная очистка
```bash
git reset --hard HEAD
git clean -fdx
```

### 2. Пересоздание .gitignore
```bash
rm .gitignore
# Создать новый .gitignore с правильными исключениями
```

### 3. Проверка файлов
```bash
# Проверить какие файлы отслеживаются
git ls-files
``` 