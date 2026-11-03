"""Original music + sound effects for the Lockman rescue video. Pure numpy, no samples."""
import numpy as np
import wave

SR = 44100
BPM = 128
BEAT = 60 / BPM


def note_freq(n):  # MIDI note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a=0.005, r=0.08):
    t = np.arange(n) / SR
    e = np.minimum(1, t / a) if a > 0 else np.ones(n)
    tail = np.clip((n / SR - t) / r, 0, 1)
    return e * tail


def tone(freq, dur, kind="saw", vol=0.2, a=0.005, r=0.08):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ph = (freq * t) % 1
    if kind == "saw":
        w = 2 * ph - 1
    elif kind == "square":
        w = np.where(ph < 0.5, 1.0, -1.0)
    elif kind == "tri":
        w = 4 * np.abs(ph - 0.5) - 1
    else:
        w = np.sin(2 * np.pi * freq * t)
    return w * env(n, a, r) * vol


def add(buf, sig, at):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def kick():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 25) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 0.9


def snare(rng):
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    return (rng.standard_normal(n) * 0.5 + np.sin(2 * np.pi * 190 * t) * 0.3) * np.exp(-t * 22) * 0.55


def hat(rng):
    n = int(0.05 * SR)
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(4) / 4, "same")  # crude high-pass
    return noise * np.exp(-np.arange(n) / SR * 80) * 0.25


def whoosh(rng, dur=1.2):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    k = 1
    for i in range(0, n, 512):  # sweep a moving-average low-pass from dark to bright
        frac = i / n
        k = max(1, int(60 * (1 - frac)) + 1)
        seg = noise[max(0, i - k): i + 512]
        sm = np.convolve(seg, np.ones(k) / k, "same")[-min(512, n - i):]
        out[i:i + len(sm)] = sm
    shape = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    return out * shape * 0.9


def click():
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2400 * t) + 0.6 * np.sin(2 * np.pi * 3700 * t)) * np.exp(-t * 90) * 0.6


def bark():
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 520 - 900 * t
    return np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 16) * 0.18


def chime():
    sig = np.zeros(int(1.4 * SR))
    for k, n in enumerate([72, 76, 79, 84]):
        add(sig, tone(note_freq(n), 1.0, "tri", 0.18, 0.005, 0.8), k * 0.09)
    return sig


def render(total, events, path):
    rng = np.random.default_rng(7)
    buf = np.zeros(int(total * SR) + SR)
    # C minor heroic progression: Cm  Ab  Eb  Bb  (one bar each, 4 beats)
    chords = [(48, [60, 63, 67]), (44, [56, 60, 63]), (51, [58, 63, 67]), (46, [58, 62, 65])]
    # original lead motif (scale degrees in C minor), 8 eighth-notes per bar
    motif = [
        [67, 0, 67, 70, 72, 0, 70, 67],
        [68, 0, 68, 72, 75, 0, 72, 68],
        [70, 0, 70, 74, 75, 74, 72, 70],
        [74, 0, 72, 70, 67, 0, 0, 0],
    ]
    bar = 4 * BEAT
    nbars = int(total / bar) + 1
    for b in range(nbars):
        t0 = b * bar
        root, triad = chords[b % 4]
        intro = b < 2
        for e8 in range(8):  # driving eighth-note bass
            add(buf, tone(note_freq(root - 12 + (12 if e8 % 2 else 0)), BEAT / 2 * 0.9, "saw", 0.13, 0.003, 0.05), t0 + e8 * BEAT / 2)
        for n in triad:  # pad
            add(buf, tone(note_freq(n), bar, "tri", 0.045, 0.08, 0.3), t0)
        for beat in range(4):
            add(buf, kick(), t0 + beat * BEAT)
            if beat in (1, 3) and not intro:
                add(buf, snare(rng), t0 + beat * BEAT)
            for h in range(2):
                add(buf, hat(rng), t0 + beat * BEAT + h * BEAT / 2)
        if not intro:
            for i, n in enumerate(motif[b % 4]):
                if n:
                    add(buf, tone(note_freq(n), BEAT / 2 * 0.95, "square", 0.07, 0.004, 0.06), t0 + i * BEAT / 2)
    # gentle fade out at the end
    fade = int(2.0 * SR)
    end = int(total * SR)
    buf[end - fade:end] *= np.linspace(1, 0, fade)
    buf[end:] = 0
    music = buf * 0.55
    sfx = np.zeros_like(buf)
    for kind, at in events:
        s = {"whoosh": lambda: whoosh(rng), "click": click, "bark": bark, "chime": chime}[kind]()
        add(sfx, s, at)
    mix = music + sfx
    mix = np.tanh(mix * 1.2) * 0.85
    mix = mix[: int(total * SR)]
    pcm = (mix * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).ravel()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
