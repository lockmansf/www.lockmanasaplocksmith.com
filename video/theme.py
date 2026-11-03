"""Offline render of the site's original Lockman theme (assets/theme.js): D minor, 84 BPM,
string ostinato, brass chords, sub drone, taiko, clock tick, horn line, reverb."""
import wave

import numpy as np
from scipy.signal import fftconvolve, lfilter

SR = 44100
BPM = 84
STEP = 60 / BPM / 4
CHORDS = [(73.42, 3), (58.27, 4), (49.00, 3), (55.00, 4)]
OSTINATO = [0, 0, 12, 0, 7, 0, 12, 7, 0, 0, 12, 0, 7, 12, 7, 0]
HORN = [[(7, 16)], [(3, 8), (5, 8)], [(12, 8), (8, 8)], [(11, 16)]]
D4 = 293.66


def semi(f, n):
    return f * 2 ** (n / 12)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = lfilter([1 - a], [1, -a], x)
    return lfilter([1 - a], [1, -a], y)  # two poles, a little steeper


def osc(kind, f, n, detune=0.0):
    t = np.arange(n) / SR
    f2 = f * 2 ** (detune / 1200)
    out = 0
    for ff in (f, f2):
        ph = (ff * t) % 1
        out = out + ((2 * ph - 1) if kind == "saw" else np.where(ph < 0.5, 1.0, -1.0))
    return out / 2


def voice(dry, wet, kind, f, t, dur, gain, cutoff, attack, wetamt):
    tail = max(0.05, dur * 0.25)
    n = int((dur + tail * 4) * SR)
    x = lowpass(osc(kind, f, n, 9), cutoff)
    tt = np.arange(n) / SR
    env = np.where(tt < attack, tt / attack * gain, gain)
    rel = tt > dur
    env = np.where(rel, gain * np.exp(-(tt - dur) / tail), env)
    sig = x * env
    i = int(t * SR)
    j = min(len(dry), i + n)
    dry[i:j] += sig[: j - i]
    if wetamt:
        wet[i:j] += sig[: j - i] * wetamt


def taiko(dry, wet, t, gain):
    n = int(1.0 * SR)
    tt = np.arange(n) / SR
    f = 95 * (38 / 95) ** np.minimum(1, tt / 0.45)
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * gain * (0.001 / 1) ** (tt / 0.9)
    i = int(t * SR)
    j = min(len(dry), i + n)
    dry[i:j] += sig[: j - i]
    wet[i:j] += sig[: j - i] * 0.35


def tick(dry, t, rng):
    n = int(0.03 * SR)
    x = rng.uniform(-1, 1, n) * (1 - np.arange(n) / n)
    x = x - lowpass(x, 3500)
    i = int(t * SR)
    j = min(len(dry), i + n)
    dry[i:j] += x[: j - i] * 0.05


def render_theme(total, path=None, sfx=None, fade_in=1.2, fade_out=2.0):
    rng = np.random.default_rng(1)
    n = int((total + 4) * SR)
    dry, wet = np.zeros(n), np.zeros(n)
    drone_f = np.zeros(n)
    steps = int(total / STEP) + 1
    for s in range(steps):
        t = s * STEP
        step = s % (16 * 8)
        bar, b16 = step // 16, step % 16
        root, third = CHORDS[bar % 4]
        phrase = bar % 8
        voice(dry, wet, "saw", semi(root, OSTINATO[b16]), t, STEP * 0.9, 0.07, 700 + 500 * (phrase / 7), 0.01, 0.15)
        if b16 == 0:
            for k in (12, 12 + third, 19):
                voice(dry, wet, "saw", semi(root, k), t, STEP * 15, 0.028, 520, 1.2, 0.5)
            drone_f[int(t * SR):] = root / 2
        if b16 in (0, 10):
            taiko(dry, wet, t, 0.55 if b16 == 0 else 0.35)
        if phrase == 7 and b16 >= 12:
            taiko(dry, wet, t, 0.25)
        if b16 % 4 == 0:
            tick(dry, t, rng)
        if phrase >= 4:
            pos = 0
            for semis, length in HORN[phrase - 4]:
                if pos == b16:
                    voice(dry, wet, "square", semi(D4, semis), t, STEP * length * 0.95, 0.03, 1400, 0.25, 0.6)
                pos += length
    drone_f[drone_f == 0] = CHORDS[0][0] / 2
    tt = np.arange(n) / SR
    dry += np.sin(2 * np.pi * np.cumsum(drone_f) / SR) * 0.16 * np.minimum(1, tt / 1.5)
    ir_n = int(3.2 * SR)
    ir = rng.uniform(-1, 1, ir_n) * (1 - np.arange(ir_n) / ir_n) ** 2.6
    ir /= np.sqrt(np.sum(ir ** 2))
    rev = fftconvolve(wet, ir)[:n] * 0.6
    mix = (dry + rev) * 0.55
    if sfx is not None:
        mix[: len(sfx)] += sfx[: len(mix)]
    end = int(total * SR)
    mix[: int(fade_in * SR)] *= np.linspace(0, 1, int(fade_in * SR))
    mix[end - int(fade_out * SR): end] *= np.linspace(1, 0, int(fade_out * SR))
    mix = mix[:end]
    mix = np.tanh(mix * 1.6) * 0.9  # gentle compression
    if path:
        pcm = (mix * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(np.column_stack([pcm, pcm]).ravel().tobytes())
    return mix
