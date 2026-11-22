#!/usr/bin/env python3
"""build_artifacts.py - generate the submission's data/ CSVs from raw JSON evidence.

Inputs (RAW_DIR, default: code/raw - checked in): receipts_15tx.json,
receipts_redeems.json, dataapi_activity.json.
Outputs (DATA_DIR): wallet_activity.csv, redemptions.csv, receipts_summary.csv,
funding_ladder.csv, SHA256SUMS.

All numeric values come from raw on chain receipts, except the funding ladder, which is a
literal table verified in REPORT.md.
"""
import csv, glob, hashlib, json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # submission dir
RAW_DIR = os.environ.get("RAW_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw"))
# raw inputs are vendored at code/raw (see README); RAW_DIR relocation still supported
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
              [{"proxy_wallet": a["proxyWallet"],
                "type": a["type"], "side": a["side"], "outcome": a.get("outcome", ""),
                "market_slug": a.get("slug", ""), "size": a["size"],
                "usdc_size": a["usdcSize"], "price": a["price"],
                "timestamp": a["timestamp"],
                "iso_utc": __import__("datetime").datetime.utcfromtimestamp(a["timestamp"]).isoformat() + "Z",
                "condition_id": a["conditionId"], "tx": a["transactionHash"]} for a in act],
              ["proxy_wallet", "type", "side", "outcome", "market_slug",
               "size", "usdc_size", "price", "timestamp", "iso_utc", "condition_id", "tx"])

# 2) redemptions
rr = load("receipts_redeems.json")
if rr is not None:
    write_csv("redemptions.csv", list(usdc_flows(rr)),
              ["transaction_hash", "block", "timestamp", "usdc_e_in", "usdc_e_out"])

# 3) the 15 fill transactions' receipts summary
r15 = load("receipts_15tx.json")
if r15 is not None:
    write_csv("receipts_summary.csv", list(usdc_flows(r15)),
              ["transaction_hash", "block", "timestamp", "usdc_e_in", "usdc_e_out"])

# 4) funding ladder (complaint para 50 - receipt-verified)
write_csv("funding_ladder.csv", [
    {"step": 1, "date_et": "Dec 30 evening", "tx_et": "19:20 & 22:02", "shares": 14619.33,
     "note": "2 txs same evening (complaint para 50: first ladder rung)"},
    {"step": 2, "date_et": "Jan 1 evening", "tx_et": "18:57", "shares": 73685.38},
    {"step": 3, "date_et": "Jan 2 morning", "tx_et": "11:49", "shares": 90347.29},
    {"step": 4, "date_et": "Jan 2 evening", "tx_et": "20:38/21:15/21:58", "shares": 258107.60,
     "note": "3 txs; complaint: 'between 8:30 and 10:00 PM ET'"},
], ["step", "date_et", "tx_et", "shares", "note"])

# 5) checksums
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