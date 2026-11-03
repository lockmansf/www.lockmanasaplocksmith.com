"""Lockman rescue: original comic animation, 1080x1920, 24 fps. Pillow frames piped into ffmpeg."""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import music  # noqa: E402

W, H, FPS = 1080, 1920, 24
TOTAL = 27.0
ASSETS = Path(__file__).resolve().parent.parent / "assets"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

import os
FONT = next((f for f in ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
             if os.path.exists(f)), None)
F = {s: ImageFont.truetype(FONT, s) for s in (30, 38, 46, 54, 64, 76, 92, 120)}

YELLOW = (242, 194, 0)
BLACK = (14, 14, 18)
BLUE = (28, 66, 170)
BLUE_D = (16, 40, 110)
SKIN = (196, 136, 92)
WHITE = (255, 255, 255)
GROUND_Y = 1460

logo = Image.open(ASSETS / "img/logo-full-600.webp").convert("RGBA")
emblem = logo.crop((60, 0, 540, 330))  # the yellow diamond-lock emblem


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def seg(t, a, b):
    return max(0.0, min(1.0, (t - a) / (b - a)))


def lerp(a, b, x):
    return a + (b - a) * x


# ------------------------------------------------------------------ text helpers
def text_c(d, cx, y, s, font, fill=BLACK, stroke=0, stroke_fill=BLACK):
    w = d.textlength(s, font=font)
    d.text((cx - w / 2, y), s, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)


def bubble(img, x, y, w, lines, tail, font=F[54], appear=1.0):
    if appear <= 0:
        return
    s = 0.6 + 0.4 * ease(appear)
    lh = font.size * 1.15
    h = int(len(lines) * lh + 56)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = x + w / 2, y + h / 2
    bw, bh = w * s, h * s
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    tx, ty = tail
    base = [(cx - 40 * s, box[3] - 8), (cx + 40 * s, box[3] - 8)] if ty > cy else [(cx - 40 * s, box[1] + 8), (cx + 40 * s, box[1] + 8)]
    d.polygon([base[0], (tx, ty), base[1]], fill=WHITE, outline=BLACK)
    d.line([base[0], (tx, ty), base[1]], fill=BLACK, width=7)
    d.rounded_rectangle(box, radius=int(46 * s), fill=WHITE, outline=BLACK, width=7)
    d.polygon([(base[0][0] + 7, base[0][1] - (6 if ty > cy else -6)), (tx, ty - (14 if ty > cy else -14)), (base[1][0] - 7, base[1][1] - (6 if ty > cy else -6))], fill=WHITE)
    if appear > 0.5:
        f = ImageFont.truetype(FONT, max(10, int(font.size * s)))
        for i, ln in enumerate(lines):
            text_c(d, cx, box[1] + 26 * s + i * lh * s, ln, f)
    img.alpha_composite(layer)


def burst(img, cx, cy, r, word, color=YELLOW, appear=1.0, rot=0):
    if appear <= 0:
        return
    k = 0.3 + 0.7 * ease(min(1, appear * 1.6))
    wob = 1 + 0.05 * math.sin(appear * 30)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = []
    n = 14
    for i in range(n * 2):
        a = rot + i * math.pi / n
        rr = r * k * wob * (1.0 if i % 2 == 0 else 0.68)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.8))
    d.polygon(pts, fill=(200, 30, 40))
    d.polygon([(cx + (px - cx) * 0.88, cy + (py - cy) * 0.88) for px, py in pts], fill=color, outline=BLACK, width=6)
    f = ImageFont.truetype(FONT, max(10, int(r * 0.42 * k)))
    tw = d.textlength(word, font=f)
    d.text((cx - tw / 2, cy - f.size * 0.62), word, font=f, fill=WHITE, stroke_width=max(2, int(8 * k)), stroke_fill=BLACK)
    img.alpha_composite(layer)


def caption(img, s, appear=1.0, y=110):
    if appear <= 0:
        return
    d = ImageDraw.Draw(img)
    shown = s[: max(1, int(len(s) * min(1, appear * 1.5)))]
    f = F[54]
    w = d.textlength(s, font=f)
    d.rectangle((W / 2 - w / 2 - 34, y - 18, W / 2 + w / 2 + 34, y + f.size + 22), fill=BLACK, outline=YELLOW, width=6)
    d.text((W / 2 - w / 2, y), shown, font=f, fill=YELLOW)


# ------------------------------------------------------------------ backgrounds
def day_street(t):
    img = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(0, GROUND_Y, 8):  # sky gradient
        k = y / GROUND_Y
        d.rectangle((0, y, W, y + 8), fill=(int(lerp(80, 190, k)), int(lerp(170, 225, k)), int(lerp(235, 250, k))))
    d.ellipse((780, 180, 960, 360), fill=(255, 226, 90))  # sun
    for i in range(12):
        a = t * 0.4 + i * math.pi / 6
        d.line((870 + 110 * math.cos(a), 270 + 110 * math.sin(a), 870 + 150 * math.cos(a), 270 + 150 * math.sin(a)), fill=(255, 226, 90), width=10)
    # comic clouds drifting
    for cx, cy, sc in ((200, 420, 1.0), (640, 560, 0.8), (1100, 380, 0.9)):
        x = (cx + t * 18 * sc) % (W + 400) - 200
        for dx, dy, r in ((0, 0, 70), (70, -30, 80), (150, 0, 65), (75, 20, 70)):
            d.ellipse((x + dx * sc - r * sc, cy + dy * sc - r * sc, x + dx * sc + r * sc, cy + dy * sc + r * sc), fill=WHITE, outline=(40, 40, 50), width=4)
    # San Francisco row houses (Victorian style), original shapes
    colors = [(232, 120, 120), (120, 190, 170), (245, 205, 110), (150, 160, 220), (240, 160, 90), (190, 120, 180)]
    x = -40
    for i in range(7):
        w = 190
        top = 820 + (i % 3) * 40
        c = colors[i % len(colors)]
        d.rectangle((x, top, x + w, GROUND_Y), fill=c, outline=BLACK, width=5)
        d.polygon([(x - 10, top), (x + w / 2, top - 120), (x + w + 10, top)], fill=tuple(max(0, v - 40) for v in c), outline=BLACK, width=5)
        for wy in (top + 60, top + 260):
            for wx in (x + 30, x + 110):
                d.rectangle((wx, wy, wx + 52, wy + 110), fill=(250, 245, 220), outline=BLACK, width=4)
                d.line((wx + 26, wy, wx + 26, wy + 110), fill=BLACK, width=3)
        d.rectangle((x + 70, GROUND_Y - 170, x + 125, GROUND_Y), fill=(110, 70, 50), outline=BLACK, width=4)
        x += w
    d.rectangle((0, GROUND_Y, W, GROUND_Y + 70), fill=(200, 200, 205), outline=BLACK, width=5)  # sidewalk
    d.rectangle((0, GROUND_Y + 70, W, H), fill=(60, 62, 70))  # road
    for i in range(6):
        d.rectangle((i * 220 + 40, 1720, i * 220 + 160, 1740), fill=(240, 240, 240))
    return img


def halftone(img, color=(0, 0, 0, 40), step=26):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, H, step):
        for x in range((y // step % 2) * step // 2, W, step):
            r = 3 + 3 * (y / H)
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    return layer


HALF_DARK = None


def night_sky(t, zoom=1.0):
    img = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 8):
        k = y / H
        d.rectangle((0, y, W, y + 8), fill=(int(lerp(10, 60, k)), int(lerp(12, 30, k)), int(lerp(40, 90, k))))
    rng = np.random.default_rng(3)
    for _ in range(90):
        x, y = rng.integers(0, W), rng.integers(0, 1100)
        tw = 2 + 2 * math.sin(t * 6 + x)
        d.ellipse((x - tw, y - tw, x + tw, y + tw), fill=(255, 255, 230))
    # beam from the street up into the clouds
    by = 520
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.polygon([(W / 2 - 40, H), (W / 2 + 40, H), (W / 2 + 330 * zoom, by), (W / 2 - 330 * zoom, by)], fill=(255, 235, 150, 90))
    g.ellipse((W / 2 - 380 * zoom, by - 250 * zoom, W / 2 + 380 * zoom, by + 250 * zoom), fill=(255, 230, 120, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(glow)
    # clouds around the signal
    for cx, cy, r in ((130, 430, 120), (300, 330, 140), (820, 340, 150), (980, 470, 120), (540, 250, 120), (200, 640, 110), (900, 650, 120)):
        d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 0.6), fill=(70, 70, 110), outline=(25, 25, 45), width=5)
    em = emblem.resize((int(560 * zoom), int(385 * zoom)))
    dark = Image.new("RGBA", em.size, (20, 20, 30, 255))
    mask = em.split()[3]
    sig = Image.new("RGBA", em.size, (0, 0, 0, 0))
    sig.paste(dark, (0, 0), mask)  # emblem silhouette inside the light, like a projected signal
    img.alpha_composite(sig, (int(W / 2 - em.size[0] / 2), int(by - em.size[1] / 2)))
    # city skyline silhouette (generic shapes)
    sky = ImageDraw.Draw(img)
    x = 0
    rng2 = np.random.default_rng(11)
    while x < W:
        w = int(rng2.integers(70, 150))
        h = int(rng2.integers(180, 420))
        sky.rectangle((x, H - h, x + w, H), fill=(8, 8, 14))
        for wy in range(H - h + 30, H - 20, 46):
            for wx in range(x + 14, x + w - 20, 30):
                if rng2.random() < 0.45:
                    sky.rectangle((wx, wy, wx + 12, wy + 18), fill=(250, 210, 90))
        x += w + 6
    sky.polygon([(380, H - 300), (430, H - 760), (480, H - 300)], fill=(8, 8, 14))  # pointed tower
    img.alpha_composite(HALF_DARK)
    return img


# ------------------------------------------------------------------ characters
def draw_car(img, door=0.0, shake=0.0, ox0=260, color=(205, 40, 50)):
    d = ImageDraw.Draw(img)
    ox = ox0 + shake
    top = 1110
    d.ellipse((ox - 20, GROUND_Y - 10, ox + 620, GROUND_Y + 40), fill=(0, 0, 0, 70))
    body = [(ox, 1300), (ox + 40, 1240), (ox + 140, 1220), (ox + 210, top), (ox + 450, top), (ox + 530, 1220), (ox + 600, 1250), (ox + 610, 1300), (ox + 600, 1400), (ox + 10, 1400)]
    d.polygon(body, fill=color, outline=BLACK)
    d.line(body + [body[0]], fill=BLACK, width=8)
    # windows
    d.polygon([(ox + 225, top + 20), (ox + 325, top + 20), (ox + 325, 1225), (ox + 160, 1225)], fill=(170, 215, 240), outline=BLACK, width=6)
    d.polygon([(ox + 345, top + 20), (ox + 440, top + 20), (ox + 510, 1225), (ox + 345, 1225)], fill=(170, 215, 240), outline=BLACK, width=6)
    for wx in (ox + 120, ox + 470):
        d.ellipse((wx - 70, 1330, wx + 70, 1470), fill=BLACK)
        d.ellipse((wx - 34, 1366, wx + 34, 1434), fill=(160, 160, 170))
    d.rectangle((ox + 580, 1270, ox + 612, 1300), fill=(255, 230, 120), outline=BLACK, width=4)
    d.line((ox + 335, 1230, ox + 335, 1390), fill=BLACK, width=5)
    # front door (opens towards the viewer, drawn as a widening panel)
    if door > 0:
        dx = 335 - 200 * door
        d.polygon([(ox + 335, 1225), (ox + dx, 1200 - 40 * door), (ox + dx, 1400 + 30 * door), (ox + 335, 1395)], fill=(170, 25, 35), outline=BLACK)
        d.line([(ox + 335, 1225), (ox + dx, 1200 - 40 * door), (ox + dx, 1400 + 30 * door), (ox + 335, 1395)], fill=BLACK, width=7)
    else:
        d.rectangle((ox + 360, 1250, ox + 410, 1266), fill=(60, 60, 70), outline=BLACK, width=3)  # handle
    return ox


def draw_dog(img, x, y, s=1.0, bark=0.0, happy=False, tongue=False):
    d = ImageDraw.Draw(img)
    fur, dark = (176, 112, 56), (110, 66, 30)
    # body (only when out of the car)
    if happy:
        d.ellipse((x - 95 * s, y + 20 * s, x + 95 * s, y + 130 * s), fill=fur, outline=BLACK, width=5)
        wag = math.sin(bark * 20) * 25
        d.line((x + 90 * s, y + 60 * s, x + 150 * s, y + 10 * s + wag), fill=fur, width=int(18 * s))
    d.ellipse((x - 62 * s, y - 60 * s, x + 62 * s, y + 55 * s), fill=fur, outline=BLACK, width=5)  # head
    d.ellipse((x - 78 * s, y - 50 * s, x - 38 * s, y + 30 * s), fill=dark, outline=BLACK, width=4)  # ears
    d.ellipse((x + 38 * s, y - 50 * s, x + 78 * s, y + 30 * s), fill=dark, outline=BLACK, width=4)
    d.ellipse((x - 34 * s, y - 18 * s, x - 14 * s, y + 4 * s), fill=BLACK)
    d.ellipse((x + 14 * s, y - 18 * s, x + 34 * s, y + 4 * s), fill=BLACK)
    d.ellipse((x - 40 * s, y + 6 * s, x + 40 * s, y + 52 * s), fill=(230, 200, 160), outline=BLACK, width=4)  # muzzle
    d.ellipse((x - 12 * s, y + 8 * s, x + 12 * s, y + 24 * s), fill=BLACK)
    mo = 10 + 18 * max(0, math.sin(bark * math.pi * 6)) if bark else 4
    d.ellipse((x - 14 * s, y + 30 * s, x + 14 * s, y + (30 + mo) * s), fill=(120, 20, 30))
    if tongue:
        d.ellipse((x - 10 * s, y + 38 * s, x + 10 * s, y + 70 * s), fill=(240, 110, 130), outline=BLACK, width=3)


def draw_owner(img, x, y, t, mode="panic", s=1.0, shirt=(60, 150, 90), hair=(70, 45, 30), skin=None):
    d = ImageDraw.Draw(img)
    jit = math.sin(t * 40) * 6 if mode == "panic" else 0
    x += jit
    pants = (50, 60, 90)
    SK = skin or SKIN
    d.ellipse((x - 70, GROUND_Y - 12, x + 70, GROUND_Y + 14), fill=(0, 0, 0, 70))
    d.rectangle((x - 40, y + 210, x - 8, GROUND_Y - 10), fill=pants, outline=BLACK, width=5)  # legs
    d.rectangle((x + 8, y + 210, x + 40, GROUND_Y - 10), fill=pants, outline=BLACK, width=5)
    d.rounded_rectangle((x - 58, y + 60, x + 58, y + 225), radius=30, fill=shirt, outline=BLACK, width=6)  # torso
    if mode == "panic":  # hands on head
        for sx in (-1, 1):
            d.line((x + sx * 50, y + 80, x + sx * 95, y - 10, x + sx * 50, y - 60), fill=SK, width=22, joint="curve")
    elif mode == "phone":
        d.line((x - 50, y + 80, x - 80, y + 200), fill=SK, width=22)
        d.line((x + 50, y + 80, x + 70, y + 20, x + 40, y - 30), fill=SK, width=22, joint="curve")
        d.rounded_rectangle((x + 20, y - 70, x + 60, y), radius=8, fill=BLACK)
    else:  # happy, arms holding the dog
        d.line((x - 50, y + 90, x - 20, y + 150, x + 40, y + 150), fill=SK, width=22, joint="curve")
        d.line((x + 50, y + 90, x + 70, y + 160), fill=SK, width=22)
    d.ellipse((x - 52, y - 60, x + 52, y + 55), fill=SK, outline=BLACK, width=6)  # head
    d.chord((x - 54, y - 66, x + 54, y + 20), 180, 360, fill=hair)  # hair
    if mode == "panic":
        d.ellipse((x - 30, y - 12, x - 8, y + 12), fill=WHITE, outline=BLACK, width=3)
        d.ellipse((x + 8, y - 12, x + 30, y + 12), fill=WHITE, outline=BLACK, width=3)
        d.ellipse((x - 14, y + 24, x + 14, y + 46), fill=(90, 20, 20))
        for i in range(3):  # panic lines
            a = -math.pi / 2 + (i - 1) * 0.6
            d.line((x + 90 * math.cos(a), y - 20 + 90 * math.sin(a), x + 130 * math.cos(a), y - 20 + 130 * math.sin(a)), fill=BLACK, width=6)
    else:
        d.arc((x - 30, y - 14, x - 8, y + 6), 200, 340, fill=BLACK, width=5)
        d.arc((x + 8, y - 14, x + 30, y + 6), 200, 340, fill=BLACK, width=5)
        d.arc((x - 24, y + 8, x + 24, y + 42), 20, 160, fill=BLACK, width=6)


def lockman_layer(cape_phase=0.0, arm="side", s=1.0):
    """Original drawing of the Lockman hero (black suit, blue cape, yellow lock emblem). Feet at bottom center."""
    L = Image.new("RGBA", (520, 720), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    cx = 260
    flap = math.sin(cape_phase) * 30
    d.polygon([(cx - 90, 230), (cx + 90, 230), (cx + 150 + flap, 640), (cx + 40, 610 + flap / 2), (cx - 40, 640), (cx - 150 - flap / 2, 610)], fill=BLUE, outline=BLACK)
    d.line([(cx - 90, 230), (cx - 150 - flap / 2, 610)], fill=BLUE_D, width=10)
    d.rectangle((cx - 62, 470, cx - 10, 680), fill=BLACK, outline=(50, 50, 60), width=4)  # legs
    d.rectangle((cx + 10, 470, cx + 62, 680), fill=BLACK, outline=(50, 50, 60), width=4)
    d.rounded_rectangle((cx - 68, 620, cx - 4, 700), radius=14, fill=BLUE, outline=BLACK, width=5)  # boots
    d.rounded_rectangle((cx + 4, 620, cx + 68, 700), radius=14, fill=BLUE, outline=BLACK, width=5)
    d.polygon([(cx - 105, 240), (cx + 105, 240), (cx + 70, 480), (cx - 70, 480)], fill=BLACK, outline=(55, 55, 65))  # torso
    d.arc((cx - 80, 250, cx - 4, 330), 20, 160, fill=(60, 60, 70), width=5)
    d.arc((cx + 4, 250, cx + 80, 330), 20, 160, fill=(60, 60, 70), width=5)
    d.rectangle((cx - 72, 450, cx + 72, 480), fill=BLUE, outline=BLACK, width=4)  # belt
    d.rectangle((cx - 16, 452, cx + 16, 478), fill=YELLOW)
    # chest emblem: yellow diamond with lock
    d.polygon([(cx - 62, 300), (cx - 40, 272), (cx + 40, 272), (cx + 62, 300), (cx, 392)], fill=YELLOW, outline=BLACK)
    d.line([(cx - 62, 300), (cx - 40, 272), (cx + 40, 272), (cx + 62, 300), (cx, 392), (cx - 62, 300)], fill=BLACK, width=5)
    d.arc((cx - 18, 288, cx + 18, 326), 180, 360, fill=BLACK, width=7)
    d.rounded_rectangle((cx - 24, 306, cx + 24, 346), radius=6, fill=BLACK)
    d.ellipse((cx - 6, 316, cx + 6, 328), fill=YELLOW)
    # arms
    if arm == "up":  # flying: both arms forward/up
        d.line((cx + 95, 260, cx + 140, 150, cx + 150, 40), fill=BLACK, width=40, joint="curve")
        d.ellipse((cx + 128, 10, cx + 172, 54), fill=SKIN, outline=BLACK, width=4)
        d.line((cx - 95, 260, cx - 150, 380), fill=BLACK, width=40)
    elif arm == "thumb":
        d.line((cx + 95, 260, cx + 160, 300, cx + 175, 200), fill=BLACK, width=40, joint="curve")
        d.ellipse((cx + 152, 170, cx + 198, 216), fill=SKIN, outline=BLACK, width=4)
        d.rectangle((cx + 168, 132, cx + 184, 178), fill=SKIN, outline=BLACK, width=3)
        d.line((cx - 95, 260, cx - 130, 450), fill=BLACK, width=40)
    elif arm == "work":
        d.line((cx - 95, 260, cx - 150, 330, cx - 200, 310), fill=BLACK, width=40, joint="curve")
        d.line((cx - 200, 310, cx - 250, 300), fill=(170, 170, 180), width=10)  # pick tool
        d.line((cx + 95, 260, cx + 120, 450), fill=BLACK, width=40)
    else:
        d.line((cx - 95, 260, cx - 130, 450), fill=BLACK, width=40)
        d.line((cx + 95, 260, cx + 130, 450), fill=BLACK, width=40)
    # head
    d.rectangle((cx - 26, 200, cx + 26, 245), fill=SKIN)
    d.ellipse((cx - 70, 70, cx + 70, 225), fill=SKIN, outline=BLACK, width=6)
    d.chord((cx - 74, 58, cx + 74, 170), 180, 360, fill=BLACK)  # hair
    d.polygon([(cx - 74, 112), (cx - 20, 70), (cx + 30, 64), (cx + 74, 112)], fill=BLACK)
    d.chord((cx - 66, 140, cx + 66, 232), 0, 180, fill=(70, 45, 30))  # short beard
    d.rounded_rectangle((cx - 72, 118, cx + 72, 160), radius=18, fill=BLACK)  # mask
    d.ellipse((cx - 50, 126, cx - 14, 152), fill=WHITE)
    d.ellipse((cx + 14, 126, cx + 50, 152), fill=WHITE)
    d.chord((cx - 34, 170, cx + 34, 214), 0, 180, fill=WHITE, outline=BLACK, width=4)  # big grin
    return L.resize((int(520 * s), int(720 * s)))


def paste_lockman(img, x, y, angle=0.0, **kw):
    L = lockman_layer(**kw)
    if angle:
        L = L.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(L, (int(x - L.size[0] / 2), int(y - L.size[1])))


def hearts(img, cx, cy, t):
    d = ImageDraw.Draw(img)
    for i in range(6):
        k = (t * 0.8 + i / 6) % 1
        x = cx + math.sin(i * 2.1 + t * 2) * 140
        y = cy - k * 380
        r = 26 * (1 - k * 0.4)
        a = int(255 * (1 - k))
        d.ellipse((x - r, y - r, x, y), fill=(230, 40, 70, a))
        d.ellipse((x, y - r, x + r, y), fill=(230, 40, 70, a))
        d.polygon([(x - r, y - r / 2), (x + r, y - r / 2), (x, y + r)], fill=(230, 40, 70, a))


def speed_lines(img, cx, cy, ang, n=10):
    d = ImageDraw.Draw(img)
    for i in range(n):
        off = (i - n / 2) * 26
        x0 = cx + off * math.cos(ang + math.pi / 2)
        y0 = cy + off * math.sin(ang + math.pi / 2)
        L = 200 + (i % 3) * 80
        d.line((x0, y0, x0 - L * math.cos(ang), y0 - L * math.sin(ang)), fill=(255, 255, 255, 200), width=6)


# ------------------------------------------------------------------ scenes
def frame(t):
    if t < 5.0:  # owner panics, dog barking inside the car
        img = day_street(t)
        shake = math.sin(t * 50) * 3 if int(t * 3) % 2 == 0 else 0
        draw_car(img, shake=shake)
        draw_dog(img, 690 + shake, 1165, 0.9, bark=t)
        draw_owner(img, 150, 1110, t, "panic")
        caption(img, "SAN FRANCISCO, 2:14 PM", seg(t, 0.1, 1.2))
        for at, (bx, by) in ((0.5, (860, 1000)), (2.0, (900, 940)), (3.6, (840, 980))):
            if at < t < at + 0.7:
                burst(img, bx, by, 120, "WOOF!", appear=seg(t, at, at + 0.35), rot=at)
        if t > 0.9:
            lines = ["MY DOG IS LOCKED", "IN THE CAR!"] if t < 2.9 else ["AND THE KEYS", "ARE INSIDE!!"]
            bubble(img, 40, 600, 640, lines, (190, 1040), appear=seg(t, 0.9 if t < 2.9 else 2.9, (0.9 if t < 2.9 else 2.9) + 0.3))
        return img
    if t < 6.4:  # calls Lockman
        img = day_street(t)
        draw_car(img)
        draw_dog(img, 690, 1165, 0.9, bark=t)
        draw_owner(img, 150, 1110, t, "phone")
        bubble(img, 40, 640, 660, ["I NEED LOCKMAN!"], (200, 1040), appear=seg(t, 5.05, 5.35))
        return img
    if t < 9.0:  # the Lockman signal in the sky
        z = 0.85 + 0.25 * ease(seg(t, 6.4, 9.0))
        img = night_sky(t, z)
        caption(img, "THE LOCKMAN SIGNAL!", seg(t, 6.8, 7.6), y=1080)
        flash = 1 - seg(t, 6.4, 6.8)
        if flash > 0:
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(220 * flash))))
        return img
    if t < 12.6:  # Lockman flies down from the sky
        img = day_street(t)
        draw_car(img)
        draw_dog(img, 690, 1165, 0.9, bark=t)
        draw_owner(img, 150, 1110, t, "phone" if t < 10.5 else "panic")
        k = ease(seg(t, 9.0, 11.4))
        x, y = lerp(1250, 960, k), lerp(-150, GROUND_Y + 10, k)
        if k < 1:
            speed_lines(img, x - 40, y - 250, math.atan2(GROUND_Y + 160, -290))
            paste_lockman(img, x, y, angle=lerp(35, 0, k ** 3), cape_phase=t * 14, arm="up", s=0.62)
            burst(img, 820, 520, 190, "WHOOSH!", appear=seg(t, 9.4, 9.8), rot=0.3)
        else:
            paste_lockman(img, 960, GROUND_Y + 10, cape_phase=t * 4, s=0.62)
            d = ImageDraw.Draw(img)
            dust = seg(t, 11.4, 12.0)
            for i in range(6):
                r = 30 + 60 * dust
                d.ellipse((960 + (i - 2.5) * 50 - r / 2, GROUND_Y - r / 3, 960 + (i - 2.5) * 50 + r / 2, GROUND_Y + r / 3), fill=(230, 230, 230, int(200 * (1 - dust))))
            bubble(img, 420, 620, 640, ["LOCKMAN IS HERE!"], (900, 1000), appear=seg(t, 11.5, 11.8))
        return img
    if t < 17.8:  # careful entry, door opens, dog jumps out
        img = day_street(t)
        door = ease(seg(t, 14.4, 15.0))
        ox = draw_car(img, door=door)
        jump = seg(t, 15.0, 16.0)
        if jump <= 0:
            draw_dog(img, 690, 1165, 0.9, bark=t)
        draw_owner(img, 150, 1110, t, "panic" if t < 15.6 else "happy")
        walk = ease(seg(t, 12.6, 13.4))
        paste_lockman(img, lerp(960, 880, walk), GROUND_Y + 10, cape_phase=t * 4, arm="work" if t < 14.4 else "side", s=0.62)
        caption(img, "SAFE ENTRY. NO DAMAGE.", seg(t, 13.2, 14.0))
        burst(img, 560, 1000, 150, "CLICK!", appear=seg(t, 14.0, 14.3) if t < 14.45 else 0, rot=0.6)
        if 14.4 < t < 15.15:
            burst(img, 700, 900, 200, "UNLOCKED!", appear=seg(t, 14.45, 14.8), rot=1.1)
        if jump > 0:
            jx = lerp(560, 230, jump)
            jy = lerp(1170, 1240, jump) - math.sin(jump * math.pi) * 330
            draw_dog(img, jx, jy, 0.85, bark=t, happy=True, tongue=True)
        if t > 16.0:
            hearts(img, 220, 1100, t)
        return img
    if t < 21.6:  # thank you
        img = day_street(t)
        draw_car(img, door=1.0)
        draw_owner(img, 150, 1110, t, "happy")
        draw_dog(img, 225, 1225, 0.8, bark=t, happy=True, tongue=True)
        hearts(img, 220, 1080, t)
        paste_lockman(img, 800, GROUND_Y + 10, cape_phase=t * 4, arm="thumb" if t > 19.0 else "side", s=0.66)
        bubble(img, 30, 560, 560, ["THANK YOU,", "LOCKMAN!"], (190, 1040), appear=seg(t, 17.9, 18.2))
        if t > 19.2:
            bubble(img, 450, 330, 600, ["ANOTHER DAY,", "ANOTHER RESCUE!"], (800, 960), appear=seg(t, 19.2, 19.5))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 1800, W, H), fill=(0, 0, 0, 180))
        text_c(d, W / 2, 1822, "Pet in danger in a hot car? Call 911 first.", F[38], fill=WHITE)
        return img
    # end card
    img = night_sky(t, 1.05)
    d = ImageDraw.Draw(img)
    a = ease(seg(t, 21.6, 22.4))
    panel = Image.new("RGBA", (W, H), (0, 0, 0, int(170 * a)))
    img.alpha_composite(panel)
    d.rounded_rectangle((W / 2 - 330, 270, W / 2 + 330, 850), radius=40, fill=(255, 255, 255, int(235 * a)), outline=YELLOW, width=8)
    lg = logo.resize((int(560 * (0.8 + 0.2 * a)), int(513 * (0.8 + 0.2 * a))))
    img.alpha_composite(lg, (int(W / 2 - lg.size[0] / 2), 300))
    rows = [("24/7 SAN FRANCISCO LOCKSMITH", F[54], YELLOW, 22.3), ("Home  •  Car  •  Business Lockouts", F[46], WHITE, 22.7),
            ("30 years of family experience", F[46], WHITE, 23.1), ("(415) 806-7343", F[92], YELLOW, 23.5), ("lockmanasaplocksmith.com", F[54], WHITE, 23.9)]
    y = 900
    for s_, f, c, at in rows:
        k = ease(seg(t, at, at + 0.4))
        if k > 0:
            text_c(d, W / 2, y + (1 - k) * 40, s_, f, fill=c + (int(255 * k),), stroke=4, stroke_fill=BLACK)
        y += f.size + 46
    return img


def main():
    global HALF_DARK
    HALF_DARK = halftone(None or Image.new("RGBA", (W, H)), (255, 255, 255, 14))
    events = [("bark", 0.5), ("bark", 0.75), ("bark", 2.0), ("bark", 2.2), ("bark", 3.6), ("whoosh", 6.4), ("whoosh", 9.2),
              ("click", 14.2), ("click", 14.32), ("bark", 15.3), ("chime", 21.6)]
    wav = OUT / "audio.wav"
    music.render(TOTAL, events, str(wav))
    mp4 = OUT / "lockman-rescue.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-shortest", "-movflags", "+faststart", str(mp4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(TOTAL * FPS)
    only = [float(a) for a in sys.argv[1:]]
    if only:
        p.kill()
        for a in only:
            frame(a).convert("RGB").save(OUT / f"f_{a:05.2f}.png")
        return
    for i in range(n):
        p.stdin.write(frame(i / FPS).convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    print(mp4)


if __name__ == "__main__":
    main()
