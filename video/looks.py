"""Real-photo looks for LOCKMAN videos: 1080x1920, 30 fps, graded, with film grain and vignette.

Looks (pick a different one each video):
  cinematic     slow push / pan, warm grade, soft light leaks, blur-dissolves, serif captions
  documentary   handheld drift, quick cuts with a flash, bold lower-third titles
  before-after  pairs of photos revealed with a sliding wipe and a split line
  macro         tight crops on lock parts, rack-focus pull, slow creeping zoom, cool steel grade
  reel          punchy beat-synced cuts, zoom punches, kinetic word-by-word text

Backgrounds (intro plate + outro card): steel-dusk, fog-morning, golden-sunset, night-bokeh,
concrete-day, blurred-photo.  Caption styles: mono-top, clean-lower-left, bold-lower-third,
serif-center, kinetic-pop.

Images are never enlarged past their real resolution: each shot's zoom is capped so the crop
still has at least as many pixels as the output frame.
"""
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from video import moods, music

W, H, FPS = 1080, 1920, 30
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = Path("/usr/share/fonts")
LOOKS = ("cinematic", "documentary", "before-after", "macro", "reel")
BACKGROUNDS = ("steel-dusk", "fog-morning", "golden-sunset", "night-bokeh", "concrete-day", "blurred-photo")
CAPTION_STYLES = ("mono-top", "clean-lower-left", "bold-lower-third", "serif-center", "kinetic-pop")
YELLOW = (242, 194, 0)


def font(name, size):
    paths = {
        "inter-semibold": "opentype/inter/Inter-SemiBold.otf",
        "inter-bold": "opentype/inter/Inter-Bold.otf",
        "inter-black": "opentype/inter/Inter-Black.otf",
        "inter-light": "opentype/inter/InterDisplay-Light.otf",
        "mono": "truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "serif": "truetype/dejavu/DejaVuSerif-Bold.ttf",
    }
    for p in (FONTS / paths.get(name, ""), FONTS / "truetype/dejavu/DejaVuSans-Bold.ttf"):
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def ease(x):  # smootherstep: gentle start and stop, like a real camera operator
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def seg(t, a, b):
    return max(0.0, min(1.0, (t - a) / (b - a)))


# ------------------------------------------------------------------ look settings
LOOK = {
    "cinematic": dict(shot=4.6, trans="blur-dissolve", tlen=0.7, zoom=(1.0, 1.18), shake=0, grade="warm", grain=7,
                      leaks=True, rack=False, caption="serif-center", bars=True),
    "documentary": dict(shot=3.6, trans="flash-cut", tlen=0.18, zoom=(1.05, 1.15), shake=6, grade="neutral", grain=9,
                        leaks=False, rack=False, caption="bold-lower-third", bars=False),
    "before-after": dict(shot=4.4, trans="wipe", tlen=0.8, zoom=(1.0, 1.08), shake=0, grade="clean", grain=5,
                         leaks=False, rack=False, caption="clean-lower-left", bars=False),
    "macro": dict(shot=4.3, trans="focus-dissolve", tlen=0.6, zoom=(1.25, 1.7), shake=1.2, grade="steel", grain=5,
                  leaks=False, rack=True, caption="mono-top", bars=False),
    "reel": dict(shot=2.4, trans="zoom-punch", tlen=0.22, zoom=(1.0, 1.22), shake=0, grade="punchy", grain=6,
                 leaks=False, rack=False, caption="kinetic-pop", bars=False),
}

GRADES = {  # (lift rgb, gain rgb, contrast, saturation)
    "warm": ((10, 4, -4), (1.04, 0.99, 0.90), 1.10, 1.05),
    "neutral": ((2, 2, 2), (1.0, 1.0, 0.98), 1.06, 1.0),
    "clean": ((0, 0, 0), (1.02, 1.01, 1.0), 1.04, 1.06),
    "steel": ((-2, 6, 14), (1.03, 1.0, 0.95), 1.14, 0.88),  # teal shadows, warm metal highlights
    "punchy": ((0, 0, 4), (1.03, 1.0, 1.0), 1.18, 1.18),
}


def make_lut(grade):
    lift, gain, contrast, _ = GRADES[grade]
    x = np.arange(256) / 255.0
    s = 0.5 + (x - 0.5) * contrast
    s = np.clip(s, 0, 1)
    s = s * s * (3 - 2 * s) * 0.35 + s * 0.65  # soft filmic S-curve
    luts = []
    for c in range(3):
        y = s * gain[c] * 255 + lift[c] * (1 - x) ** 2
        luts.append(np.clip(y, 0, 255).astype(np.uint8))
    return np.stack(luts, axis=1)  # (256, 3)


class Finisher:
    """Colour grade, saturation, vignette and moving film grain on every frame."""

    def __init__(self, grade, grain, vignette=0.42, seed=4):
        self.lut = make_lut(grade)
        self.sat = GRADES[grade][3]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
        self.vig = (1 - vignette * np.clip(r - 0.35, 0, 1) ** 1.6)[..., None].astype(np.float32)
        rng = np.random.default_rng(seed)
        self.grain = []
        for _ in range(6):
            g = Image.fromarray((rng.normal(128, 40, (H // 2, W // 2))).clip(0, 255).astype(np.uint8))
            g = g.resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(0.6))
            self.grain.append(((np.asarray(g).astype(np.float32) - 128) / 40 * grain)[..., None])

    def __call__(self, img, n):
        a = np.asarray(img.convert("RGB"))
        a = np.stack([self.lut[a[..., c], c] for c in range(3)], axis=-1).astype(np.float32)
        if self.sat != 1.0:
            lum = (a @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
            a = lum + (a - lum) * self.sat
        a = a * self.vig + self.grain[(n // 2) % len(self.grain)]
        return np.clip(a, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ backgrounds
def background(name, t, photo=None):
    rng = np.random.default_rng(21)
    yy = np.linspace(0, 1, H)[:, None, None]
    if name == "blurred-photo" and photo is not None:
        bg = ImageOps.fit(photo, (W // 4, H // 4)).filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        a = np.asarray(bg).astype(np.float32) * 0.45
        return Image.fromarray(a.astype(np.uint8)).convert("RGBA")
    if name == "steel-dusk":
        streak = rng.normal(0, 1, (H, W // 24)).astype(np.float32)  # brushed metal: smooth along x, busy along y
        streak = np.asarray(Image.fromarray(((streak * 30) + 128).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR))
        base = np.array([46, 58, 74], np.float32) * (1.15 - 0.6 * yy) + (np.array([22, 26, 30], np.float32) * yy)
        sweep = np.exp(-((np.linspace(0, 1, W)[None, :] - (0.2 + 0.12 * t)) ** 2) / 0.02)[..., None] * np.array([55, 52, 46])
        a = base + (streak[..., None].astype(np.float32) - 128) * 0.25 + sweep * (0.7 - 0.4 * yy)
    elif name == "fog-morning":
        base = np.array([196, 202, 206], np.float32) * (1 - 0.25 * yy)
        a = base + 0 * yy
        fog = Image.new("L", (W // 4, H // 4), 0)
        d = ImageDraw.Draw(fog)
        for i in range(9):
            x = (i * 97 + t * 12 * (1 + i % 3)) % (W // 4 + 80) - 40
            y = 40 + i * 50
            d.ellipse((x - 70, y - 25, x + 70, y + 25), fill=60)
        fog = np.asarray(fog.filter(ImageFilter.GaussianBlur(14)).resize((W, H), Image.BILINEAR)).astype(np.float32)[..., None]
        a = a + fog * 0.5
    elif name == "golden-sunset":
        top, mid, bot = np.array([70, 48, 110]), np.array([235, 120, 70]), np.array([40, 22, 40])
        a = np.where(yy < 0.55, top + (mid - top) * (yy / 0.55), mid + (bot - mid) * ((yy - 0.55) / 0.45)).astype(np.float32)
        xx = np.linspace(0, 1, W)[None, :, None]
        a = a + 120 * np.exp(-(((xx - 0.5) ** 2) / 0.03 + ((yy - 0.52) ** 2) / 0.004))
    elif name == "night-bokeh":
        a = (np.array([10, 16, 34], np.float32) + np.array([8, 10, 20], np.float32) * yy).astype(np.float32) + 0 * np.zeros((1, W, 1))
        lay = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))
        d = ImageDraw.Draw(lay)
        for i in range(26):
            x = (rng.uniform(0, W / 2) + t * rng.uniform(-8, 8)) % (W / 2)
            y = rng.uniform(H * 0.1, H * 0.48)
            r = rng.uniform(14, 46)
            c = (255, 170, 70) if i % 3 else (90, 160, 255)
            d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(v * rng.uniform(0.3, 0.7)) for v in c))
        lay = np.asarray(lay.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR)).astype(np.float32)
        a = a + lay
    else:  # concrete-day
        n = rng.normal(0, 1, (H // 3, W // 3)).astype(np.float32)
        n = np.asarray(Image.fromarray((n * 22 + 128).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)).astype(np.float32)
        a = np.array([150, 148, 142], np.float32) * (1.05 - 0.3 * yy) + (n[..., None] - 128) * 0.35
    a = np.broadcast_to(a, (H, W, 3)) if a.shape != (H, W, 3) else a
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


# ------------------------------------------------------------------ photos and camera
def load(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return im


def cover_scale(src):
    return max(W / src.size[0], H / src.size[1])


def max_zoom(src):
    """Largest zoom that still samples >= 1 source pixel per output pixel (no blurry upscaling)."""
    return max(1.0, 1 / cover_scale(src))


def prepare(src, zmax):
    """Downscale huge originals once, keeping exactly enough pixels for the tightest crop."""
    need = cover_scale(src) * zmax
    if need < 1:
        src = src.resize((int(src.size[0] * need) + 2, int(src.size[1] * need) + 2), Image.LANCZOS)
    return src


def view(src, cx, cy, z):
    s = cover_scale(src)
    cw, ch = W / (s * z), H / (s * z)
    cx = min(max(cx * src.size[0], cw / 2), src.size[0] - cw / 2)
    cy = min(max(cy * src.size[1], ch / 2), src.size[1] - ch / 2)
    return src.resize((W, H), box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2), resample=Image.BICUBIC).convert("RGBA")


def card(src, bg):
    """Small image: show it at (at most) its real size on the background instead of blowing it up."""
    k = min(1.0, (W - 120) / src.size[0], (H - 500) / src.size[1])
    im = src.resize((int(src.size[0] * k), int(src.size[1] * k)), Image.LANCZOS) if k < 1 else src
    out = bg.copy()
    sh = Image.new("RGBA", (im.size[0] + 60, im.size[1] + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 30, im.size[0] + 30, im.size[1] + 30), 24, fill=(0, 0, 0, 150))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)), ((W - sh.size[0]) // 2, (H - sh.size[1]) // 2 + 20))
    out.alpha_composite(im.convert("RGBA"), ((W - im.size[0]) // 2, (H - im.size[1]) // 2))
    return out


# ------------------------------------------------------------------ captions
def draw_caption(img, text, style, x, t_shot=0.0):
    """x = 0..1 progress inside the shot; text max ~26 characters."""
    if not text:
        return
    a = seg(x, 0.06, 0.2) * (1 - seg(x, 0.9, 0.99))
    if a <= 0:
        return
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if style == "mono-top":
        f = font("mono", 54)
        chars = int(len(text) * seg(x, 0.06, 0.24) + 0.999)
        s = text[:chars]
        y = 290
        tw = d.textlength(text, font=f)
        d.rectangle((70, y - 26, 70 + tw + 64, y + 150), fill=(8, 12, 18, int(205 * a)))
        d.rectangle((70, y - 26, 78, y + 150), fill=YELLOW + (int(255 * a),))
        d.text((112, y), s, font=f, fill=(235, 244, 250, int(255 * a)))
        if chars < len(text) or int(t_shot * 2.4) % 2 == 0:
            cx = 112 + d.textlength(s, font=f) + 6
            d.rectangle((cx, y + 4, cx + 26, y + 62), fill=YELLOW + (int(230 * a),))
        f2 = font("mono", 30)
        d.text((112, y + 92), "LOCKMAN // SAN FRANCISCO", font=f2, fill=(242, 194, 0, int(200 * a)))
    elif style == "clean-lower-left":
        f = font("inter-semibold", 62)
        off = (1 - ease(seg(x, 0.06, 0.2))) * -80
        tw = d.textlength(text, font=f)
        y = 1480
        d.rounded_rectangle((60 + off, y - 24, 60 + off + tw + 80, y + 96), 26, fill=(10, 10, 14, int(170 * a)))
        d.rounded_rectangle((60 + off, y - 24, 72 + off, y + 96), 6, fill=YELLOW + (int(255 * a),))
        d.text((104 + off, y), text, font=f, fill=(255, 255, 255, int(255 * a)))
    elif style == "bold-lower-third":
        f = font("inter-black", 66)
        s = text.upper()
        tw = d.textlength(s, font=f)
        y = 1390
        wipe = ease(seg(x, 0.04, 0.16))
        d.rectangle((0, y - 20, (tw + 140) * wipe, y + 92), fill=YELLOW + (int(255 * a),))
        if wipe > 0.6:
            d.text((70, y), s, font=f, fill=(14, 14, 18, int(255 * a)))
        d.rectangle((0, y + 92, (tw + 60) * wipe, y + 140), fill=(14, 14, 18, int(230 * a)))
        d.text((70, y + 98), "LOCKMAN ASAP LOCKSMITH", font=font("inter-bold", 30), fill=(255, 255, 255, int(255 * a)))
    elif style == "serif-center":
        f = font("serif", 60)
        tw = d.textlength(text, font=f)
        y = 1560
        # soft dark shading behind the subtitle so it stays readable on bright photos
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shade).rounded_rectangle(((W - tw) / 2 - 70, y - 40, (W + tw) / 2 + 70, y + 110), 60,
                                                fill=(12, 8, 4, int(165 * a)))
        img.alpha_composite(shade.filter(ImageFilter.GaussianBlur(28)))
        d.text(((W - tw) / 2, y), text, font=f, fill=(255, 244, 226, int(255 * a)), stroke_width=3, stroke_fill=(0, 0, 0, int(190 * a)))
    else:  # kinetic-pop
        f = font("inter-black", 92)
        words = text.upper().split()
        shown = words[: max(1, int(len(words) * seg(x, 0.04, 0.3) + 0.999))]
        lines, cur = [], ""
        for w_ in shown:
            if d.textlength((cur + " " + w_).strip(), font=f) > W - 140:
                lines.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        lines.append(cur)
        y = 1180
        for i, ln in enumerate(lines):
            tw = d.textlength(ln, font=f)
            d.text(((W - tw) / 2, y + i * 108), ln, font=f, fill=(255, 255, 255, int(255 * a)), stroke_width=8, stroke_fill=(0, 0, 0, int(255 * a)))
    img.alpha_composite(lay)


# ------------------------------------------------------------------ intro / outro
def hook_text(img, hook, p, style):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if style == "mono-top":
        f = font("mono", 76)
    elif style == "serif-center":
        f = font("serif", 84)
    else:
        f = font("inter-black", 96)
    lines = hook.split("|")
    a = seg(p, 0.0, 0.18)
    for i, ln in enumerate(lines):
        k = ease(seg(p, 0.05 + i * 0.12, 0.3 + i * 0.12))
        tw = d.textlength(ln, font=f)
        y = 820 + i * 112 + (1 - k) * 40
        d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255, int(255 * k * a)), stroke_width=4, stroke_fill=(0, 0, 0, int(160 * k)))
    img.alpha_composite(lay)


def outro(t, bg_name, photo, style):
    img = background(bg_name, 3 + t, photo)
    logo = Image.open(ASSETS / "img/logo-full-600.webp").convert("RGBA")
    k = ease(seg(t, 0.0, 0.8))
    lw = int(560 * (0.92 + 0.08 * k))
    lg = logo.resize((lw, int(logo.size[1] * lw / logo.size[0])), Image.LANCZOS)
    lg.putalpha(lg.getchannel("A").point(lambda v: int(v * k)))
    img.alpha_composite(lg, ((W - lw) // 2, 520))
    d = ImageDraw.Draw(img)
    lines = [("San Francisco Locksmith", font("inter-semibold", 56), (255, 255, 255)),
             ("(415) 806-7343", font("inter-black", 104), YELLOW),
             ("lockmanasaplocksmith.com", font("inter-semibold", 44), (230, 234, 240))]
    y = 520 + lg.size[1] + 70
    for i, (s, f, c) in enumerate(lines):
        kk = ease(seg(t, 0.35 + i * 0.18, 0.9 + i * 0.18))
        tw = d.textlength(s, font=f)
        d.text(((W - tw) / 2, y + (1 - kk) * 30), s, font=f, fill=c + (int(255 * kk),), stroke_width=3, stroke_fill=(0, 0, 0, int(140 * kk)))
        y += f.size + 46
    return img


# ------------------------------------------------------------------ main render
def make(out, images, captions=(), look="cinematic", background_name="blurred-photo", music_mood="chill",
         hook=None, focus=None, caption_style=None, fps=FPS, crf=18, opener=None):
    global FPS
    FPS = fps
    cfg = dict(LOOK.get(look, LOOK["cinematic"]))
    style = caption_style or cfg["caption"]
    raw = [load(p) for p in images]
    zcap = [max_zoom(s) for s in raw]
    zoom_lo, zoom_hi = cfg["zoom"]
    srcs = [prepare(s, min(zoom_hi * 1.15, zc)) for s, zc in zip(raw, zcap)]
    small = [cover_scale(s) > 1.02 for s in raw]  # smaller than the frame: shown as a card, never blown up
    focus = list(focus or [])
    focus += [(0.5, 0.5)] * (len(srcs) - len(focus))
    fin = Finisher(cfg["grade"], cfg["grain"])
    bg_static = background(background_name, 0, srcs[0])

    moves = []
    for i, s in enumerate(srcs):
        zc = max_zoom(s) if not small[i] else 1.0
        lo, hi = min(zoom_lo, zc), min(zoom_hi, zc)
        fx, fy = focus[i]
        wide = (0.5 + (fx - 0.5) * 0.3, 0.5 + (fy - 0.5) * 0.3, lo)
        tight = (fx, fy, hi)
        if look == "macro":
            moves.append((tight[:2] + (max(lo, hi * 0.88),), tight))  # creep in on the detail
        elif look == "reel":
            moves.append((tight, wide) if i % 2 else (wide, tight))
        else:
            moves.append((wide, tight) if i % 2 == 0 else (tight, wide))

    intro = 2.4
    shot = cfg["shot"]
    tl = cfg["tlen"]
    outro_len = 4.8
    pairs = look == "before-after"
    nshots = (len(srcs) + 1) // 2 if pairs else len(srcs)
    total = intro + shot * nshots + outro_len
    end_start = intro + shot * nshots
    op = opener if opener is not None else (1 if len(srcs) > 1 else 0)
    hook = hook or "WATCH THIS|LOCK"

    def shot_img(i, x, t):
        s = srcs[i]
        if small[i]:
            return card(s, background(background_name, t, srcs[0]))
        (ax, ay, az), (bx, by, bz) = moves[i]
        k = ease(x)
        cx, cy, z = ax + (bx - ax) * k, ay + (by - ay) * k, az + (bz - az) * k
        if cfg["shake"]:
            amp = cfg["shake"] / 1000
            cx += amp * (math.sin(t * 1.7) + 0.5 * math.sin(t * 4.3 + 1))
            cy += amp * (math.cos(t * 1.3) + 0.5 * math.sin(t * 3.7 + 2))
        img = view(s, cx, cy, z)
        if cfg["rack"]:
            r = 16 * (1 - ease(seg(x, 0.0, 0.16)))
            if r > 0.3:
                img = img.filter(ImageFilter.GaussianBlur(r))
        if cfg["leaks"]:
            leak = Image.new("RGBA", (W // 8, H // 8), (0, 0, 0, 0))
            dd = ImageDraw.Draw(leak)
            lx = (W // 8) * (0.1 + 0.8 * ((t * 0.07 + i * 0.37) % 1))
            dd.ellipse((lx - 40, -30, lx + 40, 70), fill=(255, 140, 60, 70))
            img.alpha_composite(leak.filter(ImageFilter.GaussianBlur(14)).resize((W, H), Image.BILINEAR))
        return img

    def pair_img(j, x, t):
        a_i, b_i = 2 * j, min(2 * j + 1, len(srcs) - 1)
        before, after = shot_img(a_i, x * 0.5, t), shot_img(b_i, 0.5 + x * 0.5, t)
        p = ease(seg(x, 0.35, 0.65))
        cut = int(W * (1 - p))
        img = before.copy()
        if cut < W:
            img.paste(after.crop((cut, 0, W, H)), (cut, 0))
            dd = ImageDraw.Draw(img)
            dd.rectangle((cut - 4, 0, cut + 4, H), fill=(255, 255, 255, 255))
        dd = ImageDraw.Draw(img)
        f = font("inter-black", 54)
        if p < 0.98:
            dd.text((60, 220), "BEFORE", font=f, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
        if p > 0.02:
            dd.text((W - 60 - dd.textlength("AFTER", font=f), 220), "AFTER", font=f, fill=YELLOW, stroke_width=4, stroke_fill=(0, 0, 0))
        return img, (captions[b_i] if p > 0.5 and b_i < len(captions) else (captions[a_i] if a_i < len(captions) else ""))

    def main_frame(t):
        k = int((t - intro) // shot)
        x = (t - intro - k * shot) / shot
        if pairs:
            img, cap = pair_img(k, x, t)
        else:
            img = shot_img(k, x, t)
            cap = captions[k] if k < len(captions) else ""
        draw_caption(img, cap, style, x, t - intro - k * shot)
        return img

    def frame(t):
        if t < intro:
            p = t / intro
            if look == "macro":  # open on an extreme close-up of a lock part, coming into focus
                s = srcs[op]
                fx, fy = focus[op]
                z = min(max_zoom(s), zoom_hi * 1.15)
                img = view(s, fx, fy, z * (1 - 0.04 * p))
                r = 22 * (1 - ease(seg(p, 0.0, 0.55)))
                if r > 0.3:
                    img = img.filter(ImageFilter.GaussianBlur(r))
                img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(90 * (1 - seg(p, 0.6, 1))))))
            else:
                img = background(background_name, t, srcs[0])
            hook_text(img, hook, p, style)
            return img
        if t >= end_start:
            return outro(t - end_start, background_name, srcs[0], style)
        img = main_frame(t)
        k = int((t - intro) // shot)
        local = t - intro - k * shot
        if local < tl:  # transition from the previous frame source
            prev_t = intro + k * shot - 1e-3 if k > 0 else intro - 1e-3
            prev = main_frame(prev_t) if k > 0 else frame(prev_t)
            p = ease(local / tl)
            tr = cfg["trans"]
            if tr in ("blur-dissolve", "focus-dissolve"):
                r = 12 * math.sin(math.pi * p)
                mixed = Image.blend(prev, img, p)
                img = mixed.filter(ImageFilter.GaussianBlur(r)) if r > 0.5 else mixed
            elif tr == "flash-cut":
                img = Image.blend(img, Image.new("RGBA", (W, H), (255, 255, 255, 255)), (1 - p) * 0.85)
            elif tr == "zoom-punch":
                z = 1 + 0.12 * (1 - p)
                cw, ch = W / z, H / z
                img = img.resize((W, H), box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2), resample=Image.BICUBIC)
            elif tr == "wipe":
                cut = int(W * p)
                base = prev.copy()
                base.paste(img.crop((0, 0, cut, H)), (0, 0))
                img = base
        if t > end_start - 0.5:  # fade into the end card
            img = Image.blend(img, outro(0, background_name, srcs[0], style), seg(t, end_start - 0.5, end_start))
        return img

    # sound: original music in the chosen mood + soft transition sounds
    sfx = np.zeros(int((total + 1) * moods.SR))
    r2 = np.random.default_rng(7)
    for k in range(nshots):
        music.add(sfx, music.whoosh(r2) * 0.25, intro + k * shot - 0.25)
    music.add(sfx, music.chime() * 0.35, end_start + 0.1)
    wav = Path(out).with_suffix(".wav")
    moods.render(music_mood, total, wav, sfx)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-maxrate", "10M", "-bufsize", "20M", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(int(total * fps)):
        p.stdin.write(fin(frame(n / fps), n).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    wav.unlink(missing_ok=True)
    poster = Path(out).with_suffix(".jpg")
    mid = intro + shot * 0.6
    Image.fromarray(fin(frame(mid), 0)).resize((540, 960), Image.LANCZOS).save(poster, quality=88)
    return out
