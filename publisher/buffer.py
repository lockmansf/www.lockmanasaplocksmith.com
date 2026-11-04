"""Posts new LOCKMAN videos to Instagram, TikTok and YouTube through Buffer.

Reads content/videos.json. A video is posted once to every connected Buffer
channel; the result is saved on the video as "buffer": {channel: post id or error}.
Skipped: videos with "buffer": "hold", and videos published before START
(the old samples) unless they are given "buffer": {} to release them.
The video file must already be live on the site, so this runs after deploy.

Needs one secret: BUFFER_API_KEY (Buffer > Settings > API > Personal key).

Usage:
  python3 -m publisher.buffer --check     # list channels only, posts nothing
  python3 -m publisher.buffer [--dry-run] # post videos not posted yet
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from publisher import common

API = "https://api.buffer.com"
VIDEOS_FILE = common.ROOT / "content" / "videos.json"
START = "2026-11-05"
PHONE = "(415) 806-7343"
TAGS = "#SanFrancisco #Locksmith #Lockman #SFLocksmith #LockedOut #CarLockout #BayArea"


class BufferError(Exception):
    pass


def gql(query, variables=None):
    key = (os.environ.get("BUFFER_API_KEY") or "").strip()
    if not key:
        raise BufferError("BUFFER_API_KEY secret is missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "lockman-site/1.0", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as ex:
        raise BufferError(f"HTTP {ex.code}: {ex.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError as ex:
        raise BufferError(f"connection failed: {ex}")
    if data.get("errors"):
        raise BufferError("; ".join(e.get("message", "?") for e in data["errors"]))
    return data["data"]


def diagnose():
    """Prints what is wrong with the key, without printing the key."""
    key = (os.environ.get("BUFFER_API_KEY") or "")
    print(f"key length {len(key.strip())}, has spaces/newlines inside: {any(c.isspace() for c in key.strip())}, "
          f"starts with 'Bearer': {key.strip().lower().startswith('bearer')}, dots: {key.count('.')}")
    for name, hdr in (("Bearer", f"Bearer {key.strip()}"), ("raw", key.strip())):
        req = urllib.request.Request(API, data=json.dumps({"query": "query { account { id } }"}).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "User-Agent": "lockman-site/1.0", "Authorization": hdr})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"  {name}: HTTP {r.status} {r.read()[:150]!r}")
        except urllib.error.HTTPError as ex:
            print(f"  {name}: HTTP {ex.code} {ex.read()[:150]!r}")
        except urllib.error.URLError as ex:
            print(f"  {name}: connection failed {ex}")


def channels():
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    out = []
    for org in orgs:
        q = 'query { channels(input: {organizationId: "%s"}) { id name displayName service isQueuePaused } }'
        out.extend(gql(q % org["id"])["channels"])
    return out


def caption(video, service):
    title = video["title"]
    desc = video.get("description", "")
    if service == "youtube":
        return (f"{desc}\n\nLockman ASAP Locksmith: 24/7 mobile locksmith in San Francisco. "
                f"30 years of experience, a family trade.\nCall {PHONE}\n"
                "https://lockmanasaplocksmith.com\n\n" + TAGS)
    return f"{title}\n\n{desc}\n\nLocked out? Call Lockman: {PHONE}\n\n{TAGS}"


def metadata(video, service):
    if service == "youtube":
        return {"youtube": {"title": video["title"][:100], "categoryId": "26", "madeForKids": False}}
    if service == "instagram":
        return {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    if service == "tiktok":
        return {"tiktok": {"title": video["title"][:90]}}
    return None


CREATE = """mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id } }
    ... on MutationError { message }
  }
}"""


def post(video, channel, video_url, dry_run=False):
    inp = {
        "text": caption(video, channel["service"]),
        "channelId": channel["id"],
        "schedulingType": "automatic",
        "mode": "shareNow",
        "assets": [{"video": {"url": video_url, "metadata": {"thumbnailOffset": 2000}}}],
    }
    meta = metadata(video, channel["service"])
    if meta:
        inp["metadata"] = meta
    if dry_run:
        print("DRY RUN", json.dumps(inp)[:400])
        return "dry-run"
    res = gql(CREATE, {"input": inp})["createPost"]
    if res.get("post"):
        return res["post"]["id"]
    raise BufferError(res.get("message", "unknown error"))


def due(video):
    state = video.get("buffer")
    if state == "hold":
        return False
    if state is None and video.get("published_at", "") < START:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        chs = channels()
    except BufferError as ex:
        print(f"Buffer: FAILED - {ex}")
        diagnose()
        return 1
    print("Buffer key works. Channels:")
    for c in chs:
        print(f"  {c['service']}: {c.get('displayName') or c['name']}"
              + (" [queue paused]" if c.get("isQueuePaused") else ""))
    if args.check:
        return 0

    cfg = common.load_config()
    videos = json.loads(VIDEOS_FILE.read_text(encoding="utf-8")) if VIDEOS_FILE.exists() else []
    changed = False
    for v in videos:
        if not due(v):
            continue
        state = v.get("buffer") if isinstance(v.get("buffer"), dict) else {}
        url = f"{cfg['site_url']}/assets/videos/{v['slug']}.mp4"
        for c in chs:
            done = state.get(c["id"], "")
            if done and not done.startswith("error"):
                continue
            if done.count("error") >= 3:  # tried 3 times, stop
                continue
            try:
                state[c["id"]] = post(v, c, url, args.dry_run)
                print(f"Posted '{v['slug']}' to {c['service']}")
            except BufferError as ex:
                state[c["id"]] = (done + " | " if done else "") + f"error: {str(ex)[:200]}"
                print(f"FAILED '{v['slug']}' on {c['service']}: {ex}")
            changed = True
        v["buffer"] = state
    if changed and not args.dry_run:
        VIDEOS_FILE.write_text(json.dumps(videos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
