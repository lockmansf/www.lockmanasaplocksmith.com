# Lockman ASAP Locksmith website

Static site for https://lockmanasaplocksmith.com, hosted free on GitHub Pages.

## Edit business details
Fill every `TODO` value in `config.json` (phone, WhatsApp, license, email, hours, Google Analytics ID).
The logo lives in `assets/img/` (`logo-full-600.webp`, `emblem.png`, `favicon.png`).

## Build locally
    python3 build.py        # output in dist/
    python3 -m unittest discover -s tests -t .

## Daily articles
`.github/workflows/site.yml` runs every hour. `publisher/publish.py` publishes at most one article a day,
at a random hour between 8:00 and 20:00 Pacific, never the same hour as the day before.
An article goes live only if it passes: structure and length, similarity against our own articles,
and a Copyscape web check. A failed attempt publishes nothing; there are at most 3 attempts a day.
Every Monday, `publisher/recheck.py` re-checks up to 15 articles, removes any that now match text
online, and writes a replacement.

Repository secrets needed: `GEMINI_API_KEY`, `COPYSCAPE_USER`, `COPYSCAPE_KEY`.
Topics are in `content/topics.json`; after they run out, Gemini picks new topics.

## Go live
1. Push this folder to a GitHub repository (branch `main`).
2. Settings > Pages > Source: GitHub Actions.
3. Settings > Secrets and variables > Actions: add the three secrets.
4. At your domain registrar, point DNS to GitHub Pages (A records 185.199.108.153, .109.153,
   .110.153, .111.153 and a CNAME `www` -> `<github-user>.github.io`), then set the custom domain
   in Settings > Pages and enable "Enforce HTTPS".
5. Add the site to Google Search Console and submit `/sitemap.xml`.
