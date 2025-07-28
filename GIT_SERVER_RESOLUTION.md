# Решение проблемы Git на Linux сервере

## Текущая ситуация
У вас есть расходящиеся ветки и много неотслеживаемых файлов. Нужно решить конфликт и очистить репозиторий.

## Пошаговое решение

### Шаг 1: Настройте Git для merge
```bash
git config pull.rebase false
```

### Шаг 2: Очистите неотслеживаемые файлы
```bash
# Удалите все неотслеживаемые файлы
git clean -fd

# Удалите файлы .pyc (кеш Python)
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
```

### Шаг 3: Добавьте важные изменения
```bash
# Добавьте только важные файлы
git add backend/Dockerfile
git add backend/api/autopiter_parser.py
git add backend/api/tasks.py
git add backend/requirements.txt
git add docker-compose.yml
git add *.md
```

### Шаг 4: Зафиксируйте изменения
```bash
git commit -m "Fix Docker build issues and update parser"
```

### Шаг 5: Выполните pull с merge
```bash
git pull --no-rebase
```

### Шаг 6: Если есть конфликты, разрешите их
```bash
# Проверьте статус
git status

# Если есть конфликты, отредактируйте файлы
# Затем добавьте их
git add .

# Завершите merge
git commit
```

## Альтернативное решение (если выше не работает)

### Вариант 1: Принудительный reset
```bash
# Сохраните текущие изменения в новую ветку
git checkout -b backup-changes

# Вернитесь на main
git checkout main

# Сбросьте к origin/main
git reset --hard origin/main

# Выполните pull
git pull
```

### Вариант 2: Stash и pull
```bash
# Сохраните изменения
git stash

# Выполните pull
git pull

# Верните изменения
git stash pop
```

## Очистка репозитория

### Удаление ненужных файлов
```bash
# Удалите .pyc файлы
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Удалите временные файлы
rm -rf backend/media/results/*
rm -rf backend/media/uploads/*
rm -rf pg_data/

# Удалите backup файлы
rm -f backend/Dockerfile.backup
rm -f backend/Dockerfile.alternative
```

### Добавление в .gitignore
```bash
# Добавьте в .gitignore
echo "*.pyc" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "backend/media/results/" >> .gitignore
echo "backend/media/uploads/" >> .gitignore
echo "pg_data/" >> .gitignore
echo "*.backup" >> .gitignore
```

## Проверка результата

### Проверьте статус
```bash
git status
```

### Проверьте историю
```bash
git log --oneline -10
```

### Проверьте ветки
```bash
git branch -a
```

## Ожидаемые результаты

### После успешного решения
- Локальная ветка синхронизирована с origin/main
- Все важные изменения сохранены
- Репозиторий очищен от ненужных файлов

### Если проблемы продолжаются
1. Используйте `git reset --hard origin/main`
2. Создайте новую ветку с изменениями
3. Обратитесь к администратору репозитория

## Дополнительные команды

### Просмотр различий
```bash
# Посмотрите различия между ветками
git diff origin/main

# Посмотрите последние коммиты
git log --oneline origin/main..HEAD
```

### Отмена изменений
```bash
# Отменить все локальные изменения
git reset --hard HEAD

# Отменить изменения в конкретном файле
git checkout -- backend/Dockerfile
```

### Создание патча
```bash
# Создать патч с изменениями
git diff > changes.patch

# Применить патч позже
git apply changes.patch
``` 