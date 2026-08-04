# nichebot — demand-signal miner

Finds micro-SaaS opportunities by mining **complaints from people who already
pay for software**, then ranking them by frequency × willingness-to-pay ×
buildability.

## Why these two sources only

- **Chrome Web Store 1-2★ reviews on 5k+ user extensions** — proven demand
  (people installed it) + failing incumbent (they hate it). Best signal on the
  internet for this purpose.
- **Reddit buyer-intent searches in vertical subreddits** — r/realtors,
  r/dentistry, r/HVAC etc. Maker subs are saturated; verticals are not.

Adding more sources does not improve signal, it just adds noise and ban risk.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests playwright
playwright install chromium

export REDDIT_CLIENT_ID=...        # reddit.com/prefs/apps -> type "script"
export REDDIT_CLIENT_SECRET=...
export REDDIT_USER_AGENT="nichebot/0.1 by u/yourhandle"
export GROQ_API_KEYS=key1,key2,... # free keys: console.groq.com (rotates on rate limit)
```

## Run

```bash
python collect_reddit.py     # ~30-60 min
python collect_chrome.py     # ~2-4 hrs, run headless on a VPS
python score.py              # classify + rank
python score.py --report     # re-print ranking anytime
```

Data lands in `signals.db` (SQLite). Nothing is overwritten — safe to re-run
daily; duplicates are ignored by content hash.

## Daily loop on a VPS

```
0 2 * * *  cd /opt/nichebot && ./.venv/bin/python collect_reddit.py >> log 2>&1
0 4 * * *  cd /opt/nichebot && ./.venv/bin/python collect_chrome.py >> log 2>&1
0 9 * * *  cd /opt/nichebot && ./.venv/bin/python score.py >> log 2>&1
```

Hetzner CX22 / DigitalOcean $6 droplet is plenty.

## Reading the output

Ignore the top line if `freq` is only 2-3 — that's coincidence, not a market.
What you want: **freq ≥ 8, avg_wtp ≥ 2.0, avg_build ≥ 2.0, and 2+ distinct
personas saying it.** That combination is rare and it is the whole point of
running this.

## Rules that keep you unbanned

- Reddit: official OAuth API, 60 req/min. Never scrape old.reddit HTML.
- Chrome Store: 2-4s delay between pages, headless is fine, don't parallelise.
- If you add G2/Capterra later you WILL need residential proxies. Skip it.

## The trap

Collecting data is the easy, fun part. It is not the business. Cap the
collection phase — 4 days is enough — then spend the remaining time putting a
landing page + a real Stripe payment link in front of the top 3 clusters.
People paying before the product exists is the only validation that counts.
