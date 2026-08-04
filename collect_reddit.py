"""
Reddit collector — uses the OFFICIAL OAuth API (script app), not scraping.
Create an app at https://www.reddit.com/prefs/apps -> type 'script'.

env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

Strategy: run buyer-intent search queries inside vertical subreddits.
The queries matter more than the volume. These are the phrases people
actually type right before they'd pay for something.
"""
import os, time, requests, sys
import db

UA = os.getenv("REDDIT_USER_AGENT", "nichebot/0.1 by u/yourname")
CID = os.getenv("REDDIT_CLIENT_ID")
CSEC = os.getenv("REDDIT_CLIENT_SECRET")

# Buyer-intent phrases. Add/remove freely — this is your lever.
QUERIES = [
    '"is there a tool"',
    '"is there an app"',
    '"I would pay for"',
    '"I\'d pay for"',
    '"does anyone know a tool"',
    '"still doing this manually"',
    '"spreadsheet hell"',
    '"wish there was"',
    '"any alternative to"',
    '"too expensive" software',
]

# Mix of maker subs + VERTICAL subs (verticals are where the real money is —
# makers complain about maker tools, which is a saturated market).
SUBS = [
    # maker / general
    "SaaS", "microsaas", "smallbusiness", "Entrepreneur", "EntrepreneurRideAlong",
    "freelance", "agency",
    # verticals — these are the goldmine
    "realtors", "RealEstate", "photography", "videography", "personaltraining",
    "dentistry", "physicaltherapy", "Accounting", "bookkeeping", "lawfirm",
    "Construction", "HVAC", "Plumbing", "restaurateur", "salon", "Etsy",
    "shopify", "FulfillmentByAmazon", "PropertyManagement", "recruiting",
    "nonprofit", "Teachers", "gunsmithing", "veterinary", "Chiropractic",
]

TOKEN = {"val": None, "exp": 0}


def token():
    if TOKEN["val"] and time.time() < TOKEN["exp"] - 60:
        return TOKEN["val"]
    if not (CID and CSEC):
        sys.exit("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(CID, CSEC),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    TOKEN["val"] = j["access_token"]
    TOKEN["exp"] = time.time() + j.get("expires_in", 3600)
    return TOKEN["val"]


def search(sub, q, limit=100, after=None):
    r = requests.get(
        f"https://oauth.reddit.com/r/{sub}/search",
        params={
            "q": q, "restrict_sr": 1, "sort": "new", "t": "year",
            "limit": limit, "after": after,
        },
        headers={"Authorization": f"bearer {token()}", "User-Agent": UA},
        timeout=25,
    )
    if r.status_code == 429:
        time.sleep(30)
        return None, None
    if r.status_code in (403, 404):   # private/banned sub
        return [], None
    r.raise_for_status()
    d = r.json()["data"]
    return d["children"], d.get("after")


def run(pages=2):
    db.init()
    new = 0
    for sub in SUBS:
        for q in QUERIES:
            after = None
            for _ in range(pages):
                items, after = search(sub, q, after=after)
                if items is None:
                    continue
                for it in items:
                    p = it["data"]
                    body = (p.get("selftext") or "").strip()
                    text = f"{p.get('title','')}\n\n{body}".strip()
                    if len(text) < 60:
                        continue
                    if db.insert_signal(
                        source="reddit",
                        subsource=sub,
                        url="https://reddit.com" + p.get("permalink", ""),
                        author=p.get("author"),
                        title=p.get("title"),
                        text=text[:6000],
                        score=p.get("score"),
                        created_utc=int(p.get("created_utc") or 0),
                    ):
                        new += 1
                if not after:
                    break
                time.sleep(1.2)   # be polite; 60 req/min limit
            time.sleep(1.2)
        print(f"[reddit] {sub} done — {new} new so far", flush=True)
    return new


if __name__ == "__main__":
    print(f"[reddit] inserted {run()} new signals")
