"""Writes an article with the Gemini API (REST, standard library only)."""
import json
import os
import time
import urllib.error
import urllib.request

RETRY_WAITS = [30, 90, 180]  # seconds between retries when Gemini is overloaded

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You write articles for the website of Lockman ASAP Locksmith, a licensed mobile locksmith in San Francisco, California.
Services: home, business and car lockouts, broken key extraction, lock repair.

Write ONE new, completely original article.
{topic_line}

Existing article titles on the site. Do NOT repeat or closely paraphrase any of them:
{existing}

Rules:
- Write in your own words from scratch. Never copy, adapt or paraphrase text from any website, book or article.
- Practical and genuinely useful for San Francisco residents and businesses. Mention San Francisco specifics only when they are true and relevant (fog and salt air corrode locks, Victorian doors, apartment buildings, street parking, and so on).
- {min_words}-1100 words in total. Plain, friendly English. Short paragraphs.
- Do NOT invent prices, statistics, laws, customer stories, reviews, awards or years of experience.
- Do NOT promise or estimate arrival times, response times or costs.
- Do NOT give step-by-step instructions for opening locks the reader does not own or for bypassing security.
- Do NOT mention competitors.
- The title must be under 65 characters. The description must be 140-155 characters.

Return ONLY JSON in exactly this shape:
{{
  "title": "...",
  "description": "...",
  "intro": "one paragraph",
  "sections": [{{"heading": "...", "paragraphs": ["..."], "bullets": ["optional", "..."]}}],
  "faq": [{{"question": "...", "answer": "..."}}]
}}
Use 4 to 6 sections and 3 FAQ items."""


class GeminiError(Exception):
    pass


def build_prompt(topic, existing_titles, min_words):
    topic_line = f"Topic: {topic}" if topic else "Choose a fresh, useful topic that is not covered by the existing titles."
    existing = "\n".join(f"- {t}" for t in existing_titles) or "- (none yet)"
    return PROMPT.format(topic_line=topic_line, existing=existing, min_words=min_words)


def write_article(model, topic, existing_titles, min_words):
    if os.environ.get("LOCKMAN_MOCK"):
        from publisher import mock
        return mock.fake_article(topic)
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    body = {
        "contents": [{"role": "user", "parts": [{"text": build_prompt(topic, existing_titles, min_words)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        API.format(model=model),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    data = None
    for wait in RETRY_WAITS + [None]:
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 503) and wait is not None:
                time.sleep(wait)  # Google is temporarily overloaded; wait and try again
                continue
            raise GeminiError(f"Gemini HTTP {ex.code}: {ex.read()[:400]!r}") from ex
        except (urllib.error.URLError, TimeoutError) as ex:
            raise GeminiError(f"Gemini connection failed: {ex}") from ex
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as ex:
        raise GeminiError(f"Gemini returned unusable output: {str(data)[:400]}") from ex
