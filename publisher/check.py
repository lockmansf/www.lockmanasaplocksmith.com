"""Checks that the Gemini and Copyscape keys work, without publishing anything.

Usage: python3 -m publisher.check
Prints only OK / the error, never the keys themselves. Copyscape's balance
check is free; it does not use a search credit.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from publisher import common

MODELS = "https://generativelanguage.googleapis.com/v1beta/models"


def check_gemini(model):
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return False, "GEMINI_API_KEY secret is missing"
    body = {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word OK."}]}]}
    req = urllib.request.Request(f"{MODELS}/{model}:generateContent", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        for wait in (20, 60, None):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    json.loads(r.read())
                break
            except urllib.error.HTTPError as ex:
                if ex.code in (429, 500, 503) and wait:
                    time.sleep(wait)
                    continue
                raise
        return True, f"Gemini key works with model {model}"
    except urllib.error.HTTPError as ex:
        detail = ex.read()[:300].decode(errors="replace")
        if ex.code == 404:
            return False, f"model '{model}' not found. Available: {', '.join(available_models(key))}"
        return False, f"Gemini HTTP {ex.code}: {detail}"
    except urllib.error.URLError as ex:
        return False, f"Gemini connection failed: {ex}"


def available_models(key):
    try:
        req = urllib.request.Request(MODELS + "?pageSize=200", headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=60) as r:
            names = [m["name"].split("/", 1)[1] for m in json.loads(r.read()).get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        return [n for n in names if "flash" in n] or names
    except (urllib.error.URLError, KeyError, ValueError):
        return ["(could not list models)"]


def check_copyscape():
    user, key = (os.environ.get("COPYSCAPE_USER") or "").strip(), (os.environ.get("COPYSCAPE_KEY") or "").strip()
    if not user or not key:
        return False, "COPYSCAPE_USER / COPYSCAPE_KEY secrets are missing"
    url = "https://www.copyscape.com/api/?" + urllib.parse.urlencode({"u": user, "k": key, "o": "balance"})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            root = ET.fromstring(r.read())
    except (urllib.error.URLError, ET.ParseError) as ex:
        return False, f"Copyscape connection failed: {ex}"
    if root.findtext("error"):
        return False, (f"Copyscape error: {root.findtext('error')} "
                       f"(username is {len(user)} characters{', contains @' if '@' in user else ''}; key is {len(key)} characters)")
    return True, f"Copyscape works. Balance: ${root.findtext('value')} ({root.findtext('total')} searches left)"


def main():
    cfg = common.load_config()
    results = [check_gemini(cfg["articles"]["gemini_model"]), check_copyscape()]
    for ok, msg in results:
        print(("OK:   " if ok else "FAIL: ") + msg)
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
