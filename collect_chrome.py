"""
Chrome Web Store collector — the highest-signal source in this whole pipeline.

Logic: find extensions with big user counts, then read their 1-2 star reviews.
A popular extension with angry reviews = proven demand + failing incumbent.
That is the single best micro-SaaS setup there is.

pip install playwright && playwright install chromium
"""
import time, re, sys, random
import db

SEED_QUERIES = [
    # broad categories where people pay
    "invoice", "screenshot", "email tracker", "seo", "scraper", "crm",
    "productivity timer", "tab manager", "grammar", "price tracker",
    "linkedin", "youtube downloader", "pdf", "translate", "ad blocker",
    "shopify", "amazon seller", "real estate", "calendar", "meeting notes",
    "form filler", "password", "bookmark", "dark mode", "accessibility",
]

BASE = "https://chromewebstore.google.com"
MIN_USERS = 5000        # ignore tiny extensions — no proven demand
MAX_PER_QUERY = 12


def parse_users(s):
    if not s:
        return 0
    s = s.replace(",", "").lower()
    m = re.search(r"([\d.]+)\s*([km]?)", s)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * {"k": 1_000, "m": 1_000_000, "": 1}[m.group(2)])


def run(headless=True):
    from playwright.sync_api import sync_playwright

    db.init()
    new = 0
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=headless)
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.new_page()

        for q in SEED_QUERIES:
            try:
                page.goto(f"{BASE}/search/{q}", timeout=45000)
                page.wait_for_timeout(2500)
                links = page.eval_on_selector_all(
                    'a[href*="/detail/"]',
                    "els => [...new Set(els.map(e => e.href))]",
                )[:MAX_PER_QUERY]
            except Exception as e:
                print(f"[chrome] search fail {q}: {e}", flush=True)
                continue

            for url in links:
                try:
                    new += scrape_detail(page, url)
                except Exception as e:
                    print(f"[chrome] detail fail {url}: {e}", flush=True)
                time.sleep(random.uniform(2, 4))
            print(f"[chrome] '{q}' done — {new} new so far", flush=True)
        br.close()
    return new


def scrape_detail(page, url):
    page.goto(url, timeout=45000)
    page.wait_for_timeout(2000)
    body = page.inner_text("body")

    name = (page.title() or "").split(" - ")[0].strip()
    m = re.search(r"([\d.,]+[KM]?)\s*users", body)
    users = parse_users(m.group(1)) if m else 0
    if users < MIN_USERS:
        return 0

    # open reviews panel
    for sel in ['text="See all reviews"', 'text="All reviews"', 'button:has-text("reviews")']:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_timeout(2500)
            break
        except Exception:
            continue

    # scroll the review list to load more
    for _ in range(6):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(900)

    added = 0
    blocks = page.query_selector_all('[role="article"], .ba-Ea-Q, section')
    for b in blocks:
        try:
            txt = (b.inner_text() or "").strip()
        except Exception:
            continue
        if not (60 < len(txt) < 4000):
            continue
        rm = re.search(r"(\d)\s*(?:out of 5|star)", txt, re.I)
        rating = int(rm.group(1)) if rm else None
        if rating is not None and rating > 2:
            continue      # ONLY 1-2 star reviews — that's where the gap is
        if db.insert_signal(
            source="chrome_store", subsource=f"{name} ({users} users)",
            url=url, title=name, text=txt[:4000], rating=rating,
        ):
            added += 1
    return added


if __name__ == "__main__":
    print(f"[chrome] inserted {run(headless='--show' not in sys.argv)} new signals")
