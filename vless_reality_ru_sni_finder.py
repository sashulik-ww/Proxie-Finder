#!/usr/bin/env python3
"""
VLESS Reality RU-SNI Finder v2.1
- Собирает публичные VLESS Reality конфиги
- Фильтрует только security=reality + российские SNI
- Определяет флаг, страну и город по IP
- Измеряет latency и сортирует по скорости
- Оставляет до 500 лучших
- Формат названия: 🇳🇱 Netherlands, Amsterdam
"""

import re
import socket
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, parse_qs
from collections import defaultdict
from datetime import datetime

# ===================== НАСТРОЙКИ =====================
MAX_SERVERS = 500
TIMEOUT_CONNECT = 2.8          # секунды на проверку скорости
MAX_WORKERS = 40               # параллельных проверок
GEO_CACHE = {}                 # кэш геолокации

# ===================== ИСТОЧНИКИ =====================
SOURCES = [
    # Основные "белые" списки
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/nikita29a/FreeProxyList/refs/heads/main/mirror/1.txt", 

    # kort0881
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/ru-sni/vless.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/ru-sni/vless_ru.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/clean/vless.txt",

    # Другие публичные источники
    "https://raw.githubusercontent.com/aviamastersgh/vpn-free-russia/main/verified_configs.txt",
    "https://raw.githubusercontent.com/aviamastersgh/vpn-free-russia/main/all_configs.txt",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/reality",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/protocols/vless",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
]

# ===================== РОССИЙСКИЕ SNI =====================
RU_SNI_PATTERNS = [
    r"vk\.com", r"userapi\.com", r"okcdn\.ru", r"ok\.ru",
    r"yandex\.ru", r"ya\.ru", r"yandex\.", r"yastatic\.net",
    r"maps\.yandex", r"api-maps\.yandex", r"mirror\.yandex",
    r"max\.ru", r"ozon\.ru", r"ozon\.me",
    r"avito\.ru", r"avito\.st", r"kinopoisk\.ru",
    r"mail\.ru", r"sber", r"tinkoff", r"wildberries", r"wb\.ru",
    r"mts\.ru", r"beeline", r"megafon", r"dns-shop", r"citilink",
    r"rbc\.ru", r"ria\.ru", r"lenta\.ru",
]
RU_SNI_RE = re.compile("|".join(RU_SNI_PATTERNS), re.IGNORECASE)

VLESS_RE = re.compile(
    r"vless://([0-9a-fA-F-]{36})@([^:/\s]+):(\d+)\?([^#\s]+)(?:#([^\s]*))?",
    re.IGNORECASE
)

# ===================== ФУНКЦИИ =====================

def is_reality_and_ru_sni(query: str) -> bool:
    params = parse_qs(query)
    if params.get("security", [""])[0].lower() != "reality":
        return False
    sni = params.get("sni", [""])[0]
    return bool(sni and RU_SNI_RE.search(sni))


def extract_configs(text: str) -> list[str]:
    found = []
    for m in VLESS_RE.finditer(text):
        uuid, host, port, query, remark = m.groups()
        if not is_reality_and_ru_sni(query):
            continue
        link = f"vless://{uuid}@{host}:{port}?{query}"
        if remark:
            link += f"#{unquote(remark)[:60]}"
        found.append(link)
    return found


def fetch_source(url: str) -> str:
    try:
        r = requests.get(url, timeout=18, headers={
            "User-Agent": "Mozilla/5.0 (compatible; VLESS-Finder/2.1)"
        })
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  [!] {url.split('/')[-1]} → {e}")
        return ""


def resolve_ip(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except:
        return None


def get_geo(ip: str) -> dict:
    """Получаем страну, город и флаг по IP (с кэшем)"""
    if ip in GEO_CACHE:
        return GEO_CACHE[ip]

    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,query",
            timeout=4
        )
        data = r.json()
        if data.get("status") == "success":
            code = data.get("countryCode", "XX")
            flag = "".join(
                chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper()
            ) if len(code) == 2 else "🏳️"
            result = {
                "flag": flag,
                "country": data.get("country", "Unknown"),
                "city": data.get("city") or "—",
                "ip": ip
            }
        else:
            result = {"flag": "🏳️", "country": "Unknown", "city": "—", "ip": ip}
    except:
        result = {"flag": "🏳️", "country": "Unknown", "city": "—", "ip": ip}

    GEO_CACHE[ip] = result
    time.sleep(0.12)  # защита от лимита API
    return result


def measure_latency(host: str, port: int) -> float | None:
    """Измеряет TCP latency (мс)"""
    try:
        start = time.perf_counter()
        sock = socket.create_connection((host, port), timeout=TIMEOUT_CONNECT)
        sock.close()
        return round((time.perf_counter() - start) * 1000, 1)
    except:
        return None


def process_one(link: str) -> dict | None:
    m = VLESS_RE.match(link)
    if not m:
        return None
    uuid, host, port, query, remark = m.groups()
    port = int(port)

    ip = resolve_ip(host)
    if not ip:
        return None

    latency = measure_latency(host, port)
    if latency is None:
        return None

    geo = get_geo(ip)

    # Формат: 🇳🇱 Netherlands, Amsterdam
    title = f"{geo['flag']} {geo['country']}, {geo['city']}"
    clean_link = f"vless://{uuid}@{host}:{port}?{query}#{title}"

    return {
        "link": clean_link,
        "latency": latency,
        "country": geo["country"],
        "city": geo["city"],
        "flag": geo["flag"],
        "ip": ip
    }


def main():
    print("=" * 65)
    print("VLESS Reality RU-SNI Finder v2.1")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 1. Собираем все конфиги
    all_links = []
    for url in SOURCES:
        print(f"→ {url.split('/')[-1]}")
        text = fetch_source(url)
        if text:
            found = extract_configs(text)
            print(f"   +{len(found)}")
            all_links.extend(found)
        time.sleep(0.6)

    unique_links = list(dict.fromkeys(all_links))
    print(f"\nВсего уникальных Reality+RU-SNI: {len(unique_links)}")

    if not unique_links:
        print("Ничего не найдено")
        return

    # 2. Параллельная проверка скорости + гео
    print(f"\nПроверяю скорость и геолокацию (до {MAX_SERVERS} лучших)...")
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, link): link for link in unique_links}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            if res:
                results.append(res)
            if i % 50 == 0:
                print(f"  обработано {i}/{len(unique_links)} | живых: {len(results)}")

    # 3. Сортировка по скорости и ограничение
    results.sort(key=lambda x: x["latency"])
    results = results[:MAX_SERVERS]

    print(f"\nЖивых серверов после фильтра: {len(results)}")

    # 4. Сохраняем
    out_file = "vless_reality_ru_sni.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"# VLESS Reality + RU-SNI | отсортировано по скорости\n")
        f.write(f"# Сгенерировано: {datetime.now().isoformat()}\n")
        f.write(f"# Всего: {len(results)}\n\n")
        for r in results:
            f.write(r["link"] + "\n")

    print(f"\n✅ Сохранено в {out_file}")

    # Статистика
    print("\nТоп-10 самых быстрых:")
    for r in results[:10]:
        print(f"  {r['latency']:6.1f} ms  {r['flag']} {r['country']}, {r['city']}")

    countries = defaultdict(int)
    for r in results:
        countries[r["country"]] += 1
    print("\nПо странам:")
    for country, cnt in sorted(countries.items(), key=lambda x: -x[1])[:12]:
        print(f"  {cnt:3d}  {country}")


if __name__ == "__main__":
    main()
