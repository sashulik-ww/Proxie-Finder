#!/usr/bin/env python3
"""
VLESS Reality RU-SNI Finder
Собирает и фильтрует публичные VLESS Reality конфиги
с SNI-маскировкой под российские домены (VK / Yandex / Max / Ozon и т.д.)
для работы в режиме белых списков.
"""

import re
import requests
from urllib.parse import unquote, parse_qs, urlparse
from collections import defaultdict
from datetime import datetime
import time

# === Источники (raw-файлы с GitHub) ===
SOURCES = [
    # Основной «белый» SNI-список
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    
    # RU-SNI зеркало
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/ru-sni/vless.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/ru-sni/vless_ru.txt",
    
    # Дополнительные публичные источники (можно добавлять)
    "https://raw.githubusercontent.com/aviamastersgh/vpn-free-russia/main/verified_configs.txt",
]

# === Российские домены / SNI (маскировка) ===
RU_SNI_PATTERNS = [
    r"vk\.com", r"userapi\.com", r"okcdn\.ru", r"ok\.ru",
    r"yandex\.ru", r"ya\.ru", r"yandex\.", r"yastatic\.net",
    r"maps\.yandex", r"api-maps\.yandex", r"mirror\.yandex",
    r"max\.ru", r"ozon\.ru", r"ozon\.me",
    r"avito\.ru", r"avito\.st", r"kinopoisk\.ru",
    r"mail\.ru", r"mailru", r"sberbank", r"sbercloud",
    r"mts\.ru", r"beeline\.ru", r"megafon", r"tinkoff",
    r"wildberries", r"wb\.ru", r"dns-shop", r"citilink",
    r"rbc\.ru", r"ria\.ru", r"lenta\.ru", r"gazeta\.ru",
]

RU_SNI_RE = re.compile("|".join(RU_SNI_PATTERNS), re.IGNORECASE)

# === VLESS Reality regex ===
VLESS_RE = re.compile(
    r"vless://([0-9a-fA-F-]{36})@([^:/\s]+):(\d+)\?([^#\s]+)(?:#([^\s]+))?",
    re.IGNORECASE
)


def is_ru_sni(query_string: str) -> bool:
    """Проверяет, что SNI — российский домен."""
    params = parse_qs(query_string)
    sni = params.get("sni", [""])[0]
    if not sni:
        return False
    return bool(RU_SNI_RE.search(sni))


def is_reality(query_string: str) -> bool:
    """Проверяет security=reality."""
    params = parse_qs(query_string)
    security = params.get("security", [""])[0].lower()
    return security == "reality"


def extract_configs(text: str) -> list[str]:
    """Достаёт все валидные VLESS Reality + RU-SNI ссылки."""
    found = []
    for match in VLESS_RE.finditer(text):
        uuid, host, port, query, remark = match.groups()
        full = match.group(0)
        
        if not is_reality(query):
            continue
        if not is_ru_sni(query):
            continue
        
        # Чистим remark (убираем мусор)
        if remark:
            remark = unquote(remark)[:80]
            full = f"vless://{uuid}@{host}:{port}?{query}#{remark}"
        else:
            full = f"vless://{uuid}@{host}:{port}?{query}"
        
        found.append(full)
    return found


def fetch_source(url: str, timeout: int = 15) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; VLESS-RU-SNI-Finder/1.0)"
        })
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[!] Ошибка {url}: {e}")
        return ""


def main():
    print("=" * 60)
    print("VLESS Reality RU-SNI Finder")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_configs = []
    stats = defaultdict(int)

    for url in SOURCES:
        print(f"\n→ Загружаю: {url.split('/')[-1]}")
        text = fetch_source(url)
        if not text:
            continue
        
        configs = extract_configs(text)
        print(f"  Найдено подходящих: {len(configs)}")
        all_configs.extend(configs)
        stats[url] = len(configs)
        time.sleep(0.8)  # вежливость к GitHub

    # Уникализация
    unique = list(dict.fromkeys(all_configs))  # сохраняет порядок
    print("\n" + "=" * 60)
    print(f"Всего сырых:     {len(all_configs)}")
    print(f"Уникальных:      {len(unique)}")
    print("=" * 60)

    # Сохраняем
    out_file = "vless_reality_ru_sni.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"# VLESS Reality + RU-SNI (белый список)\n")
        f.write(f"# Сгенерировано: {datetime.now().isoformat()}\n")
        f.write(f"# Всего: {len(unique)}\n\n")
        for cfg in unique:
            f.write(cfg + "\n")

    print(f"\n✅ Сохранено в: {out_file}")

    # Краткая статистика по SNI
    sni_count = defaultdict(int)
    for cfg in unique:
        m = re.search(r"sni=([^&]+)", cfg, re.I)
        if m:
            sni_count[m.group(1).lower()] += 1

    print("\nТоп SNI:")
    for sni, cnt in sorted(sni_count.items(), key=lambda x: -x[1])[:15]:
        print(f"  {cnt:4d}  {sni}")

    print("\nГотово. Можно импортировать файл в v2rayNG / Hiddify / NekoBox / Happ.")


if __name__ == "__main__":
    main()
