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
    self-check against receipts (`raw/wallet_receipt_cash.json`, rebuilt from receipts by
    `receipts_fetch.py`) + against the wallet's self-reported activity for share counts,
    → `raw/fills_cluster_window.jsonl` + `cluster_stats.txt`.
  - `build_artifacts.py` — generates the four receipt-derived tables in `data/` from raw JSON.
Raw JSONs live in `raw/` beside the scripts (each script derives its own `raw/` via
`BASE_DIR`/`dirname(__file__)`); `build_artifacts.py` regenerates the four receipt-derived
CSVs (`RAW_DIR`/`DATA_DIR` env overrides). The remaining three
(`window_multipliers.csv`, `funding_ladder.csv`, `ranking.csv`) are static copies of figures
independently re-verified in `REPORT.md` §6 — stated as static, not hidden behind a compute
step. Stdlib only, no requirements.

## How to reproduce

```bash
python3 code/polymarket_fetch.py --meta    # token map
python3 code/polymarket_fetch.py --blocks  # block anchors (checkpointed)
python3 code/polymarket_fetch.py --probe   # optional RPC pool probe
python3 code/polymarket_fetch.py --scan 80793979 81312371   # full OrderFilled scan -> code/raw/fills.jsonl (124,850 fills; ~1h on free RPCs)
python3 code/dataapi.py                    # wallet activity + positions -> code/raw/dataapi_activity.json
python3 code/receipts_fetch.py             # 15 fill-tx + 2 redemption receipts; writes code/raw/wallet_receipt_cash.json (from receipts) + code/claude_pack/{receipts_15tx,block_ts}.json
python3 code/redeem_receipts.py            # redemption receipts detail
python3 code/cluster_slice.py              # frame-separated rebuild + self-check -> code/raw/fills_cluster_window.jsonl + cluster_stats.txt
RAW_DIR="$PWD/code/raw" python3 code/build_artifacts.py    # regenerates data/*.csv + SHA256SUMS
```
All scripts accept `BASE_DIR` to relocate; stdlib only. The full chain-scan window and all block
anchors are RPC-verified.

Public endpoints only; no keys; no paid APIs. The full chain-scan window and all block anchors
are RPC-verified (`block_ts.json` is available on request).

## Submission note

Report and figures were produced with an AI agent as a research tool under the author's
direction, and every number in `REPORT.md` is anchored to an on-chain receipt or raw file in
`data/`; the independent adversarial recomputation pass and its fixes are described there.