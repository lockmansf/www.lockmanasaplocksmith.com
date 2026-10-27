"""Checks text against the whole web with the Copyscape Premium API.

Returns (is_original, details). Any error counts as NOT original, so nothing is
published unless the check actually ran and passed.
"""
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API = "https://www.copyscape.com/api/"


def check(text, own_domain, percent_limit, words_limit):
    if os.environ.get("LOCKMAN_MOCK"):
        from publisher import mock
        return mock.fake_check(text)
    user, key = os.environ.get("COPYSCAPE_USER"), os.environ.get("COPYSCAPE_KEY")
    if not user or not key:
        return False, "Copyscape credentials missing: refusing to publish without a web originality check"
    form = urllib.parse.urlencode({"u": user, "k": key, "o": "csearch", "e": "UTF-8", "c": "5", "t": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(API, data=form, method="POST"), timeout=120) as r:
            root = ET.fromstring(r.read())
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as ex:
        return False, f"Copyscape check failed: {ex}"
    err = root.findtext("error")
    if err:
        return False, f"Copyscape error: {err}"
    matches = []
    for res in root.findall("result"):
        url = res.findtext("url") or ""
        if own_domain and own_domain in url:
            continue  # our own published copy
        words = int(res.findtext("minwordsmatched") or 0)
        pct = int(res.findtext("percentmatched") or 0)
        if words >= words_limit or pct >= percent_limit:
            matches.append(f"{url} ({words} words, {pct}%)")
    if matches:
        return False, "Similar text found online: " + "; ".join(matches[:5])
    return True, "No matching text found online"
