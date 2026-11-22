#!/usr/bin/env python3
"""analyze.py - Inca challenge #1222 rebuild: verify day-1 numbers for the charged wallet.

Reads raw/fills.jsonl (decoded CTF-Exchange V1 OrderFilled) + raw/token_map.json,
recomputes the day-1 (2026-10-23) market totals and the charged wallet's figures,
and writes csv/ + summary.json. Only the wallet named in the charging documents is
reported at wallet level; everything else is a market level aggregate.

Fill row schema (from polymarket_fetch.py):
  k=OF, b=block, tx, li=log index, oh=orderHash,
  mk=maker addr, tk=taker addr,
  ma=makerAssetId (0 == USDC collateral), ta=takerAssetId,
  mi=makerAmountFilled (9 decimals: USDC 1e6 / shares 1e6), ti=takerAmountFilled,
  em=emitter, f=fee
Direction: the side that gives USDC (assetId 0, amount usdc) BUYS the token side.
"""
import json, os, csv, collections, sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
CSV = os.path.join(BASE, "csv")
os.makedirs(CSV, exist_ok=True)

# day-1 verification targets (writeup 2026-10-23)
PRIOR = {
    "totals": {  # market_slug -> (fills, txs, wallets, usd_total, usd_cftc_window)
        "maduro-out-in-2025-411": (65_020, None, None, 1_528_577, 391_745),
    },
    "wallets": {
        "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9": {"net_yes": 65_020},
    },
    "cftc": {"yes_shares": 436_000, "usd": 409_881, "bets": 13, "markets": 4},
}
# block anchors from --blocks run
BLOCK_ANCHORS = [
    (80793979, 1766707201),  # 2025-12-26 00:00:01Z
    (80923579, 1766966401),  # 2025-12-29 00:00:01Z
    (80966779, 1767052801),  # 2025-12-30 00:00:01Z (CFTC window start)
    (81139571, 1767398401),  # 2026-01-03 00:00:01Z
    (81182771, 1767484801),  # 2026-01-04 00:00:01Z
    (81312371, 1767744001),  # 2026-01-07 00:00:01Z (scan end)
]
CFTC_B = [80966779, 81182771]  # Dec30 00:00 -> Jan4 00:00 (covers the CFTC's Dec30-Jan2 buys)

def ts_of(block, start_i=0):
    """linear interpolation between anchors; derived ts, ±1 min drift tolerated."""
    for i in range(start_i if start_i else 0, len(BLOCK_ANCHORS) - 1):
        (b0, t0), (b1, t1) = BLOCK_ANCHORS[i], BLOCK_ANCHORS[i + 1]
        if b0 <= block <= b1:
            return t0 + (t1 - t0) * (block - b0) // (b1 - b0)
    if block > BLOCK_ANCHORS[-1][0]:
        (b0, t0), (b1, t1) = BLOCK_ANCHORS[-2], BLOCK_ANCHORS[-1]
        return t1 + (t1 - t0) // (b1 - b0) * (block - b1)
    (b0, t0), (b1, t1) = BLOCK_ANCHORS[0], BLOCK_ANCHORS[1]
    return t0 - (t1 - t0) // (b1 - b0) * (b0 - block)

def main():
    if not os.path.exists(os.path.join(RAW, "fills.jsonl")):
        sys.exit("missing raw/fills.jsonl: run polymarket_fetch.py --scan 80793979 81312371 first")
    tmap = json.load(open(os.path.join(RAW, "token_map.json")))
    per_fill = []           # parsed buys/sells on our 18 markets
    skipped = 0
    with open(os.path.join(RAW, "fills.jsonl")) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                skipped += 1
                continue
            ma, ta, mi, ti = r["ma"], r["ta"], r["mi"], r["ti"]
            mtk, tkr = r["mk"], r["tk"]
            tok = None
            usdc = None
            if str(ta) in tmap:
                # taker GIVES the outcome token (maker receives it) -> MAKER buys
                tok = tmap[str(ta)]
                side, buyer, seller, shares, usdc = "buy", mtk.lower(), tkr.lower(), ti, mi
            elif str(ma) in tmap:
                # maker GIVES the outcome token (taker receives it) -> TAKER buys
                tok = tmap[str(ma)]
                side, buyer, seller, shares, usdc = "buy", tkr.lower(), mtk.lower(), mi, ti
            elif str(ma) == "0" and str(ta) == "0":
                skipped += 1
                continue
            else:
                skipped += 1
                continue
            if side == "buy" and usdc == 0:
                # zero-usdc leg (split/merge artefacts) - keep for share flow but flag
                pass
            per_fill.append({
                "b": r["b"], "tx": r["tx"], "li": r["li"],
                "market": tok["market_slug"], "outcome": tok["outcome"],
                "buyer": buyer, "seller": seller,
                "shares": shares, "usdc": usdc, "ts": ts_of(r["b"]),
            })

    # ---- 1. per-market totals over the full scan window
    mk_stats = collections.defaultdict(lambda: {"fills": 0, "txs": set(), "wallets": set(), "usd": 0, "shares_yes": 0})
    for f in per_fill:
        s = mk_stats[f["market"]]
        s["fills"] += 1
        s["txs"].add(f["tx"])
        s["wallets"].add(f["buyer"])
        s["wallets"].add(f["seller"])
        s["usd"] += f["usdc"]
        if f["outcome"] == "Yes":
            s["shares_yes"] += f["shares"] / 1e6
    rows = []
    for slug, s in sorted(mk_stats.items(), key=lambda kv: -kv[1]["usd"]):
        rows.append({"market": slug, "fills": s["fills"], "txs": len(s["txs"]),
                     "wallets": len(s["wallets"]), "usd_all": s["usd"] / 1e6,
                     "yes_bought_shares": s["shares_yes"]})
    with open(os.path.join(CSV, "counts.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ---- 2. CFTC window aggregates (Dec30 00:00Z -> block 81182771)
    cftc = collections.defaultdict(lambda: {"buy_yes_shares": 0, "buy_usd": 0, "sells_yes": 0, "fills": 0, "buyers": set()})
    for f in per_fill:
        if not (CFTC_B[0] <= f["b"] <= CFTC_B[1] and f["outcome"] == "Yes"):
            continue
        s = cftc[f["market"]]
        s["fills"] += 1
        s["buy_yes_shares"] += f["shares"] / 1e6
        s["buy_usd"] += f["usdc"] / 1e6
        s["buyers"].add(f["buyer"])
    cf_rows = [{"market": k, **{kk: (len(v["buyers"]) if kk == "buyers" else round(v[kk], 2)) for kk in
                 ("buy_yes_shares", "buy_usd", "sells_yes", "fills", "buyers")}} for k, v in cftc.items()]
    with open(os.path.join(CSV, "cftc_window.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["market", "buy_yes_shares", "buy_usd", "sells_yes", "fills", "buyers"])
        w.writeheader(); w.writerows(cf_rows)
    tot_yes = sum(r["buy_yes_shares"] for r in cf_rows)
    tot_usd = sum(r["buy_usd"] for r in cf_rows)
    tot_wal = set()
    for v in cftc.values():
        tot_wal |= v["buyers"]

    # ---- 3. candidate wallets, in the CFTC window (and full-window for context)
    cand = PRIOR["wallets"]
    w_stats = {}
    w_per_market = []
    for w in cand:
        for label, lo, hi in (("cftc", CFTC_B[0], CFTC_B[1]),
                              ("jan3", CFTC_B[0], 81139571),
                              ("full", None, None)):
            me = [f for f in per_fill if (f["buyer"] == w or f["seller"] == w)
                  and (lo is None or lo <= f["b"] <= hi)]
            yes_b = sum(f["shares"] / 1e6 for f in me if f["buyer"] == w and f["outcome"] == "Yes")
            yes_s = sum(f["shares"] / 1e6 for f in me if f["seller"] == w and f["outcome"] == "Yes")
            usd_b = sum(f["usdc"] / 1e6 for f in me if f["buyer"] == w)
            usd_r = sum(f["usdc"] / 1e6 for f in me if f["seller"] == w)
            mkts = sorted({f["market"] for f in me})
            wb = min([f["b"] for f in me], default=None)
            w_stats.setdefault(w, {})[label] = {
                "fills": len(me), "yes_bought": yes_b, "yes_sold": yes_s,
                "net_yes": yes_b - yes_s, "usd_spent": usd_b, "usd_received": usd_r,
                "markets": mkts, "first_block": wb}
            if label == "cftc":
                for slug in sorted({f["market"] for f in me}):
                    ms = [f for f in me if f["market"] == slug]
                    w_per_market.append({
                        "wallet": w, "market": slug,
                        "yes_bought": sum(f["shares"] / 1e6 for f in ms if f["buyer"] == w and f["outcome"] == "Yes"),
                        "yes_sold": sum(f["shares"] / 1e6 for f in ms if f["seller"] == w and f["outcome"] == "Yes"),
                        "usd_spent": sum(f["usdc"] / 1e6 for f in ms if f["buyer"] == w),
                        "fills": len(ms)})
        # single-minute batch test: fill timestamps over its CFTC window buys
        batch = [f for f in per_fill if f["buyer"] == w and CFTC_B[0] <= f["b"] <= CFTC_B[1]
                 and f["outcome"] == "Yes"]
        if batch:
            blocks = sorted(f["b"] for f in batch)
            span_blk = blocks[-1] - blocks[0]
            w_stats[w]["cftc_buy_block_span"] = span_blk
            w_stats[w]["cftc_buys_spread_seconds_derived"] = span_blk * 2.1
    with open(os.path.join(CSV, "candidates.csv"), "w", newline="") as fh:
        fields = ["wallet", "cutoff", "fills", "yes_bought", "yes_sold", "net_yes",
                  "usd_spent", "usd_received", "markets", "first_block"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for w_, cuts in w_stats.items():
            for label, s in cuts.items():
                if label not in ("cftc", "jan3", "full"):
                    continue
                w.writerow({"wallet": w_, "cutoff": label, "fills": s["fills"],
                            "yes_bought": round(s["yes_bought"], 2),
                            "yes_sold": round(s["yes_sold"], 2),
                            "net_yes": round(s["net_yes"], 2),
                            "usd_spent": round(s["usd_spent"], 2),
                            "usd_received": round(s["usd_received"], 2),
                            "markets": len(s["markets"]), "first_block": s["first_block"]})
    with open(os.path.join(CSV, "candidates_per_market.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["wallet", "market", "yes_bought", "yes_sold", "usd_spent", "fills"])
        w.writeheader(); w.writerows(w_per_market)

    cftc_totals = {
        "cftc_yes_target": PRIOR["cftc"]["yes_shares"],
        "cftc_window_total_buy_yes": tot_yes,
        "cftc_window_total_buy_usd": tot_usd,
        "cftc_window_distinct_buyers": len(tot_wal),
        "label": "derived: block-interpolated timestamps, ±1 min",
    }

    summary = {
        "markets_n": len(mk_stats), "fills_total": len(per_fill), "skipped_rows": skipped,
        "cftc": cftc_totals, "per_market": rows[:10],
        "candidates": {w: {k_: v for k_, v in s.items() if k_ != "markets"} for w, s in w_stats.items()},
    }
    json.dump(summary, open(os.path.join(CSV, "summary.json"), "w"), indent=1, default=str)

    # console digest
    print("FILLS:", len(per_fill), "SKIPPED:", skipped, "MARKETS:", len(mk_stats))
    print("\nTOP 8 MARKETS BY USD (full window):")
    for r in rows[:8]:
        print("  %-46s fills=%-7s txs=%-6s wallets=%-6s usd=%-12.0f yes_shares=%-12.0f"
              % (r["market"], r["fills"], r["txs"], r["wallets"], r["usd_all"], r["yes_bought_shares"]))
    print("\nCFTC WINDOW (Dec30-Jan4 blocks %d-%d):" % (CFTC_B[0], CFTC_B[1]))
    print("  total buy YES shares: %.0f   buy USD: %.0f   distinct buyers: %d"
          % (tot_yes, tot_usd, len(tot_wal)))
    print("\nCANDIDATES (cutoffs: cftc=Dec3->Jan4, jan3=Dec3->Jan3, full=whole window):")
    for w_, cuts in w_stats.items():
        for label in ("cftc", "jan3", "full"):
            s = cuts.get(label)
            print("  %s [%s] fills=%s yes_b=%.0f yes_s=%.0f net=%.0f usd_spent=%.0f usd_recv=%.0f mkts=%d firstblk=%s"
                  % (w_[:12], label, s["fills"], s["yes_bought"], s["yes_sold"], s["net_yes"],
                     s["usd_spent"], s["usd_received"], len(s["markets"]), s["first_block"]))
        if "cftc_buys_spread_seconds_derived" in cuts:
            print("    batch spread (derived): %.1f s over block span %s"
                  % ( cuts["cftc_buys_spread_seconds_derived"], cuts["cftc_buy_block_span"]))
    print("\nCFTC-window per-market (joined with writeup table = candidates_per_market.csv)")

if __name__ == "__main__":
    main()