#!/usr/bin/env python3
"""Builds the static site into dist/.

Run: python3 build.py
Reads config.json and content/articles/*.json. Uses only the Python standard library.
"""
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ARTICLES_DIR = ROOT / "content" / "articles"

e = html.escape


def load_config():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    todos = [k for k, v in cfg.items() if isinstance(v, str) and v.startswith("TODO")]
    for k in todos:
        print(f"WARNING: config.json '{k}' is still a placeholder", file=sys.stderr)
    return cfg


def clean(value):
    """Strip the TODO marker so placeholders render readably during preview."""
    return value[5:] if isinstance(value, str) and value.startswith("TODO ") else value


def load_articles():
    items = []
    for f in sorted(ARTICLES_DIR.glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        if a.get("status", "published") == "published":
            items.append(a)
    items.sort(key=lambda a: a["published_at"], reverse=True)
    return items


# ---------------------------------------------------------------- services

SERVICES = [
    {
        "slug": "lockout",
        "name": "Lockout Service",
        "short": "Locked out of your home or business? We get you back inside without damaging the door.",
        "title": "Lockout Service in San Francisco",
        "intro": "Being locked out is stressful, especially in the fog at night. Call us, tell us where you are, and a licensed locksmith comes to you to open the door the right way.",
        "points": [
            ("Non-destructive entry first", "We use picking and bypass tools before anything else, so in most cases your lock keeps working after we open it."),
            ("Proof of residence", "For your safety we ask for ID or proof that you live or work at the address before we open the door."),
            ("Clear price before we start", "We give you the price on the phone and confirm it on site before any work begins. No surprise add-ons."),
            ("Rekey or replace if needed", "Lost your keys? We can rekey the lock on the spot so the old keys stop working."),
        ],
    },
    {
        "slug": "broken-key-extraction",
        "name": "Broken Key Extraction",
        "short": "Key snapped inside the lock? We remove it cleanly and cut you a new one.",
        "title": "Broken Key Extraction in San Francisco",
        "intro": "A key that breaks inside the cylinder is common with worn keys and stiff locks. Pushing at it with tweezers usually drives it deeper. We use proper extractors to pull it out without harming the lock.",
        "points": [
            ("Clean extraction", "Specialized extractor tools pull the broken piece out without scratching the pins."),
            ("Replacement key", "We can cut a new key so you are not left with half a key."),
            ("Find the cause", "A key usually breaks because the lock is stiff or the key is worn. We check the lock and tell you if it needs service."),
            ("Doors, mailboxes and padlocks", "Front doors, back doors, mailboxes, gates and padlocks."),
        ],
    },
    {
        "slug": "lock-repair",
        "name": "Lock Repair",
        "short": "Sticking, jammed or loose locks fixed on site, so your door locks the way it should.",
        "title": "Lock Repair in San Francisco",
        "intro": "A lock that sticks, jams or turns loosely is a warning sign. We repair it before it fails and leaves you locked out, or locked in.",
        "points": [
            ("Sticking and stiff locks", "Cleaning, lubrication and adjustment of worn cylinders."),
            ("Loose handles and deadbolts", "Tightening and realigning hardware so the bolt throws fully."),
            ("Door alignment", "A door that dropped out of line strains the lock. We adjust the strike plate so it closes smoothly."),
            ("Repair or replace, honestly", "If the lock is worth fixing, we fix it. If it is not, we tell you and show you the options."),
        ],
    },
]


# ---------------------------------------------------------------- layout

def nav_links():
    return [
        ("/services/", "Services"),
        ("/service-area/", "Service Area"),
        ("/articles/", "Articles"),
        ("/about/", "About"),
        ("/contact/", "Contact"),
    ]


def whatsapp_url(cfg):
    num = "".join(ch for ch in clean(cfg["whatsapp_number"]) if ch.isdigit())
    return f"https://wa.me/{num}?text={quote(cfg['whatsapp_message'])}"


def tel(cfg):
    return "tel:" + "".join(ch for ch in clean(cfg["phone_e164"]) if ch.isdigit() or ch == "+")


def business_schema(cfg):
    data = {
        "@context": "https://schema.org",
        "@type": "Locksmith",
        "@id": cfg["site_url"] + "/#business",
        "name": cfg["business_name"],
        "url": cfg["site_url"] + "/",
        "telephone": clean(cfg["phone_e164"]),
        "image": cfg["site_url"] + "/assets/img/og-image.png",
        "logo": cfg["site_url"] + "/assets/img/logo.svg",
        "address": {"@type": "PostalAddress", "addressLocality": cfg["city"], "addressRegion": cfg["region"], "addressCountry": "US"},
        "areaServed": [{"@type": "City", "name": "San Francisco"}] + [{"@type": "Place", "name": f"{a}, San Francisco"} for a in cfg["service_areas"]],
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Locksmith services",
            "itemListElement": [{"@type": "Offer", "itemOffered": {"@type": "Service", "name": s["name"], "url": f"{cfg['site_url']}/services/{s['slug']}/"}} for s in SERVICES],
        },
    }
    if cfg.get("opening_hours_schema"):
        data["openingHoursSpecification"] = cfg["opening_hours_schema"]
    return data


def breadcrumb_schema(cfg, crumbs):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": cfg["site_url"] + path}
            for i, (path, name) in enumerate(crumbs)
        ],
    }


def page(cfg, *, path, title, description, body, schemas=(), crumbs=None, og_type="website"):
    full_title = title if cfg["business_name"] in title else f"{title} | {cfg['business_name']}"
    canonical = cfg["site_url"] + path
    schema_list = [business_schema(cfg), *schemas]
    if crumbs:
        schema_list.append(breadcrumb_schema(cfg, crumbs))
    schema_html = "\n".join(
        f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schema_list
    )
    ga_id = cfg["google_analytics_id"]
    ga_attr = "" if ga_id.startswith("TODO") else f' data-ga-id="{e(ga_id)}"'
    verify = (
        f'<meta name="google-site-verification" content="{e(cfg["google_site_verification"])}">'
        if cfg.get("google_site_verification") else ""
    )
    nav = "".join(
        f'<li><a href="{href}"{" aria-current=\"page\"" if path.startswith(href) else ""}>{label}</a></li>'
        for href, label in nav_links()
    )
    crumb_html = ""
    if crumbs and len(crumbs) > 1:
        parts = []
        for i, (p, name) in enumerate(crumbs):
            if i == len(crumbs) - 1:
                parts.append(f'<li aria-current="page">{e(name)}</li>')
            else:
                parts.append(f'<li><a href="{p}">{e(name)}</a></li>')
        crumb_html = f'<nav class="crumbs wrap" aria-label="Breadcrumb"><ol>{"".join(parts)}</ol></nav>'
    phone = e(clean(cfg["phone_display"]))
    year = dt.date.today().year
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{cfg['site_url']}/assets/img/og-image.png">
<meta property="og:site_name" content="{e(cfg['business_name'])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0d1321">
{verify}
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{e(cfg['business_name'])} articles" href="/articles/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bangers&family=Inter:wght@400;600;800&display=swap">
<link rel="stylesheet" href="/assets/style.css">
{schema_html}
</head>
<body{ga_attr}>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-row">
    <a class="brand" href="/" aria-label="{e(cfg['business_name'])} home">
      <img src="/assets/img/logo.svg" alt="" width="44" height="44">
      <span class="brand-text">Lockman <b>ASAP</b></span>
    </a>
    <button class="menu-btn" aria-expanded="false" aria-controls="site-nav">
      <span class="menu-icon" aria-hidden="true"></span><span class="menu-label">Menu</span>
    </button>
    <nav id="site-nav" class="site-nav" aria-label="Main">
      <ul>{nav}</ul>
    </nav>
    <a class="btn btn-call header-call" href="{tel(cfg)}">Call {phone}</a>
  </div>
</header>
{crumb_html}
<main id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap footer-grid">
    <div>
      <p class="footer-brand">{e(cfg['business_name'])}</p>
      <p>Mobile locksmith serving {e(cfg['city'])}, {e(cfg['region'])}.</p>
      <p>California Locksmith License: <strong>{e(clean(cfg['license_number']))}</strong></p>
    </div>
    <div>
      <p class="footer-head">Contact</p>
      <p><a href="{tel(cfg)}">{phone}</a></p>
      <p><a href="{whatsapp_url(cfg)}" rel="noopener">WhatsApp</a></p>
      <p>{e(clean(cfg['hours_text']))}</p>
    </div>
    <div>
      <p class="footer-head">Services</p>
      {''.join(f'<p><a href="/services/{s["slug"]}/">{e(s["name"])}</a></p>' for s in SERVICES)}
    </div>
    <div>
      <p class="footer-head">Legal</p>
      <p><a href="/privacy/">Privacy Policy</a></p>
      <p><a href="/terms/">Terms of Service</a></p>
      <p><a href="/accessibility/">Accessibility</a></p>
      <p><button type="button" class="link-btn" data-cookie-settings>Cookie settings</button></p>
    </div>
  </div>
  <p class="wrap copyright">&copy; {year} {e(cfg['business_name'])}. All artwork is original and owned by {e(cfg['business_name'])}.</p>
</footer>
<a class="wa-float" href="{whatsapp_url(cfg)}" rel="noopener" aria-label="Chat with us on WhatsApp">
  <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true"><path fill="currentColor" d="M16 3a13 13 0 0 0-11.2 19.6L3 29l6.6-1.7A13 13 0 1 0 16 3zm0 23.7a10.7 10.7 0 0 1-5.5-1.5l-.4-.2-3.9 1 1-3.8-.2-.4A10.7 10.7 0 1 1 16 26.7zm5.9-8c-.3-.2-1.9-1-2.2-1s-.5-.2-.7.2-.8 1-1 1.2-.4.2-.7 0a8.8 8.8 0 0 1-4.4-3.8c-.3-.6.3-.5 1-1.7.1-.2 0-.4 0-.6l-1-2.4c-.3-.6-.5-.5-.7-.5h-.6a1.2 1.2 0 0 0-.9.4 3.7 3.7 0 0 0-1.1 2.7 6.4 6.4 0 0 0 1.3 3.4 14.7 14.7 0 0 0 5.6 5c2.1.9 2.9 1 4 .8a3.4 3.4 0 0 0 2.2-1.6 2.8 2.8 0 0 0 .2-1.6c0-.2-.3-.3-.6-.4z"/></svg>
</a>
<div class="cookie" role="region" aria-label="Cookie notice" hidden>
  <p>We use Google Analytics cookies to see which pages help visitors. No advertising. <a href="/privacy/">Privacy Policy</a></p>
  <div class="cookie-actions">
    <button type="button" class="btn btn-ghost" data-consent="no">Decline</button>
    <button type="button" class="btn btn-call" data-consent="yes">Accept</button>
  </div>
</div>
<script src="/assets/main.js" defer></script>
</body>
</html>
"""


def cta_block(cfg, heading="Locked out? Key broken? Lock stuck?"):
    return f"""<section class="cta-band">
  <div class="wrap cta-inner">
    <h2 class="comic">{e(heading)}</h2>
    <p>Call or message us now. Tell us where you are in {e(cfg['city'])} and we will be on our way.</p>
    <div class="btn-row">
      <a class="btn btn-call btn-lg" href="{tel(cfg)}">Call {e(clean(cfg['phone_display']))}</a>
      <a class="btn btn-wa btn-lg" href="{whatsapp_url(cfg)}" rel="noopener">WhatsApp us</a>
    </div>
  </div>
</section>"""


def article_card(a):
    d = dt.datetime.fromisoformat(a["published_at"]).date()
    return f"""<article class="card">
  <p class="card-date"><time datetime="{d.isoformat()}">{d.strftime('%B %-d, %Y')}</time></p>
  <h3><a href="/articles/{a['slug']}/">{e(a['title'])}</a></h3>
  <p>{e(a['description'])}</p>
</article>"""


# ---------------------------------------------------------------- pages

def home(cfg, articles):
    services = "".join(
        f"""<article class="card service-card">
  <h3><a href="/services/{s['slug']}/">{e(s['name'])}</a></h3>
  <p>{e(s['short'])}</p>
  <a class="more" href="/services/{s['slug']}/">Learn more<span class="sr"> about {e(s['name'])}</span></a>
</article>""" for s in SERVICES)
    latest = "".join(article_card(a) for a in articles[:3])
    latest_section = f"""<section class="section">
  <div class="wrap">
    <h2 class="comic">Locksmith tips &amp; articles</h2>
    <div class="grid-3">{latest}</div>
    <p class="center"><a class="btn btn-ghost" href="/articles/">All articles</a></p>
  </div>
</section>""" if articles else ""
    body = f"""<section class="hero halftone">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <p class="burst" aria-hidden="true">ASAP!</p>
      <h1 class="comic">San Francisco Locksmith, on the way when you're locked out</h1>
      <p class="lead">Lockouts, broken keys and lock repair. A licensed mobile locksmith who comes to you anywhere in {e(cfg['city'])}.</p>
      <div class="btn-row">
        <a class="btn btn-call btn-lg" href="{tel(cfg)}">Call {e(clean(cfg['phone_display']))}</a>
        <a class="btn btn-wa btn-lg" href="{whatsapp_url(cfg)}" rel="noopener">WhatsApp</a>
      </div>
      <ul class="trust">
        <li>CA License {e(clean(cfg['license_number']))}</li>
        <li>Price confirmed before work</li>
        <li>{e(clean(cfg['hours_text']))}</li>
      </ul>
    </div>
    <div class="hero-art">
      <img src="/assets/img/hero.svg" alt="Lockman, the locksmith superhero, holding a giant key over the San Francisco skyline" width="560" height="560" fetchpriority="high">
    </div>
  </div>
</section>
<section class="section">
  <div class="wrap">
    <h2 class="comic">What we do</h2>
    <div class="grid-3">{services}</div>
  </div>
</section>
<section class="section section-alt">
  <div class="wrap two-col">
    <div>
      <h2 class="comic">How it works</h2>
      <ol class="steps">
        <li><strong>Call or WhatsApp.</strong> Tell us where you are and what happened.</li>
        <li><strong>Get a clear price.</strong> We confirm the price before any work starts.</li>
        <li><strong>We come to you.</strong> A licensed locksmith arrives with the right tools.</li>
        <li><strong>You're back in.</strong> We fix the problem and you pay only the agreed price.</li>
      </ol>
    </div>
    <div class="panel">
      <h2 class="comic">Watch out for locksmith scams</h2>
      <p>Some ads quote a very low "service call" price and then charge far more on site. A real California locksmith shows a state license number. Ours is <strong>{e(clean(cfg['license_number']))}</strong>, and you can check it on the BSIS website.</p>
      <p><a href="https://search.dca.ca.gov/" rel="noopener">Verify a California license</a></p>
    </div>
  </div>
</section>
<section class="section">
  <div class="wrap">
    <h2 class="comic">Serving all of San Francisco</h2>
    <p>{', '.join(e(a) for a in cfg['service_areas'])}, and every neighborhood in between.</p>
    <p><a class="more" href="/service-area/">See our service area</a></p>
  </div>
</section>
{latest_section}
{cta_block(cfg)}"""
    return page(cfg, path="/", title=f"{cfg['business_name']} | San Francisco Locksmith: Lockouts, Broken Keys, Lock Repair",
                description=f"Licensed mobile locksmith in San Francisco. Lockout service, broken key extraction and lock repair. Call {clean(cfg['phone_display'])} or WhatsApp us.",
                body=body)


def services_index(cfg):
    cards = "".join(
        f"""<article class="card service-card"><h2><a href="/services/{s['slug']}/">{e(s['name'])}</a></h2><p>{e(s['short'])}</p></article>"""
        for s in SERVICES)
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">Locksmith Services in San Francisco</h1>
<p class="lead">Everything we do, done on site by a licensed locksmith.</p></div></section>
<section class="section"><div class="wrap grid-3">{cards}</div></section>
{cta_block(cfg)}"""
    return page(cfg, path="/services/", title="Locksmith Services in San Francisco",
                description="Lockout service, broken key extraction and lock repair across San Francisco by a licensed mobile locksmith.",
                body=body, crumbs=[("/", "Home"), ("/services/", "Services")])


def service_page(cfg, s):
    points = "".join(f"<li><h3>{e(h)}</h3><p>{e(t)}</p></li>" for h, t in s["points"])
    others = "".join(f'<li><a href="/services/{o["slug"]}/">{e(o["name"])}</a></li>' for o in SERVICES if o is not s)
    schema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": s["name"],
        "serviceType": s["name"],
        "provider": {"@id": cfg["site_url"] + "/#business"},
        "areaServed": {"@type": "City", "name": "San Francisco"},
        "description": s["intro"],
    }
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">{e(s['title'])}</h1>
<p class="lead">{e(s['intro'])}</p>
<div class="btn-row"><a class="btn btn-call btn-lg" href="{tel(cfg)}">Call {e(clean(cfg['phone_display']))}</a>
<a class="btn btn-wa btn-lg" href="{whatsapp_url(cfg)}" rel="noopener">WhatsApp</a></div></div></section>
<section class="section"><div class="wrap two-col">
<div><h2 class="comic">What to expect</h2><ul class="points">{points}</ul></div>
<aside class="panel"><h2 class="comic">Other services</h2><ul class="plain">{others}</ul>
<p>License: <strong>{e(clean(cfg['license_number']))}</strong></p></aside>
</div></section>
{cta_block(cfg)}"""
    return page(cfg, path=f"/services/{s['slug']}/", title=s["title"], description=s["short"] + " Licensed locksmith in San Francisco.",
                body=body, schemas=[schema], crumbs=[("/", "Home"), ("/services/", "Services"), (f"/services/{s['slug']}/", s["name"])])


def service_area(cfg):
    items = "".join(f"<li>{e(a)}</li>" for a in cfg["service_areas"])
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">Locksmith Service Area: San Francisco</h1>
<p class="lead">We are a mobile locksmith. We come to your home, business or wherever you are locked out in {e(cfg['city'])}.</p></div></section>
<section class="section"><div class="wrap"><h2 class="comic">Neighborhoods we serve</h2><ul class="area-list">{items}</ul>
<p>Don't see your neighborhood? Call us. If you're in San Francisco, we come to you.</p></div></section>
{cta_block(cfg)}"""
    return page(cfg, path="/service-area/", title="Locksmith Service Area in San Francisco",
                description="Mobile locksmith covering every San Francisco neighborhood, from the Mission and SoMa to the Sunset and Richmond.",
                body=body, crumbs=[("/", "Home"), ("/service-area/", "Service Area")])


def about(cfg):
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">About Lockman ASAP Locksmith</h1>
<p class="lead">A local San Francisco locksmith with a superhero name and a simple promise: show up fast, quote honestly, and do the job right.</p></div></section>
<section class="section"><div class="wrap two-col">
<div>
<h2 class="comic">Who we are</h2>
<p>Lockman ASAP Locksmith is owned and run by Yaniv, a licensed California locksmith. Every job is handled by a licensed locksmith, not a call center.</p>
<p>The comic art on this site is original artwork created for Lockman. The hero stands for what we want every customer to feel when we arrive: help is here.</p>
<h2 class="comic">Our promise</h2>
<ul class="points">
<li><h3>Licensed</h3><p>California Locksmith License {e(clean(cfg['license_number']))}.</p></li>
<li><h3>Honest pricing</h3><p>The price is confirmed before work begins.</p></li>
<li><h3>Careful work</h3><p>Non-destructive methods first, always.</p></li>
</ul>
</div>
<aside class="panel"><img src="/assets/img/hero.svg" alt="Lockman superhero artwork" width="400" height="400" loading="lazy"></aside>
</div></section>
{cta_block(cfg)}"""
    return page(cfg, path="/about/", title="About Us", description="Meet Lockman ASAP Locksmith, a licensed mobile locksmith in San Francisco.",
                body=body, crumbs=[("/", "Home"), ("/about/", "About")])


def contact(cfg):
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">Contact Lockman ASAP Locksmith</h1>
<p class="lead">The fastest way to reach us is a phone call or WhatsApp message.</p></div></section>
<section class="section"><div class="wrap grid-3">
<div class="card"><h2>Phone</h2><p><a class="btn btn-call" href="{tel(cfg)}">{e(clean(cfg['phone_display']))}</a></p></div>
<div class="card"><h2>WhatsApp</h2><p><a class="btn btn-wa" href="{whatsapp_url(cfg)}" rel="noopener">Message us</a></p><p>Send a photo of the lock and we'll tell you what we need.</p></div>
<div class="card"><h2>Hours &amp; email</h2><p>{e(clean(cfg['hours_text']))}</p><p><a href="mailto:{e(clean(cfg['email']))}">{e(clean(cfg['email']))}</a></p></div>
</div></section>"""
    return page(cfg, path="/contact/", title="Contact Us", description=f"Call {clean(cfg['phone_display'])} or WhatsApp Lockman ASAP Locksmith in San Francisco.",
                body=body, crumbs=[("/", "Home"), ("/contact/", "Contact")])


def articles_index(cfg, articles):
    cards = "".join(article_card(a) for a in articles) or "<p>New articles are on the way.</p>"
    body = f"""<section class="section page-head halftone"><div class="wrap"><h1 class="comic">Locksmith Tips &amp; Articles</h1>
<p class="lead">Practical advice on locks, keys and home security in San Francisco.</p></div></section>
<section class="section"><div class="wrap grid-3">{cards}</div></section>"""
    return page(cfg, path="/articles/", title="Locksmith Tips & Articles", description="Original locksmith advice for San Francisco homes and businesses.",
                body=body, crumbs=[("/", "Home"), ("/articles/", "Articles")])


def render_sections(sections):
    out = []
    for sec in sections:
        out.append(f"<h2>{e(sec['heading'])}</h2>")
        for p in sec.get("paragraphs", []):
            out.append(f"<p>{e(p)}</p>")
        if sec.get("bullets"):
            out.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in sec["bullets"]) + "</ul>")
    return "\n".join(out)


def article_page(cfg, a, articles):
    published = dt.datetime.fromisoformat(a["published_at"])
    url = f"{cfg['site_url']}/articles/{a['slug']}/"
    faq_html, faq_schema = "", None
    if a.get("faq"):
        faq_html = "<h2>Frequently asked questions</h2>" + "".join(
            f"<h3>{e(q['question'])}</h3><p>{e(q['answer'])}</p>" for q in a["faq"])
        faq_schema = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q["question"], "acceptedAnswer": {"@type": "Answer", "text": q["answer"]}} for q in a["faq"]],
        }
    schema = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": a["title"], "description": a["description"],
        "datePublished": published.isoformat(), "dateModified": published.isoformat(),
        "mainEntityOfPage": url,
        "author": {"@type": "Organization", "name": cfg["business_name"], "url": cfg["site_url"] + "/"},
        "publisher": {"@id": cfg["site_url"] + "/#business"},
        "image": cfg["site_url"] + "/assets/img/og-image.png",
    }
    related = [x for x in articles if x["slug"] != a["slug"]][:3]
    related_html = f"""<section class="section section-alt"><div class="wrap"><h2 class="comic">More articles</h2>
<div class="grid-3">{''.join(article_card(r) for r in related)}</div></div></section>""" if related else ""
    disclosure = cfg["articles"].get("ai_disclosure")
    body = f"""<article class="section">
<div class="wrap prose">
<p class="card-date"><time datetime="{published.date().isoformat()}">{published.strftime('%B %-d, %Y')}</time></p>
<h1 class="comic">{e(a['title'])}</h1>
<p class="lead">{e(a['intro'])}</p>
{render_sections(a['sections'])}
{faq_html}
<aside class="panel article-cta"><p><strong>Need a locksmith in San Francisco now?</strong></p>
<div class="btn-row"><a class="btn btn-call" href="{tel(cfg)}">Call {e(clean(cfg['phone_display']))}</a>
<a class="btn btn-wa" href="{whatsapp_url(cfg)}" rel="noopener">WhatsApp</a></div></aside>
{f'<p class="disclosure">{e(disclosure)}</p>' if disclosure else ''}
</div>
</article>
{related_html}"""
    return page(cfg, path=f"/articles/{a['slug']}/", title=a["title"], description=a["description"], body=body, og_type="article",
                schemas=[s for s in (schema, faq_schema) if s],
                crumbs=[("/", "Home"), ("/articles/", "Articles"), (f"/articles/{a['slug']}/", a["title"])])


def legal_page(cfg, path, title, description, inner):
    body = f"""<section class="section"><div class="wrap prose"><h1 class="comic">{e(title)}</h1>
<p class="card-date">Last updated: {LEGAL_UPDATED}</p>{inner}</div></section>"""
    return page(cfg, path=path, title=title, description=description, body=body,
                crumbs=[("/", "Home"), (path, title)])


LEGAL_UPDATED = "October 27, 2026"


def privacy(cfg):
    name, email = e(cfg["business_name"]), e(clean(cfg["email"]))
    inner = f"""
<p>This policy explains what information {name} ("we") collects through this website, how we use it, and your choices. It is written to meet the California Online Privacy Protection Act (CalOPPA).</p>
<h2>Information we collect</h2>
<ul>
<li><strong>Analytics data, only if you accept cookies.</strong> Google Analytics collects pages visited, time on page, approximate location (city level), device and browser type, and how you arrived at the site. It uses cookies and a randomly generated identifier.</li>
<li><strong>Information you send us.</strong> If you call, text, email or message us on WhatsApp, we receive your phone number or email and whatever you choose to tell us, such as your address for a service visit.</li>
</ul>
<p>This website has no forms and no user accounts. We do not collect payment information on this website.</p>
<h2>How we use information</h2>
<ul><li>To respond to you and provide locksmith service.</li><li>To understand which pages are useful and improve the site.</li><li>To comply with California locksmith law, which requires us to keep certain job records, including proof of identity and residence for lockout work.</li></ul>
<h2>Who we share it with</h2>
<p>We do not sell or share personal information for cross-context behavioral advertising. We use these service providers:</p>
<ul><li><strong>Google LLC</strong> (Google Analytics) for website statistics, only after you accept cookies.</li>
<li><strong>WhatsApp / Meta</strong>, if you choose to message us on WhatsApp. Their own privacy policy applies to that conversation.</li>
<li><strong>Our website host</strong>, which processes standard server logs such as IP address to deliver the site securely.</li></ul>
<p>We may disclose information when required by law.</p>
<h2>Your choices</h2>
<ul><li><strong>Cookies:</strong> Analytics stays off unless you click Accept. You can change your choice at any time with the "Cookie settings" link at the bottom of every page.</li>
<li><strong>Global Privacy Control:</strong> If your browser sends a Global Privacy Control signal, we treat it as a refusal and do not load Google Analytics.</li>
<li><strong>Do Not Track:</strong> We also treat a browser "Do Not Track" signal as a refusal and do not load Google Analytics.</li>
<li><strong>Review, correct or delete:</strong> Email us at <a href="mailto:{email}">{email}</a> to ask what information we hold about you, or to correct or delete it, subject to records the law requires us to keep.</li></ul>
<h2>Children</h2>
<p>This site is not directed at children under 13, and we do not knowingly collect their information.</p>
<h2>Security</h2>
<p>The site is served over HTTPS. We keep job records only as long as needed for business and legal purposes.</p>
<h2>Changes</h2>
<p>If we change this policy we will update the date at the top of this page.</p>
<h2>Contact</h2>
<p>{name}, {e(cfg['city'])}, {e(cfg['region'])}. Email: <a href="mailto:{email}">{email}</a>. Phone: <a href="{tel(cfg)}">{e(clean(cfg['phone_display']))}</a>.</p>"""
    return legal_page(cfg, "/privacy/", "Privacy Policy", f"How {cfg['business_name']} handles your information.", inner)


def terms(cfg):
    name = e(cfg["business_name"])
    inner = f"""
<h2>About this website</h2>
<p>This website is operated by {name}, a California licensed locksmith (License {e(clean(cfg['license_number']))}). By using it you agree to these terms.</p>
<h2>Information, not professional advice</h2>
<p>Articles on this site are general information. Every lock and door is different. For anything involving your security, contact a licensed locksmith. Some articles are written with AI assistance and checked for originality; if you see an error, please tell us.</p>
<h2>Service and pricing</h2>
<p>Prices are quoted by phone or message and confirmed on site before work begins. For lockouts we require proof of identity and of your right to access the property, as California law requires. We may refuse a job if ownership or authorization cannot be confirmed.</p>
<h2>Intellectual property</h2>
<p>All text, comic artwork, characters and logos on this site are owned by {name} and may not be copied or reused without written permission.</p>
<h2>Third-party links</h2>
<p>Links to other websites, such as WhatsApp or government license lookups, are provided for convenience. We are not responsible for their content.</p>
<h2>Limitation of liability</h2>
<p>The website is provided "as is." To the extent allowed by law, {name} is not liable for damages arising from use of the website content. This does not limit any rights you have under California law for services we perform.</p>
<h2>Governing law</h2>
<p>These terms are governed by the laws of the State of California.</p>
<h2>Licensing authority</h2>
<p>Locksmiths in California are licensed by the Bureau of Security and Investigative Services (BSIS), Department of Consumer Affairs. You can verify a license at <a href="https://search.dca.ca.gov/" rel="noopener">search.dca.ca.gov</a>.</p>"""
    return legal_page(cfg, "/terms/", "Terms of Service", f"Terms for using the {cfg['business_name']} website.", inner)


def accessibility(cfg):
    inner = f"""
<p>{e(cfg['business_name'])} wants everyone to be able to use this website, including people who use screen readers, keyboard navigation, zoom or voice control.</p>
<h2>Our standard</h2>
<p>We aim to meet the Web Content Accessibility Guidelines (WCAG) 2.1, level AA. The site is built with semantic headings, text descriptions for images, visible keyboard focus, sufficient color contrast and layouts that work at 200% zoom and on small screens.</p>
<h2>Need help or found a problem?</h2>
<p>If any part of this site is hard to use, call us at <a href="{tel(cfg)}">{e(clean(cfg['phone_display']))}</a> or email <a href="mailto:{e(clean(cfg['email']))}">{e(clean(cfg['email']))}</a>. We will help you directly and fix the problem.</p>"""
    return legal_page(cfg, "/accessibility/", "Accessibility Statement", "Our commitment to an accessible website.", inner)


def not_found(cfg):
    body = f"""<section class="section"><div class="wrap center"><p class="burst big" aria-hidden="true">OOPS!</p>
<h1 class="comic">This page is locked</h1><p>We couldn't find that page. Try the <a href="/">home page</a> or call us at <a href="{tel(cfg)}">{e(clean(cfg['phone_display']))}</a>.</p></div></section>"""
    return page(cfg, path="/404.html", title="Page not found", description="Page not found.", body=body).replace(
        '<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="description"', 1)


# ---------------------------------------------------------------- feeds

def sitemap(cfg, urls):
    rows = "".join(f"<url><loc>{e(cfg['site_url'] + p)}</loc><lastmod>{d}</lastmod></url>\n" for p, d in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


def robots(cfg):
    return f"User-agent: *\nAllow: /\n\nSitemap: {cfg['site_url']}/sitemap.xml\n"


def rss(cfg, articles):
    items = "".join(
        f"""<item><title>{e(a['title'])}</title><link>{cfg['site_url']}/articles/{a['slug']}/</link>
<guid>{cfg['site_url']}/articles/{a['slug']}/</guid><pubDate>{dt.datetime.fromisoformat(a['published_at']).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>
<description>{e(a['description'])}</description></item>\n""" for a in articles[:30])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{e(cfg['business_name'])} Articles</title><link>{cfg['site_url']}/articles/</link>
<description>Locksmith tips for San Francisco</description>
{items}</channel></rss>
"""


# ---------------------------------------------------------------- main

def write(rel, content):
    base = load_config().get("base_path", "").rstrip("/")
    if base and rel.endswith((".html", "/")):
        content = re.sub(r'(href|src)="/(?!/)', rf'\1="{base}/', content)
    out = DIST / rel.lstrip("/")
    if rel.endswith("/"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")


def build():
    cfg = load_config()
    articles = load_articles()
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "assets", DIST / "assets")
    today = dt.date.today().isoformat()
    urls = []

    def add(path, html_text, lastmod=today, index=True):
        write(path, html_text)
        if index:
            urls.append((path, lastmod))

    newest = articles[0]["published_at"][:10] if articles else today
    add("/", home(cfg, articles), newest)
    add("/services/", services_index(cfg))
    for s in SERVICES:
        add(f"/services/{s['slug']}/", service_page(cfg, s))
    add("/service-area/", service_area(cfg))
    add("/about/", about(cfg))
    add("/contact/", contact(cfg))
    add("/articles/", articles_index(cfg, articles), newest)
    for a in articles:
        add(f"/articles/{a['slug']}/", article_page(cfg, a, articles), a["published_at"][:10])
    add("/privacy/", privacy(cfg))
    add("/terms/", terms(cfg))
    add("/accessibility/", accessibility(cfg))
    write("/404.html", not_found(cfg))
    write("/sitemap.xml", sitemap(cfg, urls))
    write("/robots.txt", robots(cfg))
    write("/articles/feed.xml", rss(cfg, articles))
    domain = cfg["site_url"].split("://", 1)[1].strip("/")
    write("/CNAME", domain + "\n")
    print(f"Built {len(urls)} pages ({len(articles)} articles) into {DIST}")


if __name__ == "__main__":
    build()
