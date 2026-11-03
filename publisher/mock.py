"""Offline stand-ins for Gemini and Copyscape. Active when LOCKMAN_MOCK=1 (tests and previews)."""
import os

LOREM = ("Salt air from the bay and the constant San Francisco fog work their way into door hardware, "
         "and a lock that turned smoothly last year can start to drag today. ")


def fake_article(topic):
    if os.environ.get("LOCKMAN_MOCK") == "fail-gemini":
        from publisher.gemini import GeminiError
        raise GeminiError("mock failure")
    t = topic or "Keeping your locks working in the fog"
    para = lambda i: f"[{t} {i}] " + LOREM * 6 + f"Point {i} for {t}."
    return {
        "title": t[:60],
        "description": ("A practical San Francisco guide: " + t)[:150].ljust(140, "."),
        "intro": para(0),
        "sections": [{"heading": f"Part {i}", "paragraphs": [para(i), para(i + 10)], "bullets": []} for i in range(1, 5)],
        "faq": [{"question": "Is this a test?", "answer": "Yes, this is mock content."}],
    }


def fake_check(text):
    if os.environ.get("LOCKMAN_MOCK") == "fail-copyscape":
        return False, "Similar text found online: https://example.com/copied (80 words, 12%)"
    return True, "No matching text found online (mock)"


def fake_graph(method, path, params):
    if os.environ.get("LOCKMAN_MOCK") == "fail-meta":
        from publisher.social import MetaError
        raise MetaError("mock Meta failure")
    if path == "me":
        return {"id": "111", "name": "Lockman", "instagram_business_account": {"id": "222"}}
    if path.endswith("/feed"):
        return {"id": "111_fbpost"}
    if path.endswith("/media"):
        return {"id": "container1"}
    if path.endswith("/media_publish"):
        return {"id": "igpost1"}
    return {"status_code": "FINISHED"}
