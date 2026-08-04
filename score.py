"""
Scoring layer — THIS is where raw noise becomes a decision.
Uses the Anthropic API to turn each complaint into structured fields,
then clusters by problem and ranks.

env: ANTHROPIC_API_KEY
pip install anthropic
"""
import os, json, sys, time
import db

MODEL = os.getenv("NICHEBOT_MODEL", "claude-sonnet-4-6")
BATCH = 12

SYSTEM = """You classify user complaints into micro-SaaS opportunity signals.
For EACH numbered item, return one JSON object. Be strict and skeptical —
most complaints are NOT business opportunities. Fields:

problem: one line, the underlying job-to-be-done that is failing. Neutral wording.
persona: who is speaking (their profession/role). "unknown" if unclear.
wtp: 0-3 willingness to pay. 0=venting, 1=annoyed, 2=asking for a tool,
     3=explicitly says they'd pay / already pays / mentions a price.
has_price: any dollar/rupee amount mentioned, else null.
existing_solution: named competing product if mentioned, else null.
buildable: 0-3, can ONE developer ship a v1 in 2 weeks with a web app or
     browser extension? 0=needs hardware/enterprise sales/huge data moat,
     3=trivially yes.
cluster_key: lowercase-hyphenated slug of the problem, GENERIC enough that
     two people describing the same pain get the SAME key.
     e.g. "invoice-reminders-for-freelancers"

Return ONLY a JSON array. No prose, no markdown fences."""


def client():
    from anthropic import Anthropic
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")
    return Anthropic()


def classify(cl, rows):
    items = "\n\n".join(
        f"[{i}] source={r['source']} ctx={r['subsource']}\n{r['text'][:1500]}"
        for i, r in enumerate(rows)
    )
    msg = cl.messages.create(
        model=MODEL, max_tokens=4000, system=SYSTEM,
        messages=[{"role": "user", "content": items}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def run():
    db.init()
    cl = client()
    total = 0
    while True:
        rows = db.unscored(BATCH)
        if not rows:
            break
        try:
            out = classify(cl, rows)
        except Exception as e:
            print(f"[score] batch failed: {e}", flush=True)
            time.sleep(5)
            continue
        for r, d in zip(rows, out):
            db.save_classification(r["id"], d)
        total += len(rows)
        print(f"[score] {total} scored", flush=True)
    return total


def report(top=25):
    """Rank clusters. frequency x demand, penalised by weak buildability."""
    with db.conn() as c:
        rows = c.execute("""
            SELECT cluster_key,
                   COUNT(*)                       AS freq,
                   COUNT(DISTINCT k.persona)      AS personas,
                   AVG(k.wtp)                     AS avg_wtp,
                   AVG(k.buildable)               AS avg_build,
                   MAX(k.problem)                 AS sample_problem,
                   GROUP_CONCAT(DISTINCT k.persona) AS who
            FROM classified k
            WHERE cluster_key IS NOT NULL
            GROUP BY cluster_key
            HAVING freq >= 2
        """).fetchall()

    scored = []
    for r in rows:
        s = r["freq"] * (1 + r["avg_wtp"]) * (r["avg_build"] / 3 + 0.2)
        scored.append((round(s, 1), dict(r)))
    scored.sort(reverse=True, key=lambda x: x[0])

    print(f"\n{'SCORE':>7}  {'FREQ':>4}  {'WTP':>4}  {'BUILD':>5}  PROBLEM")
    print("-" * 100)
    for s, r in scored[:top]:
        print(f"{s:>7}  {r['freq']:>4}  {r['avg_wtp']:>4.1f}  "
              f"{r['avg_build']:>5.1f}  {r['sample_problem'][:70]}")
        print(f"{'':>7}  who: {(r['who'] or '')[:90]}")
    return scored


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        run()
        report()
