"""Original background music in several moods, rendered offline with numpy (no samples, no network).

Moods: epic (the site's Lockman theme), chill (lo-fi electric piano), acoustic (plucked guitar),
upbeat (bright pop groove), trance (pumping supersaw + arpeggio). Every mood is a variation built
around the same Lockman motif (D - F - A - G), so the brand sound stays recognizable.

    render(mood, total_seconds, path=None, sfx=None) -> float mono mix (and a stereo wav at path)
"""
import wave

import numpy as np
from scipy.signal import fftconvolve, lfilter

from video import theme

SR = 44100
MOODS = ("epic", "chill", "acoustic", "upbeat", "trance")
MOTIF = [62, 65, 69, 67]  # D4 F4 A4 G4 - the Lockman motif


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    return lfilter([1 - a], [1, -a], lfilter([1 - a], [1, -a], x))


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def place(buf, sig, t):
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def adsr(n, a, d, s, r_from, r):
    t = np.arange(n) / SR
    env = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = t > r_from
    return np.where(rel, env * np.exp(-(t - r_from) / max(r, 1e-4)), env)


def reverb(x, seconds=2.4, seed=3, amount=0.35):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.uniform(-1, 1, n) * (1 - np.arange(n) / n) ** 3
    ir = lowpass(ir, 5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    return x + fftconvolve(x, ir)[: len(x)] * amount


# ------------------------------------------------------------------ instruments
def epiano(f, dur, vel=0.25):
    n = int((dur + 1.2) * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 3)
    bell = 0.18 * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t * 9)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.6 * t)
    return (tone + bell) * trem * adsr(n, 0.005, 1.4, 0.35, dur, 0.5) * vel


def pluck(f, dur, vel=0.3, rng=None, bright=0.5):
    """Karplus-Strong plucked string."""
    rng = rng or np.random.default_rng(0)
    n = int((dur + 1.5) * SR)
    p = max(2, int(SR / f))
    buf = lowpass(rng.uniform(-1, 1, p), 2000 + 6000 * bright)
    out = np.zeros(n)
    decay = 0.996
    for i in range(0, n, p):
        k = min(p, n - i)
        out[i:i + k] = buf[:k]
        buf = decay * 0.5 * (buf + np.roll(buf, 1))
    return out * vel * adsr(n, 0.002, 2.0, 0.6, dur + 0.6, 0.4)


def saw(f, n, voices=1, spread=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for v in range(voices):
        det = 2 ** ((spread * (v - (voices - 1) / 2) / max(1, voices - 1)) / 1200) if voices > 1 else 1
        ph = (f * det * t + rng.uniform()) % 1
        out += 2 * ph - 1
    return out / voices


def kick(vel=0.9, tight=False):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t * (40 if tight else 25))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (9 if tight else 6)) * vel


def snare(rng, vel=0.4, soft=False):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    noise = highpass(rng.uniform(-1, 1, n), 1200 if soft else 1800) * np.exp(-t * (14 if soft else 20))
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * (0.2 if soft else 0.5)
    return (noise * (0.6 if soft else 1.0) + body) * vel


def hat(rng, vel=0.12, open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    return highpass(rng.uniform(-1, 1, n), 7000) * np.exp(-t * (12 if open_ else 70)) * vel


def shaker(rng, vel=0.08):
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    env = np.sin(np.pi * np.minimum(1, t / 0.09))
    return highpass(rng.uniform(-1, 1, n), 5000) * env * vel


def crackle(n, rng, amount=0.012):
    x = np.zeros(n)
    idx = rng.integers(0, n, n // 2500)
    x[idx] = rng.uniform(-1, 1, len(idx))
    return lowpass(x, 6000) * amount * 8 + lowpass(rng.uniform(-1, 1, n), 900) * amount * 0.25


# ------------------------------------------------------------------ moods
def _chill(total, rng):
    bpm = 78
    beat = 60 / bpm
    n = int((total + 3) * SR)
    music, drums = np.zeros(n), np.zeros(n)
    prog = [[50, 57, 60, 64, 65], [55, 59, 62, 65, 69], [52, 55, 59, 62, 67], [57, 60, 64, 67, 72]]  # Dm9 G9 Em7 Am7
    bar = 4 * beat
    nb = int(total / bar) + 2
    for b in range(nb):
        t0 = b * bar
        ch = prog[b % 4]
        for k, m in enumerate(ch[1:]):
            place(music, epiano(hz(m), bar * 0.9, 0.11), t0 + k * 0.018)
        place(music, epiano(hz(ch[0] - 12), bar * 0.8, 0.16), t0)
        if b % 2 == 1:  # the Lockman motif, soft, high
            for k, m in enumerate(MOTIF):
                place(music, epiano(hz(m + 12), beat * 0.8, 0.07), t0 + k * beat)
        for q in range(4):
            sw = 0.06 * beat
            if q in (0, 2):
                place(drums, kick(0.55), t0 + q * beat + (0.5 * beat + sw if q == 2 and b % 2 else 0))
            if q in (1, 3):
                place(drums, snare(rng, 0.28, soft=True), t0 + q * beat)
            place(drums, hat(rng, 0.06), t0 + q * beat)
            place(drums, hat(rng, 0.045), t0 + q * beat + beat / 2 + sw)
    music = reverb(lowpass(music, 3200), 2.8, amount=0.45)
    mix = music * 0.9 + lowpass(drums, 5000) * 0.8 + crackle(n, rng)
    return mix


def _acoustic(total, rng):
    bpm = 96
    beat = 60 / bpm
    n = int((total + 3) * SR)
    gtr, perc = np.zeros(n), np.zeros(n)
    prog = [[50, 57, 62, 65, 69], [46, 53, 58, 62, 65], [48, 55, 60, 64, 67], [45, 52, 57, 61, 64]]  # Dm Bb C A
    pattern = [0, 2, 3, 4, 3, 2, 3, 4]
    bar = 4 * beat
    for b in range(int(total / bar) + 2):
        t0 = b * bar
        ch = prog[b % 4]
        for s, idx in enumerate(pattern):
            place(gtr, pluck(hz(ch[idx]), beat * 0.6, 0.22, rng, bright=0.45), t0 + s * beat / 2 + rng.uniform(0, 0.008))
        if b % 4 == 3:
            for k, m in enumerate(MOTIF):
                place(gtr, pluck(hz(m + 12), beat, 0.16, rng, bright=0.8), t0 + k * beat)
        for e in range(8):
            place(perc, shaker(rng, 0.05 if e % 2 else 0.08), t0 + e * beat / 2)
        place(perc, kick(0.35), t0)
        place(perc, kick(0.25), t0 + 2.5 * beat)
    return reverb(gtr, 1.8, amount=0.3) * 1.1 + perc


def _upbeat(total, rng):
    bpm = 116
    beat = 60 / bpm
    n = int((total + 3) * SR)
    syn, drums, bass = np.zeros(n), np.zeros(n), np.zeros(n)
    prog = [[62, 65, 69], [58, 62, 65], [60, 64, 67], [57, 61, 64]]
    bar = 4 * beat
    for b in range(int(total / bar) + 2):
        t0 = b * bar
        ch = prog[b % 4]
        for e in range(8):
            if e in (0, 3, 6):
                for m in ch:
                    nn = int(beat * 0.45 * SR)
                    s = lowpass(saw(hz(m), nn, 2, 12, seed=m), 2600) * adsr(nn, 0.004, 0.12, 0.3, beat * 0.3, 0.05) * 0.09
                    place(syn, s, t0 + e * beat / 2)
            nb_ = int(beat * 0.4 * SR)
            if e % 2 == 1:
                place(bass, lowpass(saw(hz(ch[0] - 24), nb_), 500) * adsr(nb_, 0.003, 0.1, 0.6, beat * 0.3, 0.04) * 0.35, t0 + e * beat / 2)
            place(drums, hat(rng, 0.07 if e % 2 else 0.05), t0 + e * beat / 2)
        for q in range(4):
            place(drums, kick(0.75, tight=True), t0 + q * beat)
            if q in (1, 3):
                place(drums, snare(rng, 0.35), t0 + q * beat)
        if b % 2 == 1:
            for k, m in enumerate(MOTIF):
                nn = int(beat * 0.5 * SR)
                place(syn, np.sin(2 * np.pi * hz(m + 12) * np.arange(nn) / SR) * adsr(nn, 0.005, 0.2, 0.4, beat * 0.4, 0.1) * 0.08, t0 + k * beat)
    return reverb(syn, 1.4, amount=0.3) + bass + drums


def _trance(total, rng):
    bpm = 134
    beat = 60 / bpm
    n = int((total + 3) * SR)
    pad, arp, drums = np.zeros(n), np.zeros(n), np.zeros(n)
    prog = [[50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64], [45, 52, 57, 61]]
    bar = 4 * beat
    for b in range(int(total / bar) + 2):
        t0 = b * bar
        ch = prog[b % 4]
        nn = int(bar * SR)
        chord = sum(saw(hz(m), nn, 5, 28, seed=m + b) for m in ch) / len(ch)
        place(pad, lowpass(chord, 1800) * adsr(nn, 0.2, 1.0, 0.8, bar * 0.9, 0.2) * 0.22, t0)
        seq = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[3] + 12]
        if b % 2 == 1:
            seq = [m + 12 for m in MOTIF]
        for s in range(16):
            m = seq[s % 4] + (12 if s % 8 == 7 else 0)
            ns = int(beat / 4 * 0.9 * SR)
            place(arp, lowpass(saw(hz(m), ns, 2, 10), 3200) * adsr(ns, 0.002, 0.06, 0.2, beat / 4 * 0.6, 0.03) * 0.09, t0 + s * beat / 4)
        for q in range(4):
            place(drums, kick(0.8, tight=True), t0 + q * beat)
            place(drums, hat(rng, 0.08, open_=True), t0 + q * beat + beat / 2)
    t = np.arange(n) / SR
    pump = 0.35 + 0.65 * np.minimum(1, ((t % beat) / (beat * 0.55)) ** 1.5)  # sidechain feel
    return reverb(pad, 2.5, amount=0.4) * pump + reverb(arp, 1.2, amount=0.35) * pump + drums


def render(mood, total, path=None, sfx=None, fade_in=0.8, fade_out=2.2):
    mood = mood if mood in MOODS else "epic"
    if mood == "epic":
        return theme.render_theme(total, str(path) if path else None, sfx)
    rng = np.random.default_rng(11)
    mix = {"chill": _chill, "acoustic": _acoustic, "upbeat": _upbeat, "trance": _trance}[mood](total, rng)
    end = int(total * SR)
    mix = mix[:end]
    mix = highpass(mix, 30)
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.8
    if sfx is not None:
        k = min(len(sfx), end)
        mix[:k] += sfx[:k]
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[end - fo:end] *= np.linspace(1, 0, fo)
    mix = np.tanh(mix * 1.4) * 0.92
    if path:
        pcm = (mix * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(np.column_stack([pcm, pcm]).ravel().tobytes())
    return mix
