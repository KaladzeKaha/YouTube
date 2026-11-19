# -*- coding: utf-8 -*-
"""
Сборка вертикального ролика 1080x1920 (черновик — 540x960).
Использование:
    python3 make_video.py                 # финал 1080x1920 -> output/final.mp4
    python3 make_video.py --draft         # черновик 540x960 -> output/chernovik.mp4
Длина сцены = длительность голосового файла audio/voice/NN.*, если он есть,
иначе duration из data.json (scenes.NN.duration).
"""
import json
import os
import sys
import glob
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (ImageClip, CompositeVideoClip, concatenate_videoclips,
                     AudioFileClip, vfx)

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
FPS = 30
FONT_PATH = os.path.join(ROOT, "fonts", "GolosText-Bold.ttf")
MARGIN_Y = 200          # надписи не ближе 200 px от верха и низа
TRANSITION = 0.3        # плавный переход между сценами
ZOOM_FACTOR = 1.06      # лёгкий медленный наезд

WHITE = (255, 255, 255)
GOLD = (255, 200, 60)
DARK = (20, 20, 30)


def load_data():
    with open(os.path.join(ROOT, "data.json"), encoding="utf-8") as f:
        return json.load(f)


def voice_duration(scene_no):
    """Длительность голоса для сцены, если файл существует."""
    for ext in ("mp3", "wav", "m4a"):
        p = os.path.join(ROOT, "audio", "voice", f"{scene_no:02d}.{ext}")
        if os.path.exists(p):
            try:
                out = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", p])
                d = float(out.decode().strip())
                if d > 0:
                    return d + 0.4  # небольшой хвост после фразы
            except Exception:
                pass
    return None


def scene_duration(data, scene_no):
    d = voice_duration(scene_no)
    if d is not None:
        return d
    return float(data.get("scenes", {}).get(str(scene_no), {}).get("duration", 4))


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def text_size(draw, text, fnt):
    b = draw.textbbox((0, 0), text, font=fnt)
    return b[2] - b[0], b[3] - b[1]


def draw_centered(draw, y, text, fnt, fill, img_w=W, shadow=True):
    tw, th = text_size(draw, text, fnt)
    x = (img_w - tw) // 2
    if shadow:
        draw.text((x + 3, y + 3), text, font=fnt, fill=(0, 0, 0))
    draw.text((x, y), text, font=fnt, fill=fill)
    return th


def cover(img, w, h):
    """Заполнить кадр w×h без искажений (crop по центру)."""
    r = max(w / img.width, h / img.height)
    nw, nh = int(img.width * r + 0.5), int(img.height * r + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def bg_image(path):
    img = Image.open(path).convert("RGB")
    return cover(img, W, H)


def zoom_clip(img_clip, dur):
    """Лёгкий медленный наезд на картинку."""
    return img_clip.with_effects([vfx.CrossFadeIn(0.01),
                                  vfx.Resize(lambda t: 1 + (ZOOM_FACTOR - 1) * t / max(dur, 0.1))]) \
        if False else img_clip.with_effects(
        [vfx.Resize(lambda t: 1 + (ZOOM_FACTOR - 1) * (t / max(dur, 0.1)))])


def add_voice(clip, scene_no):
    """Наложить голос, если он есть."""
    for ext in ("mp3", "wav", "m4a"):
        p = os.path.join(ROOT, "audio", "voice", f"{scene_no:02d}.{ext}")
        if os.path.exists(p):
            try:
                a = AudioFileClip(p)
                return clip.with_audio(a)
            except Exception:
                pass
    return clip


def card_image(base_img, items, title):
    """Нарисовать поверх фона три карточки товара в столбик."""
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    f_title = font(84)
    f_name = font(56)
    f_price = font(64)

    # заголовок блока
    _, th = text_size(draw, title, f_title)
    top_y = MARGIN_Y
    draw_centered(draw, top_y, title, f_title, WHITE)

    area_top = top_y + th + 60
    area_bottom = H - MARGIN_Y
    n = len(items)
    gap = 40
    card_h = min(420, (area_bottom - area_top - gap * (n - 1)) // max(n, 1))
    card_w = 880
    x0 = (W - card_w) // 2
    total_h = card_h * n + gap * (n - 1)
    y0 = area_top + (area_bottom - area_top - total_h) // 2

    for i, it in enumerate(items):
        y = y0 + i * (card_h + gap)
        # фон карточки
        draw.rounded_rectangle([x0, y, x0 + card_w, y + card_h], radius=36,
                               fill=(255, 255, 255, 0) or (245, 245, 250))
        # фото товара слева
        photo_path = os.path.join(ROOT, it["photo"]) if it.get("photo") else None
        ph_w = card_h - 40
        tx = x0 + 30
        if photo_path and os.path.exists(photo_path):
            ph = Image.open(photo_path).convert("RGB").resize((ph_w, ph_w), Image.LANCZOS)
            mask = Image.new("L", ph.size, 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle([0, 0, ph.size[0] - 1, ph.size[1] - 1], radius=24, fill=255)
            img.paste(ph, (x0 + 20, y + 20), mask)
            tx = x0 + 20 + ph_w + 30
        # название и цена
        name = it.get("name", "")
        price = format_price(it.get("price", ""))
        cx = tx
        cy = y + card_h // 2
        nw, nh = text_size(draw, name, f_name)
        pw, ph_ = text_size(draw, price, f_price)
        block_w = nw + 40 + pw
        start_x = x0 + (card_w - (tx - x0) - block_w) // 2 + (tx - x0)
        if block_w > card_w - (tx - x0) - 20:
            # если не помещается — в две строки
            draw.text((tx, cy - nh - 10), name, font=f_name, fill=DARK)
            draw.text((tx, cy + 10), price, font=f_price, fill=GOLD)
        else:
            draw.text((start_x, cy - nh // 2), name, font=f_name, fill=DARK)
            draw.text((start_x + nw + 40, cy - ph_ // 2 - 4), price, font=f_price, fill=GOLD)
    return img


def format_price(p):
    p = str(p).strip()
    if not p:
        return ""
    try:
        v = int(float(p))
        s = f"{v:,}".replace(",", " ")
        return s + " ₽"
    except ValueError:
        return p


def scene_from_bg(bg_path, texts, scene_no, data, cards=None, title=None):
    """texts: список (text, font_size, color) сверху вниз по центру."""
    dur = scene_duration(data, scene_no)
    base = bg_image(os.path.join(ROOT, bg_path))
    if cards:
        base = card_image(base, cards, title)
    else:
        draw = ImageDraw.Draw(base)
        # вертикальная раскладка текстов
        sizes = []
        fnts = [font(t[1]) for t in texts]
        dd = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        heights = []
        for (txt, sz, col), f in zip(texts, fnts):
            _, hh = text_size(dd, txt, f)
            heights.append(hh)
        gap = 70
        total = sum(heights) + gap * (len(texts) - 1)
        y = MARGIN_Y + (H - 2 * MARGIN_Y - total) // 2
        for (txt, sz, col), hh in zip(texts, heights):
            draw_centered(draw, y, txt, font(sz), col)
            y += hh + gap
    arr = np.array(base)
    clip = ImageClip(arr, duration=dur)
    clip = zoom_clip(clip, dur)
    clip = clip.with_position("center")
    canvas = CompositeVideoClip([clip], size=(W, H))
    canvas = add_voice(canvas, scene_no)
    return canvas


def two_image_scene(bg1, bg2, texts, scene_no, data):
    """Сцена из двух фото (например вывеска+вход), разделённых пополам."""
    dur = scene_duration(data, scene_no)
    im1 = cover(Image.open(os.path.join(ROOT, bg1)).convert("RGB"), W, H // 2)
    im2 = cover(Image.open(os.path.join(ROOT, bg2)).convert("RGB"), W, H // 2)
    base = Image.new("RGB", (W, H), DARK)
    base.paste(im1, (0, 0))
    base.paste(im2, (0, H // 2))
    if texts:
        draw = ImageDraw.Draw(base)
        dd = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        heights = []
        for (txt, sz, col) in texts:
            _, hh = text_size(dd, txt, font(sz))
            heights.append(hh)
        gap = 60
        total = sum(heights) + gap * (len(texts) - 1)
        y = MARGIN_Y + (H - 2 * MARGIN_Y - total) // 2
        for (txt, sz, col), hh in zip(texts, heights):
            # плашка под текст для читаемости
            f = font(sz)
            tw, th = text_size(draw, txt, f)
            x = (W - tw) // 2
            draw.rounded_rectangle([x - 40, y - 20, x + tw + 40, y + th + 20],
                                   radius=30, fill=(0, 0, 0))
            draw_centered(draw, y, txt, f, col)
            y += hh + gap
    arr = np.array(base)
    clip = ImageClip(arr, duration=dur)
    clip = zoom_clip(clip, dur)
    canvas = CompositeVideoClip([clip], size=(W, H))
    canvas = add_voice(canvas, scene_no)
    return canvas


def build(scale=None, out_path=None):
    data = load_data()
    shop = data.get("shop", "")
    address = data.get("address", "")
    phone = data.get("phone", "")
    group = data.get("group", "")
    blocks = data.get("blocks", [])

    scenes = []

    # Сцена 1: ёлка + название магазина
    scenes.append(scene_from_bg(
        "images/newyear/elka.jpg",
        [("Новый год", 96, WHITE),
         (f"в магазине «{shop}»", 76, GOLD)],
        1, data))

    # Сцена 2: вывеска + вход
    scenes.append(two_image_scene(
        "images/store/vyveska.jpg", "images/store/vhod.jpg",
        [(f"«{shop}»", 100, WHITE),
         ("техника для дома", 70, WHITE)],
        2, data))

    # Сцены 3–5: блоки товаров
    for i, blk in enumerate(blocks[:3]):
        title = blk.get("title") or f"до {blk.get('sum_to')} ₽"
        scenes.append(scene_from_bg(
            "images/newyear/fon.jpg", [], 3 + i, data,
            cards=blk.get("items", []), title=title))

    # Сцена 6: продавец-консультант
    scenes.append(scene_from_bg(
        "images/store/prodavec.jpg",
        [("Помощь в выборе", 88, WHITE),
         ("и доставка", 88, WHITE)],
        6, data))

    # Сцена 7: зал + адрес
    scenes.append(scene_from_bg(
        "images/store/zal.jpg",
        [("Ждём вас:", 80, WHITE),
         (address, 68, GOLD),
         (group, 56, WHITE) if group else ("", 1, WHITE)],
        7, data))

    # Сцена 8: подарки + телефон
    scenes.append(scene_from_bg(
        "images/newyear/podarki.jpg",
        [("Подарки ждут!", 92, WHITE),
         (phone, 76, GOLD)],
        8, data))

    # склейка с плавными переходами
    final = concatenate_videoclips(scenes, method="compose", padding=-TRANSITION,
                                   bg_color=(0, 0, 0))
    final = final.with_fps(FPS)

    if scale:
        sw, sh = scale
        final = final.with_effects([vfx.Resize(sw / W)])
        final = CompositeVideoClip([final.with_position("center")], size=(sw, sh))

    if out_path is None:
        out_path = os.path.join(ROOT, "output", "final.mp4")
    final.write_videofile(out_path, fps=FPS, codec="libx264",
                          audio_codec="aac" if final.audio is not None else None,
                          preset="medium", logger=None)
    print("Готово:", out_path)
    print("Длительность: %.1f сек" % final.duration)
    return out_path


if __name__ == "__main__":
    if "--draft" in sys.argv:
        build(scale=(540, 960), out_path=os.path.join(ROOT, "output", "chernovik.mp4"))
    else:
        build()
