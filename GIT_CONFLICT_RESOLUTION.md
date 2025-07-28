# Решение конфликта Git веток

## Проблема
```
hint: You have divergent branches and need to specify how to reconcile them.
fatal: Need to specify how to reconcile divergent branches.
```

## Решение

### Вариант 1: Использовать merge (рекомендуется)

```bash
# Настройка Git для использования merge
git config pull.rebase false

# Выполнение pull
git pull
```

### Вариант 2: Использовать rebase

```bash
# Настройка Git для использования rebase
git config pull.rebase true

# Выполнение pull
git pull
```

### Вариант 3: Только fast-forward

```bash
# Настройка Git для только fast-forward
git config pull.ff only

# Выполнение pull
git pull
```

## Пошаговая инструкция

### Шаг 1: Проверьте статус
```bash
git status
```

### Шаг 2: Настройте стратегию слияния
```bash
# Для merge (рекомендуется)
git config pull.rebase false

# Или для rebase
git config pull.rebase true

# Или для fast-forward only
git config pull.ff only
```

### Шаг 3: Выполните pull
```bash
git pull
```

### Шаг 4: Если есть конфликты, разрешите их
```bash
# Проверьте конфликтующие файлы
git status

# Отредактируйте файлы с конфликтами
# Затем добавьте их
git add .

# Завершите merge
git commit
```

## Альтернативные решения

### Если нужно сохранить локальные изменения
```bash
# Сохраните текущие изменения
git stash

# Выполните pull
git pull

# Верните изменения
git stash pop
```

### Если нужно принудительно обновить
```bash
# Сбросьте локальные изменения
git reset --hard origin/main

# Выполните pull
git pull
```

### Если нужно создать новую ветку
```bash
# Создайте новую ветку с текущими изменениями
git checkout -b backup-branch

# Вернитесь на main
git checkout main

# Сбросьте main к origin
git reset --hard origin/main

# Выполните pull
git pull
```

## Глобальная настройка

### Для всех репозиториев
```bash
# Настройка merge для всех репозиториев
git config --global pull.rebase false

# Или rebase
git config --global pull.rebase true

# Или fast-forward only
git config --global pull.ff only
```

## Проверка настроек

```bash
# Проверьте текущие настройки
git config --list | grep pull
```

## Рекомендации

### Для командной разработки
- Используйте **merge** (`pull.rebase false`)
- Это сохраняет историю изменений
- Легче отслеживать изменения

### Для личных проектов
- Можно использовать **rebase** (`pull.rebase true`)
- Создает более чистую историю
- Требует больше внимания при конфликтах

### Для автоматизации
- Используйте **fast-forward only** (`pull.ff only`)
- Предотвращает неожиданные слияния
- Требует ручного разрешения конфликтов

## Ожидаемые результаты

### После успешного merge
- Локальная ветка обновлена
- История изменений сохранена
- Все изменения доступны

### Если есть конфликты
- Git покажет конфликтующие файлы
- Нужно вручную разрешить конфликты
- Затем выполнить commit

### Если что-то пошло не так
- Используйте `git reset --hard origin/main`
- Или создайте новую ветку с изменениями 