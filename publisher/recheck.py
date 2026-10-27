"""Weekly re-check: published articles are checked against the web again.

If an article now matches text elsewhere online, it is removed from the site
right away (moved to content/removed/) and a replacement article is written.

Usage: python3 -m publisher.recheck
"""
import datetime as dt
import shutil
import sys
from zoneinfo import ZoneInfo

from publisher import common, originality, publish


def run():
    cfg = common.load_config()
    acfg = cfg["articles"]
    now = dt.datetime.now(ZoneInfo(acfg["timezone"]))
    domain = cfg["site_url"].split("://", 1)[1].strip("/")
    articles = common.load_articles()
    articles.sort(key=lambda a: a.get("originality", {}).get("checked_at", ""))
    removed = 0

    for a in articles[: acfg["recheck_per_week"]]:
        ok, detail = originality.check(common.article_text(a), domain, acfg["web_match_percent_limit"], acfg["web_match_words_limit"])
        if ok:
            a["originality"] = {"checked_at": now.isoformat(timespec="minutes"), "result": detail}
            common.save_article(a)
            print(f"OK: {a['slug']}")
            continue
        if detail.startswith(("Copyscape check failed", "Copyscape error", "Copyscape credentials")):
            print(f"Skipped {a['slug']}: {detail}")  # the check itself failed; don't remove on an error
            continue
        common.REMOVED_DIR.mkdir(parents=True, exist_ok=True)
        a["status"] = "removed"
        a["removed"] = {"at": now.isoformat(timespec="minutes"), "reason": detail}
        common.save_article(a)
        shutil.move(str(a["_file"]), common.REMOVED_DIR / a["_file"].name)
        removed += 1
        print(f"REMOVED: {a['slug']}: {detail}")

    # One replacement per removed article, each with the normal checks.
    log = common.load_log()
    for _ in range(removed):
        entry = {"target_hour": now.hour, "attempts": 0, "published": None, "failures": []}
        art = None
        while not art and entry["attempts"] < acfg["max_attempts_per_day"]:
            art = publish.generate_one(cfg, log, entry, now=now)
        log.setdefault("replacements", []).append({"at": now.isoformat(timespec="minutes"), **entry})
    common.save_log(log)
    return 0


if __name__ == "__main__":
    sys.exit(run())
