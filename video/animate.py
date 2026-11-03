"""Turn the owner's own comic images into a vertical LOCKMAN video (1080x1920, 24 fps).

Usage: python3 -m video.animate OUT.mp4 IMG1 [IMG2 ...] [--caption "TEXT" ...]
Each image gets ~4.5 s of camera motion (alternating push-in / pull-out). Dark (night) images get
rain and warm light glows; bright images get drifting seagulls and a soft sparkle. The video opens
with the LOCKMAN signal in the night sky and ends with the business card. Music: the site's
original Lockman theme (video/theme.py) plus original sound effects.
"""
import argparse
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from video import music, render as R, theme

W, H, FPS = R.W, R.H, R.FPS
INTRO, PER_IMAGE, OUTRO = 3.4, 4.6, 5.6
rng = np.random.default_rng(5)
RAIN = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(900, 1500)) for _ in range(150)]


def load(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if im.size[1] < H * 0.6:  # small image: upscale so the motion stays sharp enough
        k = H * 0.6 / im.size[1]
        im = im.resize((int(im.size[0] * k), int(im.size[1] * k)), Image.LANCZOS)
    return im


def is_dark(im):
    return np.asarray(im.resize((64, 64)).convert("L")).mean() < 95


def view(src, x, start, end):
    k = R.ease(x)
    cx, cy, z = (R.lerp(a, b, k) for a, b in zip(start, end))
    cover = max(H / src.size[1], W / src.size[0])
    cw, ch = W / (cover * z), H / (cover * z)
    cx = min(max(cx, cw / 2), src.size[0] - cw / 2)
    cy = min(max(cy, ch / 2), src.size[1] - ch / 2)
    return src.resize((W, H), box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2), resample=Image.BILINEAR).convert("RGBA")


def rain(img, t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x0, y0, sp in RAIN:
        y = (y0 + t * sp) % (H + 100) - 50
        x = (x0 - t * sp * 0.15) % W
        d.line((x, y, x - 8, y + 46), fill=(200, 215, 255, 100), width=3)
    img.alpha_composite(layer)


def glows(img, t, spots):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, (x, y) in enumerate(spots):
        a = int(55 + 40 * math.sin(t * 7 + i * 1.7))
        d.ellipse((x - 140, y - 140, x + 140, y + 140), fill=(255, 150, 50, a))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(40)))


def bright_spots(frame_rgb, n=6):
    """Find the brightest warm spots (lanterns, street lamps) to make them flicker."""
    small = np.asarray(frame_rgb.resize((54, 96)).convert("RGB")).astype(float)
    score = small[..., 0] + small[..., 1] * 0.6 - small[..., 2] * 0.5
    spots = []
    for _ in range(n):
        y, x = np.unravel_index(np.argmax(score), score.shape)
        if score[y, x] < 200:
            break
        spots.append((x * 20 + 10, y * 20 + 10))
        score[max(0, y - 6):y + 7, max(0, x - 6):x + 7] = -1e9
    return spots


def seagulls(img, t):
    d = ImageDraw.Draw(img)
    for i in range(4):
        x = (i * 300 + t * (60 + i * 15)) % (W + 200) - 100
        y = 240 + i * 80 + math.sin(t * 2 + i) * 20
        f = math.sin(t * 8 + i) * 14
        d.line((x - 30, y - f, x, y, x + 30, y - f), fill=(245, 245, 245), width=6, joint="curve")


def vignette():
    v = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(v)
    for i in range(30):
        d.rounded_rectangle((i * 10, i * 14, W - i * 10, H - i * 14), radius=200, outline=max(0, 110 - i * 5), width=14)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(v.filter(ImageFilter.GaussianBlur(30)))
    return layer


def flash(img, x):
    if x > 0:
        img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * x))))


def make(out, images, captions=()):
    R.HALF_DARK = R.halftone(Image.new("RGBA", (W, H)), (255, 255, 255, 14))
    vig = vignette()
    srcs = [load(p) for p in images]
    moves = []
    for i, s in enumerate(srcs):
        cx, cy = s.size[0] / 2, s.size[1] / 2
        wide, close = (cx, cy, 1.0), (cx, s.size[1] * 0.3, 1.35)  # faces/speech bubbles sit in the upper third
        moves.append((wide, close) if i % 2 == 0 else (close, wide))
    dark = [is_dark(s) for s in srcs]
    spots = [bright_spots(view(s, 0.5, *moves[i]).convert("RGB")) if dark[i] else [] for i, s in enumerate(srcs)]
    total = INTRO + PER_IMAGE * len(srcs) + OUTRO
    end_start = INTRO + PER_IMAGE * len(srcs)

    def frame(t):
        if t < INTRO:
            img = R.night_sky(t, 0.8 + 0.25 * R.ease(t / INTRO))
            R.caption(img, "SAN FRANCISCO NEEDS...", R.seg(t, 0.3, 1.3), y=1060)
            if t > 1.9:
                R.burst(img, W / 2, 1300, 230, "LOCKMAN!", appear=R.seg(t, 1.9, 2.3), rot=0.4)
            flash(img, 1 - R.seg(t, 0, 0.35))
            return img
        if t < end_start:
            i = int((t - INTRO) // PER_IMAGE)
            x = (t - INTRO - i * PER_IMAGE) / PER_IMAGE
            img = view(srcs[i], x, *moves[i])
            if dark[i]:
                glows(img, t, spots[i])
                rain(img, t)
            else:
                seagulls(img, t)
            img.alpha_composite(vig)
            if i < len(captions) and captions[i]:
                R.caption(img, captions[i], R.seg(x, 0.05, 0.3), y=1720)
            flash(img, 1 - R.seg(x, 0, 0.07))
            return img
        img = R.frame(21.6 + (t - end_start))  # business end card
        flash(img, 1 - R.seg(t, end_start, end_start + 0.35))
        return img

    events = [("whoosh", 0.1), ("chime", 1.9)] + [("whoosh", INTRO + i * PER_IMAGE - 0.1) for i in range(len(srcs))] + [("chime", end_start)]
    sfx = np.zeros(int((total + 1) * music.SR))
    r2 = np.random.default_rng(7)
    for kind, at in events:
        s = {"whoosh": lambda: music.whoosh(r2), "chime": music.chime}[kind]()
        music.add(sfx, s * 0.8, at)
    wav = Path(out).with_suffix(".wav")
    theme.render_theme(total, str(wav), sfx)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(int(total * FPS)):
        p.stdin.write(frame(n / FPS).convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink(missing_ok=True)
    poster = Path(out).with_suffix(".jpg")
    view(srcs[0], 0.0, *moves[0]).convert("RGB").resize((540, 960)).save(poster, quality=85)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--caption", action="append", default=[])
    a = ap.parse_args()
    print(make(a.out, a.images, a.caption))
