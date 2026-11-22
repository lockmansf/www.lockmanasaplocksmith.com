"""Add the Lockman Hero voice-over to draft videos (ElevenLabs).

For every entry in content/videos.json that has a "narration" text and no
"narrated": true, this script:
  1. asks ElevenLabs to speak the text with the Lockman Hero voice,
  2. mixes the voice over the video's music (music is lowered while he talks),
  3. replaces assets/videos/<slug>.mp4 and marks the entry "narrated": true.

The owner still approves every video: drafts stay drafts.

Needs the secret ELEVENLABS_API_KEY (Text to Speech access only).
Usage:
  python3 -m publisher.narrate            # narrate pending videos
  python3 -m publisher.narrate --check    # only check the key works
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_FILE = ROOT / "content" / "videos.json"
VIDEO_DIR = ROOT / "assets" / "videos"

VOICE_ID = "FHR7lobwCk80Er7ZUCxL"  # "Lockman Hero", original voice made with Voice Design
MODEL_ID = "eleven_multilingual_v2"
API = "https://api.elevenlabs.io/v1/text-to-speech/"


def speak(text, key, out_path):
    body = json.dumps({
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True},
    }).encode()
    req = urllib.request.Request(
        API + VOICE_ID + "?output_format=mp3_44100_128",
        data=body,
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        Path(out_path).write_bytes(res.read())


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def mix(video, voice, out):
    """Voice starts after 1.5 s; music is ducked under the voice."""
    filt = (
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay=1500|1500,volume=1.6,apad,asplit=2[vox][key];"
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.9[mus];"
        "[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
        "[duck][vox]amix=inputs=2:duration=first:dropout_transition=0,volume=1.4[aout]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voice),
         "-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
        check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY is not set; nothing to do.")
        return 0

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            speak("Lockman is ready.", key, Path(tmp) / "t.mp3")
        print("ElevenLabs key works with the Lockman Hero voice.")
        return 0

    videos = json.loads(VIDEOS_FILE.read_text(encoding="utf-8"))
    changed = False
    for v in videos:
        text = (v.get("narration") or "").strip()
        if not text or v.get("narrated"):
            continue
        mp4 = VIDEO_DIR / f"{v['slug']}.mp4"
        if not mp4.exists():
            print(f"skip {v['slug']}: video file missing")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / "voice.mp3"
            try:
                speak(text, key, voice)
            except urllib.error.HTTPError as e:
                print(f"ElevenLabs error for {v['slug']}: {e.code} {e.read()[:300]!r}")
                return 1
            if duration(voice) + 1.5 > duration(mp4) + 0.5:
                print(f"warning {v['slug']}: narration is longer than the video and will be cut")
            out = Path(tmp) / "out.mp4"
            mix(mp4, voice, out)
            mp4.write_bytes(out.read_bytes())
        v["narrated"] = True
        changed = True
        print(f"narrated {v['slug']}")

    if changed:
        VIDEOS_FILE.write_text(json.dumps(videos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
