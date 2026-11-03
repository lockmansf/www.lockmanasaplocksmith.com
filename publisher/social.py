"""Weekly Facebook + Instagram post about the newest article.

Runs every hour with the site job. Posts only when at least `every_days` days
have passed since the last post and the local time is inside the posting window.
A failure on one network is recorded and does not block the other.

Needs one secret: META_PAGE_TOKEN (a Page access token with pages_manage_posts,
pages_read_engagement, instagram_basic and instagram_content_publish).
The Page ID and the linked Instagram account are looked up from the token.

Usage: python3 -m publisher.social [--now] [--dry-run]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from publisher import common, gemini

LOG_FILE = common.ROOT / "content" / "social_log.json"

CAPTION_PROMPT = """Write social media captions for Lockman ASAP Locksmith, a licensed 24/7 mobile locksmith in San Francisco.
They promote this new article on the website:

Title: {title}
Summary: {description}

Rules:
- Friendly, confident, a little superhero flavor (the brand mascot is Lockman, a locksmith superhero). No exaggeration.
- Do NOT invent prices, discounts, arrival times, statistics, reviews or customer stories.
- Facebook: 2-4 short sentences, end with "Read more:" (the link is added separately) and a call line with the phone.
- Instagram: 3-5 short lines, then the phone, then "Link in bio", then 6-10 relevant hashtags (#SanFrancisco #Locksmith ...).
- Phone: (415) 806-7343. Do not include URLs in the Instagram caption.

Return ONLY JSON: {{"facebook": "...", "instagram": "..."}}"""


class MetaError(Exception):
    pass


def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {"posts": [], "failures": []}


def save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def graph(method, path, version, token, **params):
    if os.environ.get("LOCKMAN_MOCK"):
        from publisher import mock
        return mock.fake_graph(method, path, params)
    params["access_token"] = token
    url = f"https://graph.facebook.com/{version}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as ex:
        try:
            msg = json.loads(ex.read())["error"]["message"]
        except (ValueError, KeyError):
            msg = f"HTTP {ex.code}"
        raise MetaError(msg) from ex
    except urllib.error.URLError as ex:
        raise MetaError(f"connection failed: {ex}") from ex


def accounts(version, token):
    """The Page ID and the linked Instagram business account ID for this Page token."""
    me = graph("GET", "me", version, token, fields="id,name,instagram_business_account")
    ig = (me.get("instagram_business_account") or {}).get("id")
    return me["id"], me.get("name", ""), ig


def captions(article, cfg):
    fallback = {
        "facebook": f"{article['title']}\n\n{article['description']}\n\nNeed a locksmith in San Francisco? Call (415) 806-7343, 24/7.\nRead more:",
        "instagram": f"{article['title']}\n\n{article['description']}\n\n📞 (415) 806-7343 · 24/7\nLink in bio\n\n#SanFrancisco #Locksmith #SFLocksmith #Lockout #LockmanASAP",
    }
    if os.environ.get("LOCKMAN_MOCK"):
        return fallback
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return fallback
    body = {"contents": [{"role": "user", "parts": [{"text": CAPTION_PROMPT.format(**article)}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(gemini.API.format(model=cfg["articles"]["gemini_model"]), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        out = json.loads("".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]))
        if out.get("facebook") and out.get("instagram"):
            return {"facebook": out["facebook"].strip(), "instagram": out["instagram"].strip()[:2100]}
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        pass
    return fallback  # a plain caption is better than skipping the week


def post_instagram(version, token, ig_id, image_url, caption):
    container = graph("POST", f"{ig_id}/media", version, token, image_url=image_url, caption=caption)["id"]
    for _ in range(12):  # Instagram processes the image before it can be published
        status = graph("GET", container, version, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise MetaError("Instagram could not process the image")
        time.sleep(5)
    return graph("POST", f"{ig_id}/media_publish", version, token, creation_id=container)["id"]


def run(force_now=False, dry_run=False, now=None):
    cfg = common.load_config()
    scfg = cfg["social_posting"]
    tz = ZoneInfo(cfg["articles"]["timezone"])
    now = now or dt.datetime.now(tz)
    log = load_log()
    token = (os.environ.get("META_PAGE_TOKEN") or "").strip()
    if not token and not os.environ.get("LOCKMAN_MOCK"):
        print("META_PAGE_TOKEN not set: social posting is off")
        return 0

    last = log["posts"][-1]["at"] if log["posts"] else None
    if not force_now:
        if last and now - dt.datetime.fromisoformat(last) < dt.timedelta(days=scfg["every_days"]):
            print(f"Last social post {last}; next one after {scfg['every_days']} days")
            return 0
        if not scfg["window_start_hour"] <= now.hour < scfg["window_end_hour"]:
            print("Outside the posting window")
            return 0

    posted_slugs = {p["slug"] for p in log["posts"]}
    articles = sorted(common.load_articles(), key=lambda a: a["published_at"], reverse=True)
    article = next((a for a in articles if a["slug"] not in posted_slugs), None)
    if not article:
        print("No new article to share")
        return 0

    link = f"{cfg['site_url']}/articles/{article['slug']}/"
    images = scfg["images"]
    image_url = f"{cfg['site_url']}/assets/social/{images[len(log['posts']) % len(images)]}"
    text = captions(article, cfg)
    if dry_run:
        print(json.dumps({"link": link, "image": image_url, **text}, indent=2, ensure_ascii=False))
        return 0

    version = scfg["graph_version"]
    entry = {"at": now.isoformat(timespec="minutes"), "slug": article["slug"]}
    try:
        page_id, page_name, ig_id = accounts(version, token)
    except MetaError as ex:
        log["failures"].append({"at": entry["at"], "reason": f"token check failed: {ex}"})
        save_log(log)
        print(f"Social post skipped: {ex}")
        return 0

    try:
        entry["facebook"] = graph("POST", f"{page_id}/feed", version, token, message=text["facebook"], link=link)["id"]
    except MetaError as ex:
        entry["facebook_error"] = str(ex)
    if ig_id:
        try:
            entry["instagram"] = post_instagram(version, token, ig_id, image_url, text["instagram"])
        except MetaError as ex:
            entry["instagram_error"] = str(ex)
    else:
        entry["instagram_error"] = "no Instagram business account linked to the Page"

    if "facebook" in entry or "instagram" in entry:
        log["posts"].append(entry)
    else:
        log["failures"].append({"at": entry["at"], "reason": entry})
    save_log(log)
    print(json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--now", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sys.exit(run(force_now=a.now, dry_run=a.dry_run))
