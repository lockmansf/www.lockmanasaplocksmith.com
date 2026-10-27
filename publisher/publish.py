"""Publishes at most one original article per day, at a different hour each day.

Runs every hour (GitHub Actions). Each run:
  1. Picks today's publish hour (random, never the same as yesterday's).
  2. Exits if it's too early, today's article is out, or today's attempts are used up.
  3. Writes an article with Gemini, then checks it:
       - structure and length
       - not similar to our own existing articles
       - not similar to anything on the web (Copyscape)
  4. Publishes only if every check passes. A failed attempt publishes nothing.

Usage: python3 -m publisher.publish [--now] [--dry-run]
  --now      ignore the scheduled hour (publish now if today's article isn't out yet)
  --dry-run  run every step but don't save anything
"""
import argparse
import datetime as dt
import json
import random
import sys
from zoneinfo import ZoneInfo

from publisher import common, gemini, originality


def target_hour(day, previous_hour, start, end):
    hour = random.Random(f"lockman-{day.isoformat()}").randint(start, end)
    if hour == previous_hour:
        hour = start + (hour - start + 1) % (end - start + 1)
    return hour


def validate(a, min_words):
    for field in ("title", "description", "intro", "sections"):
        if not a.get(field):
            return f"missing '{field}'"
    if not isinstance(a["sections"], list) or len(a["sections"]) < 3:
        return "fewer than 3 sections"
    for s in a["sections"]:
        if not s.get("heading") or not isinstance(s.get("paragraphs", []), list):
            return "malformed section"
    if len(a["title"]) > 75:
        return "title too long"
    words = common.word_count(common.article_text(a))
    if words < min_words:
        return f"too short ({words} words, need {min_words})"
    return None


def pick_topic(log):
    topics = json.loads(common.TOPICS_FILE.read_text(encoding="utf-8")) if common.TOPICS_FILE.exists() else []
    for t in topics:
        if t not in log["used_topics"]:
            return t
    return None


def generate_one(cfg, log, day_entry, dry_run=False, now=None):
    """One attempt. Returns the saved article dict, or None on failure (nothing published)."""
    acfg = cfg["articles"]
    now = now or dt.datetime.now(ZoneInfo(acfg["timezone"]))
    existing = common.load_articles(status=None)
    topic = pick_topic(log)
    day_entry["attempts"] += 1

    def fail(reason):
        day_entry["failures"].append({"at": now.isoformat(timespec="minutes"), "topic": topic, "reason": reason})
        print(f"Attempt failed, nothing published: {reason}")
        return None

    try:
        art = gemini.write_article(acfg["gemini_model"], topic, [a["title"] for a in existing], acfg["min_words"])
    except gemini.GeminiError as ex:
        return fail(str(ex))

    problem = validate(art, acfg["min_words"])
    if problem:
        return fail(f"article rejected: {problem}")

    text = common.article_text(art)
    for other in existing:
        sim = common.similarity(text, common.article_text(other))
        if sim > acfg["internal_similarity_limit"]:
            return fail(f"too similar to our own article '{other['slug']}' ({sim:.0%})")

    domain = cfg["site_url"].split("://", 1)[1].strip("/")
    ok, detail = originality.check(text, domain, acfg["web_match_percent_limit"], acfg["web_match_words_limit"])
    if not ok:
        return fail(detail)

    slug = common.slugify(art["title"])
    taken = {a["slug"] for a in existing}
    base, n = slug, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1

    article = {
        "slug": slug,
        "title": art["title"].strip(),
        "description": art["description"].strip(),
        "intro": art["intro"].strip(),
        "sections": art["sections"],
        "faq": art.get("faq", [])[:5],
        "topic": topic,
        "published_at": now.isoformat(timespec="seconds"),
        "status": "published" if acfg.get("auto_publish", True) else "draft",
        "originality": {"checked_at": now.isoformat(timespec="minutes"), "result": detail},
    }
    if dry_run:
        print(f"[dry run] would publish: {article['title']}")
        return article
    common.save_article(article)
    if topic:
        log["used_topics"].append(topic)
    day_entry["published"] = slug
    print(f"Published: {article['title']} -> /articles/{slug}/")
    return article


def day_entry_for(log, day, start, end):
    key = day.isoformat()
    if key not in log["days"]:
        prev = log["days"].get((day - dt.timedelta(days=1)).isoformat(), {}).get("target_hour")
        log["days"][key] = {"target_hour": target_hour(day, prev, start, end), "attempts": 0, "published": None, "failures": []}
    return log["days"][key]


def run(force_now=False, dry_run=False, now=None):
    cfg = common.load_config()
    acfg = cfg["articles"]
    now = now or dt.datetime.now(ZoneInfo(acfg["timezone"]))
    log = common.load_log()
    entry = day_entry_for(log, now.date(), acfg["publish_window_start_hour"], acfg["publish_window_end_hour"])

    if entry["published"]:
        print(f"Already published today: {entry['published']}")
        return 0
    if not force_now and now.hour < entry["target_hour"]:
        print(f"Not yet. Today's publish hour is {entry['target_hour']}:00 ({acfg['timezone']}).")
        if not dry_run:
            common.save_log(log)
        return 0

    published = None
    while entry["attempts"] < acfg["max_attempts_per_day"] and not published:
        published = generate_one(cfg, log, entry, dry_run=dry_run, now=now)
    if not published and entry["attempts"] >= acfg["max_attempts_per_day"]:
        print("No article today: all attempts failed. Nothing was published.")
    if not dry_run:
        common.save_log(log)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--now", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(run(force_now=args.now, dry_run=args.dry_run))
