"""Running-comic LOCKMAN video: a tenant is locked out, calls Lockman, the signal lights up the sky,
Lockman answers "I'll be there shortly!", drives over in the real Lockman van (comic version of the
owner's photo) and lets the tenant back in safely.

Usage: python3 -m video.comic_van OUT.mp4 VAN_PHOTO.jpg
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from video import music, render as R, theme

W, H, FPS = R.W, R.H, R.FPS
END = 27.6          # end card starts
TOTAL = END + 5.6
WALL = (92, 70, 120)


def comicify(path):
    """Turn a real photo into comic art: flat posterized colors, boosted saturation, bold ink outlines."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    k = 1400 / max(im.size)
    im = im.resize((int(im.size[0] * k), int(im.size[1] * k)), Image.LANCZOS)
    smooth = im.filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.SMOOTH_MORE)
    from PIL import ImageEnhance
    flat = ImageOps.posterize(ImageEnhance.Color(smooth).enhance(1.6), 4)
    flat = ImageEnhance.Contrast(flat).enhance(1.15)
    edges = smooth.convert("L").filter(ImageFilter.GaussianBlur(1.5)).filter(ImageFilter.FIND_EDGES)
    ink = edges.point(lambda v: 255 if v > 22 else 0).filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MaxFilter(3))
    # keep the yellow van lettering crisp: no ink on bright yellow pixels
    a = np.asarray(im).astype(int)
    yellow = ((a[..., 0] > 170) & (a[..., 1] > 140) & (a[..., 2] < 110)).astype(np.uint8) * 255
    ink.paste(0, (0, 0), Image.fromarray(yellow).filter(ImageFilter.MaxFilter(5)))
    out = flat.copy()
    out.paste((12, 12, 18), (0, 0), ink)
    return out


def hallway(t):
    """Apartment hallway at night: purple wall, wooden door with a lock, floor and a lamp."""
    img = Image.new("RGBA", (W, H), WALL + (255,))
    d = ImageDraw.Draw(img)
    for y in range(0, R.GROUND_Y, 6):
        k = y / R.GROUND_Y
        d.rectangle((0, y, W, y + 6), fill=(int(R.lerp(60, 100, k)), int(R.lerp(45, 76, k)), int(R.lerp(90, 130, k))))
    d.rectangle((0, R.GROUND_Y, W, H), fill=(120, 80, 50))
    for x in range(-200, W + 200, 140):
        d.line((x, R.GROUND_Y, x + 160, H), fill=(95, 62, 38), width=5)
    d.rectangle((0, R.GROUND_Y - 30, W, R.GROUND_Y), fill=(60, 40, 30), outline=R.BLACK, width=5)
    # wall lamp glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    a = int(110 + 25 * math.sin(t * 5))
    g.ellipse((780, 260, 1080, 560), fill=(255, 200, 110, a))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(50)))
    d.polygon([(890, 380), (970, 380), (990, 450), (870, 450)], fill=(250, 220, 140), outline=R.BLACK)
    d.rectangle((920, 450, 940, 480), fill=R.BLACK)
    # apartment number plate
    d.rounded_rectangle((470, 470, 610, 540), radius=12, fill=R.YELLOW, outline=R.BLACK, width=5)
    R.text_c(d, 540, 478, "4B", R.F[46])
    img.alpha_composite(R.HALF_DARK)
    return img


def door(img, opened=0.0, glow=0.0):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 360, 580, 720, R.GROUND_Y - 30
    d.rectangle((x0 - 24, y0 - 24, x1 + 24, y1), fill=(235, 225, 210), outline=R.BLACK, width=6)  # frame
    if opened > 0:  # warm light from inside
        d.rectangle((x0, y0, x1, y1), fill=(255, 220, 140))
    w = (x1 - x0) * (1 - 0.75 * opened)
    d.rectangle((x0, y0, x0 + w, y1), fill=(150, 90, 45), outline=R.BLACK, width=6)
    if w > 120:
        for py in (y0 + 40, y0 + 380):
            d.rectangle((x0 + 30, py, x0 + w - 30, py + 300), outline=(110, 62, 28), width=6)
        kx, ky = x0 + w - 60, (y0 + y1) / 2
        if glow > 0:
            gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(gl).ellipse((kx - 70, ky - 70, kx + 70, ky + 70), fill=(255, 240, 120, int(200 * glow)))
            img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(18)))
            d = ImageDraw.Draw(img)
        d.ellipse((kx - 26, ky - 26, kx + 26, ky + 26), fill=(215, 185, 70), outline=R.BLACK, width=5)
        d.rounded_rectangle((kx - 18, ky + 50, kx + 18, ky + 110), radius=8, fill=(215, 185, 70), outline=R.BLACK, width=4)
        d.ellipse((kx - 6, ky + 66, kx + 6, ky + 78), fill=R.BLACK)


def phone_rings(img, t, at, x, y):
    if at < t < at + 1.4:
        ph = int((t - at) * 6) % 2
        R.burst(img, x, y, 150, "RING!" if ph == 0 else "RING!!", appear=R.seg(t, at, at + 0.25), rot=at + ph * 0.3)


def lockman_hq(t):
    """Lockman at his HQ, answering the phone, signal light behind him."""
    img = R.night_sky(t, 0.75)
    shade = Image.new("RGBA", (W, H), (10, 20, 60, 120))
    img.alpha_composite(shade)
    R.paste_lockman(img, W / 2, 1720, cape_phase=t * 4, arm="thumb" if t > 9.6 else "side", s=1.25)
    d = ImageDraw.Draw(img)
    # phone at his ear
    d.rounded_rectangle((W / 2 + 50, 980, W / 2 + 105, 1080), radius=10, fill=R.BLACK, outline=(90, 90, 100), width=4)
    return img


def van_scene(van, t, a, b):
    x = R.seg(t, a, b)
    z = R.lerp(1.0, 1.18, R.ease(x))
    cover = max(H / van.size[1], W / van.size[0])
    cw, ch = W / (cover * z), H / (cover * z)
    cx = R.lerp(van.size[0] * 0.40, van.size[0] * 0.52, R.ease(x))
    cy = R.lerp(van.size[1] * 0.5, van.size[1] * 0.36, R.ease(x))
    cx = min(max(cx, cw / 2), van.size[0] - cw / 2)
    cy = min(max(cy, ch / 2), van.size[1] - ch / 2)
    cy = min(max(cy + math.sin(t * 40) * 4, ch / 2), van.size[1] - ch / 2)
    img = van.resize((W, H), box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2), resample=Image.BILINEAR).convert("RGBA")
    for i in range(12):  # motion streaks
        yy = 300 + i * 120 + (i % 3) * 30
        L = 260 + (i % 4) * 90
        off = (t * 1800 + i * 210) % (W + L)
        ImageDraw.Draw(img).line((W - off, yy, W - off + L, yy), fill=(255, 255, 255, 170), width=7)
    return img


def frame(t, van):
    if t < 4.6:  # tenant locked out in the hallway
        img = hallway(t)
        door(img)
        R.draw_owner(img, 860, 1150, t, "panic", shirt=(200, 90, 40), hair=(30, 25, 25))
        R.caption(img, "SAN FRANCISCO, 11:48 PM", R.seg(t, 0.1, 1.2))
        if t > 0.9:
            lines = ["I'M LOCKED OUT", "OF MY APARTMENT!"] if t < 2.8 else ["KEYS ARE", "INSIDE!!"]
            st = 0.9 if t < 2.8 else 2.8
            R.bubble(img, 360, 230 + 160, 680, lines, (860, 1080), appear=R.seg(t, st, st + 0.3))
        return img
    if t < 7.0:  # calls Lockman
        img = hallway(t)
        door(img)
        R.draw_owner(img, 860, 1150, t, "phone", shirt=(200, 90, 40), hair=(30, 25, 25))
        R.bubble(img, 330, 380, 700, ["CALLING LOCKMAN...", "(415) 806-7343"], (860, 1080), appear=R.seg(t, 4.7, 5.0))
        return img
    if t < 8.4:  # the signal lights up
        img = R.night_sky(t, 0.85 + 0.25 * R.ease(R.seg(t, 7.0, 8.4)))
        R.caption(img, "THE LOCKMAN SIGNAL!", R.seg(t, 7.2, 7.8), y=1080)
        phone_rings(img, t, 7.0, 820, 1350)
        f = 1 - R.seg(t, 7.0, 7.35)
        if f > 0:
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(220 * f))))
        return img
    if t < 12.4:  # Lockman answers
        img = lockman_hq(t)
        phone_rings(img, t, 8.4, 850, 700)
        if t > 9.0:
            R.bubble(img, 90, 260, 900, ["I'LL BE THERE", "SHORTLY!"], (W / 2 + 40, 860), font=R.F[76], appear=R.seg(t, 9.0, 9.3))
        return img
    if t < 17.4:  # the real Lockman van on the way
        img = van_scene(van, t, 12.4, 17.4)
        R.caption(img, "ON THE WAY!", R.seg(t, 12.6, 13.3), y=1720)
        R.burst(img, 820, 330, 190, "VROOM!", appear=R.seg(t, 13.0, 13.4), rot=0.5)
        f = 1 - R.seg(t, 12.4, 12.7)
        if f > 0:
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(220 * f))))
        return img
    if t < 22.6:  # safe entry
        img = hallway(t)
        opened = R.ease(R.seg(t, 20.6, 21.4))
        door(img, opened=opened, glow=R.seg(t, 19.0, 19.8) * (1 - opened))
        walk = R.ease(R.seg(t, 17.4, 18.4))
        R.paste_lockman(img, R.lerp(1250, 900, walk), R.GROUND_Y + 10, cape_phase=t * 4,
                        arm="work" if 18.4 < t < 20.6 else "side", s=0.62)
        R.draw_owner(img, 170, 1150, t, "panic" if t < 21.0 else "happy", shirt=(200, 90, 40), hair=(30, 25, 25), s=0.9)
        R.caption(img, "SAFE ENTRY. NO DAMAGE.", R.seg(t, 18.6, 19.4))
        if 19.8 < t < 20.6:
            R.burst(img, 640, 860, 150, "CLICK!", appear=R.seg(t, 19.8, 20.1), rot=0.6)
        if 20.5 < t < 21.6:
            R.burst(img, 560, 760, 210, "OPEN!", appear=R.seg(t, 20.5, 20.85), rot=1.1)
        if t > 21.2:
            R.hearts(img, 200, 1100, t)
        return img
    # thank you
    img = hallway(t)
    door(img, opened=1.0)
    R.draw_owner(img, 230, 1150, t, "happy", shirt=(200, 90, 40), hair=(30, 25, 25))
    R.hearts(img, 230, 1080, t)
    R.paste_lockman(img, 830, R.GROUND_Y + 10, cape_phase=t * 4, arm="thumb" if t > 24.4 else "side", s=0.66)
    R.bubble(img, 30, 560, 600, ["THANK YOU,", "LOCKMAN!"], (230, 1080), appear=R.seg(t, 22.7, 23.0))
    if t > 24.6:
        R.bubble(img, 420, 300, 640, ["HAPPY TO HELP,", "ANY TIME, 24/7!"], (830, 960), appear=R.seg(t, 24.6, 24.9))
    f = R.seg(t, END - 0.3, END)
    if f > 0:
        img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * f))))
    return img


def make(out, van_photo):
    R.HALF_DARK = R.halftone(Image.new("RGBA", (W, H)), (255, 255, 255, 14))
    van = comicify(van_photo)
    van.save(Path(out).with_name(Path(out).stem + "-van-comic.jpg"), quality=90)
    sfx = np.zeros(int((TOTAL + 1) * music.SR))
    r2 = np.random.default_rng(7)
    for kind, at in [("chime", 7.0), ("chime", 7.5), ("chime", 8.5), ("whoosh", 12.3), ("whoosh", 13.0),
                     ("click", 19.9), ("click", 20.05), ("chime", 20.6), ("chime", END)]:
        s = {"whoosh": lambda: music.whoosh(r2), "chime": music.chime, "click": music.click}[kind]()
        music.add(sfx, s * 0.8, at)
    wav = Path(out).with_suffix(".wav")
    theme.render_theme(TOTAL, str(wav), sfx)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", str(out)]
    only = [float(a) for a in sys.argv[3:]]
    if only:
        for a in only:
            frame(a, van).convert("RGB").save(Path(out).with_name(f"f_{a:05.2f}.png"))
        return
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(int(TOTAL * FPS)):
        t = n / FPS
        img = frame(t, van) if t < END else R.frame(21.6 + (t - END))
        p.stdin.write(img.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink(missing_ok=True)
    frame(9.8, van).convert("RGB").resize((540, 960)).save(Path(out).with_suffix(".jpg"), quality=85)
    return out


if __name__ == "__main__":
    print(make(sys.argv[1], sys.argv[2]))
