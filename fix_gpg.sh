#!/bin/bash

# Скрипт для исправления проблем с GPG ключами Ubuntu

echo "Исправление проблем с GPG ключами Ubuntu..."

# Обновляем ключи репозиториев
sudo apt-get update
sudo apt-get install -y ubuntu-keyring

# Добавляем ключи репозиториев
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F

# Обновляем сертификаты
sudo update-ca-certificates

# Очищаем кэш apt
sudo apt-get clean
sudo apt-get autoclean

echo "GPG ключи обновлены. Попробуйте снова запустить docker compose build" 