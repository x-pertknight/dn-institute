# Submission: Insider Trading Detection on Polymarket - issue #1222

Candidate: Marco Amendola. Receipt-anchored rebuild of CFTC v. Van Dyke, No. 1:26-cv-03369 (CFTC Release 9217-26) from public,
unauthenticated data (Polymarket activity API + Polygon RPC logs + Gamma market resolution).

The one-line finding: **every receipt-level figure in the charging documents reproduces
exactly from on-chain USDC.e receipts, and the CTF Exchange's OrderFilled emission (one row
per maker order, tk = owner of the taker order, plus one row for the taker order itself,
tk = exchange; in MINT/MERGE matches the counterparty rows carry the complementary token)
poisons naive fills-only parsers - they invent ~$6,080 of phantom buys and ~$348,000 of
phantom sale receipts for the accused wallet alone.**

Residuals vs the charging documents (receipt-exact on our side): indictment para 16's Jan 3
"vault" figure $437,859 vs redemptions $437,957.39; para 16/59's $444,209 vs inflows
$443,815.29 - two downstream transfer figures differ within rounding.

## What is in this directory

- `REPORT.md` - full report: methodology, findings, heuristics, ranking, honesty notes.
- `data/` - investigation artifacts in CSV (`SHA256SUMS` pins them):
  `wallet_activity.csv` (the wallet's full public activity), `receipts_summary.csv`
  (per-tx USDC.e in/out for the 15 fill transactions), `redemptions.csv`,
  `fills_cluster_window.csv.gz` (2,013 fills of the 4-wallet cluster + same-tx sister rows),
  `window_multipliers.csv`, `funding_ladder.csv`, `ranking.csv`.
- `code/` - the collection and analysis code (stdlib-only Python 3):
  - `polymarket_fetch.py` - Polygon `OrderFilled` scan (all emitters), Dec 26 - Jan 7
    (blocks 80,793,979-81,312,371), checkpointed -> `raw/fills.jsonl` (124,850 fills).
  - `dataapi.py` - Polymarket public activity API (no auth) -> 17 activity rows.
  - `receipts_fetch.py` / `redeem_receipts.py` - `eth_getTransactionReceipt` for the 15 fill
    txs + 2 redemptions; per-tx USDC.e flows (the arbiter for every number).
  - `analyze.py` - day-1 verification + clustering pass against `raw/fills.jsonl`.
  - `cluster_slice.py` - frame-separated (maker/taker) rebuild for the 4 cluster wallets,
    self-check against receipts (`raw/wallet_receipt_cash.json`, rebuilt from receipts by
    `receipts_fetch.py`): buy cash and sell cash vs receipts, jan31 shares vs the wallet's
    self-reported activity -> `raw/fills_cluster_window.jsonl` + `cluster_stats.txt`.
  - `build_artifacts.py` - generates all seven `data/` tables + `SHA256SUMS` from the checked-in
    raw JSONs and verified literal tables.
Raw input JSONs are checked in at `code/raw/` (receipts, activity, token map, block
timestamps, the 2,013-row cluster slice); each script derives its own `raw/` via
`BASE_DIR`/`dirname(__file__)`. `build_artifacts.py` regenerates all seven `data/` CSVs
plus SHA256SUMS from them (`RAW_DIR`/`DATA_DIR` env overrides): four tables from the
evidence files, three (`window_multipliers.csv`, `funding_ladder.csv`, `ranking.csv`) from
literal tables verified in `REPORT.md`. `raw/fills.jsonl`, the 124,850-fill full scan, is
regenerated live by the scan command above and is not checked in. Stdlib only, no requirements.

## How to reproduce

```bash
python3 code/polymarket_fetch.py --meta    # token map
python3 code/polymarket_fetch.py --blocks  # block anchors (checkpointed)
python3 code/polymarket_fetch.py --probe   # optional RPC pool probe
python3 code/polymarket_fetch.py --scan 80793979 81312371   # full OrderFilled scan -> code/raw/fills.jsonl (124,850 fills; ~1h on free RPCs)
python3 code/dataapi.py                    # wallet activity + positions -> code/raw/dataapi_activity.json
python3 code/receipts_fetch.py             # 15 fill-tx + 2 redemption receipts -> code/raw/{receipts_15tx.json, block_ts.json, wallet_receipt_cash.json}
python3 code/redeem_receipts.py            # redemption receipts -> code/raw/receipts_redeems.json
python3 code/cluster_slice.py              # frame-separated rebuild + self-check -> code/raw/fills_cluster_window.jsonl + cluster_stats.txt
python3 code/build_artifacts.py            # regenerates data/*.csv + SHA256SUMS from code/raw (checked in; no refetch needed)
```
All scripts accept `BASE_DIR` to relocate; stdlib only. The full chain-scan window and all block
anchors are RPC-verified.

Public endpoints only; no keys; no paid APIs. The full chain-scan window and all block anchors
are RPC-verified (block timestamps shipped in `code/raw/block_ts.json`).

## Submission note

Report and figures were produced with an AI agent as a research tool under the author's
direction, and every number in `REPORT.md` is anchored to an on-chain receipt or raw file in
`data/`; the independent adversarial recomputation pass and its fixes are described there.