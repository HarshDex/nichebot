"""SQLite store for raw signals + scored output."""
import sqlite3, os, json, hashlib
from contextlib import contextmanager

DB_PATH = os.getenv("NICHEBOT_DB", os.path.join(os.path.dirname(__file__), "signals.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            TEXT PRIMARY KEY,      -- sha1 of source+url+text
    source        TEXT NOT NULL,         -- 'reddit' | 'chrome_store'
    subsource     TEXT,                  -- subreddit name / extension name
    url           TEXT,
    author        TEXT,
    title         TEXT,
    text          TEXT NOT NULL,
    rating        INTEGER,               -- 1-5 for store reviews, NULL for reddit
    score         INTEGER,               -- reddit upvotes
    created_utc   INTEGER,
    fetched_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);

CREATE TABLE IF NOT EXISTS classified (
    signal_id     TEXT PRIMARY KEY REFERENCES signals(id),
    problem       TEXT,                  -- one-line problem statement
    persona       TEXT,                  -- who is complaining
    wtp           INTEGER,               -- 0-3 willingness-to-pay signal
    has_price     TEXT,                  -- extracted price mention if any
    existing_sol  TEXT,
    buildable     INTEGER,               -- 0-3 solo-buildable in 2 weeks?
    cluster_key   TEXT,                  -- normalized problem slug for grouping
    raw           TEXT,
    scored_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_classified_cluster ON classified(cluster_key);
"""


def sig_id(source: str, url: str, text: str) -> str:
    return hashlib.sha1(f"{source}|{url}|{text[:300]}".encode()).hexdigest()


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def insert_signal(**kw):
    """Idempotent insert. Returns True if new."""
    kw["id"] = sig_id(kw["source"], kw.get("url") or "", kw["text"])
    cols = ",".join(kw.keys())
    ph = ",".join("?" * len(kw))
    with conn() as c:
        cur = c.execute(
            f"INSERT OR IGNORE INTO signals ({cols}) VALUES ({ph})", list(kw.values())
        )
        return cur.rowcount > 0


def unscored(limit=200):
    with conn() as c:
        return c.execute(
            """SELECT s.* FROM signals s
               LEFT JOIN classified k ON k.signal_id = s.id
               WHERE k.signal_id IS NULL
               LIMIT ?""",
            (limit,),
        ).fetchall()


def save_classification(signal_id, d):
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO classified
               (signal_id, problem, persona, wtp, has_price, existing_sol,
                buildable, cluster_key, raw)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                signal_id,
                d.get("problem"),
                d.get("persona"),
                int(d.get("wtp") or 0),
                d.get("has_price"),
                d.get("existing_solution"),
                int(d.get("buildable") or 0),
                d.get("cluster_key"),
                json.dumps(d, ensure_ascii=False),
            ),
        )


def stats():
    with conn() as c:
        raw = c.execute("SELECT source, COUNT(*) n FROM signals GROUP BY source").fetchall()
        done = c.execute("SELECT COUNT(*) n FROM classified").fetchone()["n"]
        return {r["source"]: r["n"] for r in raw}, done
