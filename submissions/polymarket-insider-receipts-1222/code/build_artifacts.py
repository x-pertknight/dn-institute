#!/usr/bin/env python3
"""build_artifacts.py - generate the submission's data/ CSVs from raw JSON evidence.

Inputs (RAW_DIR, default: sibling dir "raw_next_to_parent"): receipts_15tx.json,
receipts_redeems.json, dataapi_activity.json, fills_cluster_window.jsonl.
Outputs (DATA_DIR): wallet_activity.csv, fills_cluster_window.csv.gz, redemptions.csv,
receipts_summary.csv, window_multipliers.csv, funding_ladder.csv, ranking.csv, SHA256SUMS.

All numeric values come from raw on-chain receipts or from tables verified by an
independent recomputation pass (see REPORT.md section 6).
"""
import csv, glob, gzip, hashlib, io, json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # submission dir
RAW_DIR = os.environ.get("RAW_DIR", os.path.join(BASE, "raw"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
os.makedirs(DATA_DIR, exist_ok=True)
USDC_E = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
WALLET = "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

def load(name):
    path = os.path.join(RAW_DIR, name)
    if not os.path.exists(path):
        print(f"skip (missing {path})")
        return None
    with open(path) as f:
        return json.load(f)

def usdc_flows(receipts):
    """Per-tx USDC.e Transfer totals touching the wallet. receipts = list of RPC receipts."""
    for r in receipts:
        tmin, tmax = 0.0, 0.0
        ts, block = "", ""
        for log in r.get("logs", []):
            if log.get("address", "").lower() != USDC_E:
                continue
            topics = log.get("topics", [])
            if topics and topics[0] == TRANSFER and len(topics) == 3:
                frm = topics[1][-40:].lower()
                to = topics[2][-40:].lower()
                amt = int(log["data"], 16) / 1e6
                if to == WALLET[2:]:
                    tmin += amt
                if frm == WALLET[2:]:
                    tmax += amt
            ts = ts or str(int(log.get("blockTimestamp", "0"), 16))
            block = block or str(int(log.get("blockNumber", "0"), 16))
        yield {"transaction_hash": r.get("transactionHash", ""), "block": block,
               "timestamp": ts, "usdc_e_in": "%.6f" % tmin, "usdc_e_out": "%.6f" % tmax}

def write_csv(name, rows, keys):
    with open(os.path.join(DATA_DIR, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {name} ({len(rows)} rows)")

# 1) wallet activity (Polymarket public activity API - the 17 rows)
act = load("dataapi_activity.json")
if act is not None:
    write_csv("wallet_activity.csv",
              [{"pseudonym": a.get("pseudonym", ""), "proxy_wallet": a["proxyWallet"],
                "type": a["type"], "side": a["side"], "outcome": a.get("outcome", ""),
                "market_slug": a.get("slug", ""), "size": a["size"],
                "usdc_size": a["usdcSize"], "price": a["price"],
                "timestamp": a["timestamp"],
                "iso_utc": __import__("datetime").datetime.utcfromtimestamp(a["timestamp"]).isoformat() + "Z",
                "condition_id": a["conditionId"], "tx": a["transactionHash"]} for a in act],
              ["pseudonym", "proxy_wallet", "type", "side", "outcome", "market_slug",
               "size", "usdc_size", "price", "timestamp", "iso_utc", "condition_id", "tx"])

# 2) cluster fills slice -> csv.gz
sl = os.path.join(RAW_DIR, "fills_cluster_window.jsonl")
if os.path.exists(sl):
    out, n = os.path.join(DATA_DIR, "fills_cluster_window.csv.gz"), 0
    with open(sl) as f:
        # fixed mtime so the artifact + its SHA256 are reproducible
        rows = ["\t".join([])]
        buf, w = io.StringIO(), None
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            row = {k: row.get(k, "") for k in ["b", "tx", "li", "mk", "tk", "ma", "ta", "mi", "ti", "em", "f"]}
            if w is None:
                w = csv.DictWriter(buf, fieldnames=list(row))
                w.writeheader()
            w.writerow(row)
            n += 1
        data = buf.getvalue().encode()
    with open(out, "wb") as fobj, gzip.GzipFile(fileobj=fobj, mode="wb", mtime=0) as gz:
        gz.write(data)
    print(f"wrote fills_cluster_window.csv.gz ({n} rows, mtime=0)")

# 3) redemptions
rr = load("receipts_redeems.json")
if rr is not None:
    write_csv("redemptions.csv", list(usdc_flows(rr)),
              ["transaction_hash", "block", "timestamp", "usdc_e_in", "usdc_e_out"])

# 4) the 15 fill transactions' receipts summary
r15 = load("receipts_15tx.json")
if r15 is not None:
    write_csv("receipts_summary.csv", list(usdc_flows(r15)),
              ["transaction_hash", "block", "timestamp", "usdc_e_in", "usdc_e_out"])

# 5) window multipliers (verified tables - see REPORT.md section 6)
write_csv("window_multipliers.csv", [
    {"window": "CFTC Dec30-Jan4", "victim_mk_sh": 460552.9, "other3_mk_sh": 510734.1,
     "other3_mk_tk_sh": 651456.0, "ratio_all_mk": 1.1090, "ratio_mixed": 1.4145},
    {"window": "jan31-only", "victim_mk_sh": 436759.6, "other3_mk_sh": 485144.5,
     "other3_mk_tk_sh": 623497.4, "ratio_all_mk": 1.1108, "ratio_mixed": 1.4276},
    {"window": "ET-aligned Dec30-Jan2", "victim_mk_sh": 460552.9, "other3_mk_sh": 259955.8,
     "other3_mk_tk_sh": 318883.0, "ratio_all_mk": 0.5644, "ratio_mixed": 0.6924},
    {"window": "strict-UTC Dec30-Jan3", "victim_mk_sh": 201881.6, "other3_mk_sh": 234535.3,
     "other3_mk_tk_sh": 283588.9, "ratio_all_mk": 1.1617, "ratio_mixed": 1.4047},
], ["window", "victim_mk_sh", "other3_mk_sh", "other3_mk_tk_sh", "ratio_all_mk", "ratio_mixed"])

# 6) funding ladder (complaint para 50 - receipt-verified)
write_csv("funding_ladder.csv", [
    {"step": 1, "date_et": "Dec 30 evening", "tx_et": "19:20 & 22:02", "shares": 14619.33,
     "note": "2 txs same evening (complaint para 50: first ladder rung)"},
    {"step": 2, "date_et": "Jan 1 evening", "tx_et": "18:57", "shares": 73685.38},
    {"step": 3, "date_et": "Jan 2 morning", "tx_et": "11:49", "shares": 90347.29},
    {"step": 4, "date_et": "Jan 2 evening", "tx_et": "20:38/21:15/21:58", "shares": 258107.60,
     "note": "3 txs; complaint: 'between 8:30 and 10:00 PM ET'"},
], ["step", "date_et", "tx_et", "shares", "note"])

# 7) ranking (evidence-weighted heuristics; see REPORT.md sections 7-8)
write_csv("ranking.csv", [
    {"wallet": "0x31a56e9e...8ed9 (Burdensome-Mix)", "rank": 1, "score_fraction": "6/6",
     "heuristics_met": "H1,H2,H3,H4,H5,H6", "receipts_fetched": "yes",
     "note": " indictment/case wallet; every dollar receipt-anchored"},
    {"wallet": "0xa72db174...ebd4", "rank": 2, "score_fraction": "3/6",
     "heuristics_met": "H4,H5,H6 (H1 unverifiable, no receipts)", "receipts_fetched": "no",
     "note": "one tx (Jan 2 21:44Z, announcement day), 19 fills, mk avg $0.0716, no other fills in 12 days"},
    {"wallet": "0x858d551d...1047", "rank": 3, "score_fraction": "2/6",
     "heuristics_met": "H5,H6 (H1 unverifiable)", "receipts_fetched": "no",
     "note": "7 markets, jan31 rank 5 overall (258,256.2 sh), mk avg $0.344 on jan31"},
    {"wallet": "0x6d7776a0...b72c", "rank": 4, "score_fraction": "1/6",
     "heuristics_met": "H6", "receipts_fetched": "no",
     "note": "bulk is the 2025 contract, not the January one; resolution-family adjacency only"},
], ["wallet", "rank", "score_fraction", "heuristics_met", "receipts_fetched", "note"])

# 8) checksums
hashes = []
for path in sorted(glob.glob(os.path.join(DATA_DIR, "*"))):
    if os.path.basename(path) == "SHA256SUMS":
        continue
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    hashes.append(f"{h}  {os.path.basename(path)}")
with open(os.path.join(DATA_DIR, "SHA256SUMS"), "w") as f:
    f.write("\n".join(hashes) + "\n")
print(f"wrote SHA256SUMS ({len(hashes)} files)")
print("done")