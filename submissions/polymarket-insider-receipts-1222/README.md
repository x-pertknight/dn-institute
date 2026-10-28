# Submission: Insider Trading Detection on Polymarket — issue #1222

Candidate: Marco Amendola. Receipt-anchored rebuild of CFTC case 9217-26 from public,
unauthenticated data (Polymarket activity API + Polygon RPC logs + Gamma market resolution).

The one-line finding: **every dollar in the charging documents reproduces to the cent from
on-chain USDC.e receipts, and the wallet-mirror artifacts the exchanges emit (neg-risk
mint/merge) poison naive fills-only parsers — they invent ~$6,080 of phantom buys and
~$348,000 of phantom sale receipts for the accused wallet alone.**

## What is in this directory

- `REPORT.md` — full report: methodology, findings, heuristics, ranking, honesty notes.
- `data/` — investigation artifacts in CSV (`SHA256SUMS` pins them):
  `wallet_activity.csv` (the wallet's full public activity), `receipts_summary.csv`
  (per-tx USDC.e in/out for the 15 fill transactions), `redemptions.csv`,
  `fills_cluster_window.csv.gz` (2,013 fills of the 4-wallet cluster + same-tx sister rows),
  `window_multipliers.csv`, `funding_ladder.csv`, `ranking.csv`.
- `code/` — the collection and analysis code (stdlib-only Python 3):
  - `polymarket_fetch.py` — Polygon `OrderFilled` scan (all emitters), Dec 26 – Jan 7
    (blocks 80,793,979–81,312,371), checkpointed → `raw/fills.jsonl` (124,850 fills).
  - `dataapi.py` — Polymarket public activity API (no auth) → 17 activity rows.
  - `receipts_fetch.py` / `redeem_receipts.py` — `eth_getTransactionReceipt` for the 15 fill
    txs + 2 redemptions; per-tx USDC.e flows (the arbiter for every number).
  - `analyze.py` — day-1 verification + clustering pass against `raw/fills.jsonl`.
  - `cluster_slice.py` — frame-separated (maker/taker) rebuild for the 4 cluster wallets,
    receipts self-check → `csv/`+ `cluster_stats.txt`.
  - `build_artifacts.py` — generates everything in `data/` from the raw JSON.
Raw JSONs live in `raw/` beside the scripts (each script derives its own `raw/` from
`dirname(__file__)`); `build_artifacts.py` regenerates everything in `data/` and takes
`RAW_DIR`/`DATA_DIR` env overrides. Stdlib only — no requirements.

## How to reproduce

```bash
python3 code/polymarket_fetch.py   # writes code/raw/fills.jsonl (the full scan; ~1h on free RPCs)
python3 code/dataapi.py            # public activity API
python3 code/receipts_fetch.py     # 15 fill-tx receipts
python3 code/redeem_receipts.py    # 2 redemption receipts
python3 code/cluster_slice.py      # frame-separated rebuild + receipt self-check
RAW_DIR="$PWD/code/raw" python3 code/build_artifacts.py   # regenerates data/*.csv + SHA256SUMS
```

Public endpoints only; no keys; no paid APIs. The full chain-scan window and all block anchors
are RPC-verified (`block_ts.json` is available on request).

## Submission note

Report and figures were produced with an AI agent as a research tool under the author's
direction, and every number in `REPORT.md` is anchored to an on-chain receipt or raw file in
`data/`; the independent adversarial recomputation pass and its fixes are described there.