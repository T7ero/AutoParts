import requests
from bs4 import BeautifulSoup
import re

def get_brands_by_artikul(artikul, proxies=None):
    url = f"https://autopiter.ru/goods/{artikul}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, proxies=proxies)
    
    print(f"[DEBUG PARSER] Запрос к {url}, Статус: {response.status_code}")
    if response.status_code != 200:
        print(f"[DEBUG PARSER] Ошибка запроса, статус код не 200. Содержимое: {response.text[:500]}...") # Выводим первые 500 символов
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    brands = []
    # Новый селектор: только <span title="..."></span> внутри таблицы предложений
    for tag in soup.select('span[title]'):
        txt = tag.get('title', '').strip()
        if txt and txt.lower() != 'показать все':
            brands.append(txt)
    # Удаляем дубли
    brands = list(dict.fromkeys(brands))
    if not brands:
        print(f"[DEBUG PARSER] Бренды не найдены по селектору 'span[title]'. HTML-содержимое страницы: {response.text[:1000]}...")
    return brands 