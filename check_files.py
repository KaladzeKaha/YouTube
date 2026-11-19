#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка готовности файлов для сборки видеоролика."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIO_EXTS = (".mp3", ".wav", ".m4a")


def find_media(base: Path, name: str):
    """Возвращает путь к файлу base/name с одним из аудио-расширений, или None."""
    for ext in AUDIO_EXTS:
        p = base / (name + ext)
        if p.exists():
            return p
    return None


def ffprobe_duration(path: Path):
    """Длительность медиафайла в секундах через ffprobe; None если не удалось."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        val = out.stdout.strip()
        return float(val) if val else None
    except Exception:
        return None


def main():
    rows = []  # (проверка, статус, примечание)

    # 1. Голос: 8 файлов 01..08 в audio/voice
    voice_dir = ROOT / "audio" / "voice"
    missing_voice = []
    for i in range(1, 9):
        num = f"{i:02d}"
        f = find_media(voice_dir, num)
        if f is None:
            missing_voice.append(num)
        else:
            dur = ffprobe_duration(f)
            dur_s = f"{dur:.2f} c" if dur is not None else "? c"
            rows.append((f"Голос {num}", "OK", f"{f.name}: {dur_s}"))
    if missing_voice:
        rows.append(("Голос 01..08", "НЕТ", "отсутствуют: " + ", ".join(missing_voice)))

    # 2. Фото товаров: 9 шт в images/products
    prod_dir = ROOT / "images" / "products"
    IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    products = sorted([p for p in prod_dir.glob("*") if p.suffix.lower() in IMG_EXTS]) if prod_dir.exists() else []
    need_products = 9 - len(products)
    status = "OK" if need_products <= 0 else "НЕТ"
    note = f"найдено {len(products)} из 9"
    if need_products > 0:
        names = [p.name for p in products]
        note += "; не хватает: " + (", ".join(names) if names else f"{need_products} файлов")
    rows.append(("Фото товаров (9)", status, note))

    # 3. Фото магазина: vyveska, vhod, zal, prodavec
    store_dir = ROOT / "images" / "store"
    missing_store = []
    for name in ("vyveska", "vhod", "zal", "prodavec"):
        found = any(store_dir.glob(f"{name}.*")) if store_dir.exists() else False
        if not found:
            missing_store.append(name)
    rows.append(("Фото магазина (4)", "OK" if not missing_store else "НЕТ",
                 "все на месте" if not missing_store else "отсутствуют: " + ", ".join(missing_store)))

    # 4. Новогодние картинки: elka, podarki
    ny_dir = ROOT / "images" / "newyear"
    missing_ny = []
    for name in ("elka", "podarki"):
        found = any(ny_dir.glob(f"{name}.*")) if ny_dir.exists() else False
        if not found:
            missing_ny.append(name)
    rows.append(("Новогодние (2)", "OK" if not missing_ny else "НЕТ",
                 "все на месте" if not missing_ny else "отсутствуют: " + ", ".join(missing_ny)))

    # 5. Шрифт
    font = ROOT / "fonts" / "GolosText-Bold.ttf"
    rows.append(("Шрифт GolosText-Bold.ttf", "OK" if font.exists() else "НЕТ",
                 str(font.relative_to(ROOT))))

    # 6. Музыка (необязательно)
    music = find_media(ROOT / "audio", "music")
    if music:
        dur = ffprobe_duration(music)
        dur_s = f"{dur:.2f} c" if dur is not None else "?"
        rows.append(("Музыка (необязательно)", "OK", f"{music.name}: {dur_s}"))
    else:
        rows.append(("Музыка (необязательно)", "нет (необязательно)",
                     "audio/music.(mp3|wav|m4a) не найден — ролик соберётся и без неё"))

    # 7. data.json заполнен?
    dj = ROOT / "data.json"
    if not dj.exists():
        rows.append(("data.json", "НЕТ", "файл не существует"))
    else:
        try:
            data = json.loads(dj.read_text(encoding="utf-8"))
            empty_fields = [k for k in ("shop", "address", "phone", "group")
                            if not str(data.get(k, "")).strip()]
            empty_items = 0
            total_items = 0
            for b in data.get("blocks", []):
                for it in b.get("items", []):
                    total_items += 1
                    if not str(it.get("photo", "")).strip() or \
                       not str(it.get("name", "")).strip() or \
                       not str(it.get("price", "")).strip():
                        empty_items += 1
            if empty_fields or empty_items:
                parts = []
                if empty_fields:
                    parts.append("пустые поля: " + ", ".join(empty_fields))
                if empty_items:
                    parts.append(f"незаполненных товаров: {empty_items} из {total_items}")
                rows.append(("data.json", "НЕ ЗАПОЛНЕН", "; ".join(parts)))
            else:
                rows.append(("data.json", "OK", f"заполнен ({total_items} товаров)"))
        except Exception as e:
            rows.append(("data.json", "ОШИБКА", str(e)))

    # Печать таблицы
    w1, w2 = max(len(r[0]) for r in rows) + 2, 12
    w3 = max(len(r[2]) for r in rows) + 2
    header = f"{'Проверка':<{w1}} {'Статус':<{w2}} {'Детали':<{w3}}"
    print(header)
    print("-" * len(header))
    for name, status, note in rows:
        print(f"{name:<{w1}} {status:<{w2}} {note}")

    ok = all(s in ("OK", "нет (необязательно)") for _, s, _ in rows)
    print("\nИТОГ:", "Все файлы на месте ✅" if ok else "Есть недостающие файлы ❌")


if __name__ == "__main__":
    main()
