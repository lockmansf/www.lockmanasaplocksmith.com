"""Shared helpers for the article publisher."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "content" / "articles"
REMOVED_DIR = ROOT / "content" / "removed"
LOG_FILE = ROOT / "content" / "publish_log.json"
TOPICS_FILE = ROOT / "content" / "topics.json"


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {"days": {}, "used_topics": []}


def save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_articles(status="published"):
    out = []
    for f in sorted(ARTICLES_DIR.glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        if status is None or a.get("status", "published") == status:
            a["_file"] = f
            out.append(a)
    return out


def save_article(article):
    data = {k: v for k, v in article.items() if not k.startswith("_")}
    path = ARTICLES_DIR / f"{article['slug']}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def article_text(a):
    """Plain text of an article, used for word counts and originality checks."""
    parts = [a.get("title", ""), a.get("intro", "")]
    for s in a.get("sections", []):
        parts.append(s.get("heading", ""))
        parts.extend(s.get("paragraphs", []))
        parts.extend(s.get("bullets", []))
    for q in a.get("faq", []):
        parts.extend([q.get("question", ""), q.get("answer", "")])
    return "\n".join(p for p in parts if p)


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+", text))


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:70].rstrip("-") or "article"


def shingles(text, n=5):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similarity(a_text, b_text):
    """Jaccard similarity of 5-word shingles: 0 = nothing shared, 1 = identical."""
    a, b = shingles(a_text), shingles(b_text)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
