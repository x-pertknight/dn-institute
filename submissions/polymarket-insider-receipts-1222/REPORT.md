# Report: Insider Trading Detection on Polymarket (Challenge #1222)

Candidate: Marco Amendola. Receipt-anchored rebuild from public, unauthenticated data (Polymarket
activity API + Polygon RPC logs + Gamma market resolution). First pass 2026-10-23; corrected,
receipt-anchored rebuild 2026-10-28; independently re-verified same day (fresh-context recomputation
from raw files; fixes applied — see section 6).

## TL;DR
We rebuilt CFTC case 9217-26 against "Burdensome-Mix" (complaint mask `0x31a5***...8ed9`, ¶48/¶57
= `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9`, the only dataset wallet matching) to the cent,
with every dollar backed by an on-chain USDC.e receipt (`eth_getTransactionReceipt`, no keys):

- **13 buys = indictment "13 separate occasions" (¶11)**: $96.00, $1,238.34, $85.00, $1,000.00,
  $100.00, $5,000.00, $100.00, $6,000.00, $50.00, $6,000.00, $50.00, $7,000.00, $7,215.00 =
  **$33,934.34** (indictment ¶10 "approximately $33,934"; on-chain sum in
  `data/receipts_summary.csv`). Secondary sources disagree on the printed figure — $33,034
  appears in some summaries (e.g. Dentons, ABC News), $33,934 in others; we do not attribute an
  "erratum" to any document without quoting its primary text. The on-chain receipts total is
  $33,934.34 exactly.
- **maduro-out-by-january-31: 436,759.61 Yes for $32,538.34 (avg $0.07450) = complaint ¶52**
  (rounded there as ">436,000 / ~$0.074 / ~$32,538").
- **Funding ladder = complaint ¶50**: 14,619.33 shares on Dec 30 evening ET (2 txs, 19:20/22:02 ET);
  73,685.38 on Jan 1 evening (18:57 ET); 90,347.29 the morning of Jan 2 (11:49 ET);
  **258,107.60 > 250,000 across three txs at Jan 2 20:38 / 21:15 / 21:58 ET** ("between 8:30 and
  10:00 PM ET").
- **All four ¶11 dollar groups are receipt-exact**: (a) $96; (b) $1,238.34 + $85.00; (c) ~$6,100
  (Jan 1: $1,000.00 + $100.00 + $5,000.00); (d) ~$6,150 = $6,000.00 + $150.00 (3,618.73
  war-powers shares = $100.00 + $50.00). An earlier draft flagged ¶11(c) as overstating —
  that was our parse error (¶11(c) vs (d)); withdrawn. Also ¶11(d)'s $7,050 = $7,000
  (87,500 shares) + a separate $50.00 US-forces buy 14 seconds earlier.
- **Proceeds: $443,815.29 in** = redemption 436,759.61 USDC.e (Jan 3 13:41:49Z = 8:41 AM ET, ≈4h21m
  after the ~4:21 AM EST announcement (4h20m49s), ¶13) + redemption 1,197.77 (20:25:23Z) + sales
  $5,857.90 (17,857.88 invade @ $0.176 + 5,371.68 war-powers @ $0.5054, Jan 4 00:02-00:03Z = the
  evening of Jan 3 ET, ¶56). Components are shown rounded to the cent and sum to 443,815.28;
  the total 443,815.29 comes from unrounded micro-USDC receipt values (see
  `data/receipts_summary.csv`), as does the funding ladder's 436,759.61 (its rounded parts sum
  to 436,759.60). Rounding note, not a discrepancy.
- **Profit: $409,880.95 = DOJ ¶15 "approximately $409,881"**; jan31-only
  436,759.61 − 32,538.34 = **$404,221.27 = CFTC ¶53 "more than $404,000"**.
- **13 buy occasions + 2 sale transactions = the 15 receipted transactions** (¶11 counts buy
  occasions; fills.jsonl contains 15 wallet txs; the 2 redemptions are 2 more).

## The detection finding: composite transactions poison naive fills-only parsers
Polymarket's neg-risk adapter (mint/merge + split escrow, documented in the CTF exchange contracts;
our rebuild confirms it empirically on-chain) packs many order-book legs into one transaction.
Parsing fills and attributing every leg to a wallet **invents position and cash**: in the accused
wallet's own transactions, fill rows attribute ~$6,080 of cash-buys and ~$348,000 of "sale
receipts" to it that its USDC.e receipts prove never moved (mirror/merge legs — e.g.
tx 0x845d5e6b: a counterparty pays $80,500 while the wallet pays $7,000 in the same tx; a merge
sale shows the wallet "buying" No at ~$0.84 in a market resolving to No).

The receipt-anchored frame (maker-side cash legs only) reproduces every receipt exactly
(self-check: buys $33,934.34 PASS; jan31 436,759.6/$32,538.34 PASS). **Rule for detectors: anchor
per-wallet flows to USDC.e settlement receipts; treat composite-tx mirror legs as
non-cash-attributable until receipts arbitrate them.**

## The other wallets (full scan, maker-cash frame; window multipliers below)
| wallet | Yes bought mk (sh / USD) | tk-frame sh | note |
|---|---|---|---|
| 0x31a56e9e...8ed9 = "Burdensome-Mix" | 461,186.9 / $33,934.34 | 88,573.7 | tk rows = receipts-proven phantom (mirrors) |
| 0x858d551d...1047 | 322,939.5 / $92,027.08 | 79,935.8 | 7 distinct markets bought; jan31 = 258,256.2 sh ($88,969.20) |
| 0xa72db174...ebd4 | 80,764.9 / $5,782.66 | 36,915.6 | total 117,680.5 Yes / $8,433.30 / **19 buy fills (1 mk + 18 tk) in ONE tx**, ~$0.0717 avg, no other fills in 12 days |
| 0x6d7776a0...b72c | 506,023.7 / $28,738.20 | 40,626.9 | bulk = maduro-out-in-2025 (322,116.4 sh / $8,464.31), not the January contract |

Multipliers, "other three vs the accused", receipt-true on both sides (all-mk frame):
CFTC window **1.1090×**; jan31-only **1.1108×**; our ET-aligned window Dec 30 00:00 ET → Jan 3
05:00Z end-exclusive (RPC-anchored cuts 80,976,379 → 81,148,570; the start cut sits at 00:20 ET —
the true midnight block ≈ 80,975,77x by the observed uniform 2.000 s/block cadence, not
RPC-anchored; zero cluster fills in between, so the figure is unaffected; uniform cadence, no
chain gap) **0.5644×** — the accused alone bought ~1.8× (1.77×) the other three combined. This is
our ET-aligned window, not ¶10's (Dec 27 – Jan 2, 9:58 PM EST — a longer window under which the
others bought more). If, instead, the (unverifiable) taker-frame rows of the three others are
real, the figures rise to ≈1.415× (CFTC) / ≈1.428× (jan31) / ≈0.692× (ET) / ≈1.405× (strict UTC).
Our 2026-10-23 first-pass multipliers (1.49×/1.34×/2.0×) mixed the frames across wallets and are
corrected here. Fetching the other wallets' receipts (3 more eth_getTransactionReceipt rounds,
~30 txs) would settle the rest.

## Heuristics (H1–H6)
- **H1 — composite-tx cash mismatch (receipt-arbitrated)**: fill rows attribute cash the wallet's
  USDC.e ledger contradicts in the same transaction. The trap: in composite neg-risk txs the
  OrderFilled `taker` is the transaction *initiator*, not the cash payer; mirror/merge legs
  attribute a counterparty's cash to the initiator. Measured on the accused wallet: +$6,080.06
  phantom buys, +$347,865.64 phantom sale receipts, +9,858.6 sh phantom "sells". Implied-price
  sanity checks do NOT catch this (the phantom legs print market-plausible prices — 0.8312 vs a
  real No ≈ 0.82). Detector without receipts: flag legs whose cash side disagrees with the
  wallet's USDC.e ledger; with receipts, arbitrate per-tx.
- **H2 — event-proximate accumulation ladder**: stepwise share accumulation up to >250,000 shares
  in one evening on the target market (funding ladder ¶50), followed by the event.
- **H3 — account/first-fill adjacency**: first fill ~1 day after wallet creation (¶9), on the
  target-market family, at extreme-low prices.
- **H4 — full exit on announcement/resolution**: 1:1 redemption within ~4h21m of the public
  announcement (¶13) + adjacent-market sells the same evening (¶56).
- **H5 — single-market, low-price conviction**: $32,538.34 into 436,759.61 shares of one
  far-future market at avg $0.0745 (¶52); 19-buy-fill microbatch variants (19 fills in ONE
  transaction, 0xa72db174).
- **H6 — resolution-family adjacency**: the wallet's activity clusters inside one
  resolution family (maduro/jan31, invade, us-forces, war-powers) rather than a diverse portfolio.

## Ranking (evidence-weighted)
Score = fraction of heuristics met **with data verified to that wallet's own evidence**
(H1 is only creditable where receipts exist; the others score on behavioral evidence only —
an intentional limitation, stated as such). Details in `data/ranking.csv`.

1. **0x31a56e9e...8ed9 (Burdensome-Mix) — 6/6, score 1.0** — every heuristic met and
   receipt-verified; the indictment's own wallet.
2. **0xa72db174...ebd4 — 3/6** — announcement-day single transaction, 19 fills, mk avg $0.0716,
   no other activity in 12 days; receipts not fetched (open work).
3. **0x858d551d...1047 — 2/6** — large jan31 position (258,256.2 sh, rank 5 full-scan), 7 markets
   in the family, but avg entry $0.344 (not the low-price conviction pattern).
4. **0x6d7776a0...b72c — 1/6** — resolution-family adjacency only; bulk is the 2025 contract.

Full-scan note: the biggest jan31 buyers overall (0x94cff0a6 761,883.2 sh; 0xc5adc0dc 620,819.3
sh) outrank the accused by position size and merit the receipt-fetch next step; the accused is
the 3rd-largest jan31 buyer in the full 124,850-fill scan.

## Method
1. Gamma (no auth): market resolution; 32 token IDs across the Maduro/Venezuela family.
2. OrderFilled/OrdersMatched **topic0-filtered scan with no emitter allow-list**, Polygon
   public RPC (drpc/publicnode/1rpc), Dec 26 - Jan 7, ~124,850 fills. The cluster's fills are
   all emitted by the **CTF Exchange** `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e`
   (composite mirror legs arise through neg-risk mint/merge routed via the adapter
   `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296`; `0x4d97dcd97e...` is the ConditionalTokens
   contract, not an exchange). Dec 30 - Jan 4 window shown; Dec 26-29 rows outside the wallet's
   funding/activity range excluded from artifacts.
   (blocks 80,793,979-81,312,371), checkpointed, 124,850 fills.
3. USDC.e receipts for the wallet's 15 fill txs + 2 redemptions; timestamps for 59 anchor blocks.
4. Frame-separated classification + receipts self-check (`cluster_slice.py`, PASS/PASS).

## Data & artifacts
`data/`: wallet_activity.csv, receipts_summary.csv, redemptions.csv,
fills_cluster_window.csv.gz (2,013 rows), window_multipliers.csv, funding_ladder.csv,
ranking.csv, SHA256SUMS (pinned). `code/`: polymarket_fetch.py (full chain scan),
dataapi.py, receipts_fetch.py, redeem_receipts.py, analyze.py, cluster_slice.py,
build_artifacts.py (generates data/ from raw; RAW_DIR/DATA_DIR env overrides).

## 6. Verification trail: what adversarial recomputation changed
An independent fresh-context recomputation pass (against the raw files, not our printed stats)
verified the receipt-anchored core exactly (15/15 txs to the micro-USDC; all four all-mk
multipliers reproduced) and caught three of our v2 errors, fixed here:
- The ET-window story: block 80,976,379 is Dec 30 00:20 ET, not midnight; the claimed
  "~20-min Polygon gap" was our boundary error dressed as a chain halt (RPC probes show uniform
  2.000 s/block cadence). Figure unaffected (zero cluster fills in the span); window relabeled.
- Two mixed-frame multipliers used the wrong denominator (jan31-only victim instead of the
  window victim): corrected 1.492→1.4145 and 0.730→0.6924.
- "¶11(c) overstates" withdrawn: our ¶-parse error; all four ¶11 groups are receipt-exact.
- Smaller: "second-largest jan31 buyer" for 0x858d was cluster-scoped (rank 5 full-scan); the
  redemption elapsed time is ≈4h21m, not ≈5h20m; 549,127 (v1 artifact) is not mk+tk (mk+tk =
  549,760.6); "precedes account creation" was backwards.

## Honesty notes
- Identity is not claimed: the wallet-to-account linkage is the complaint's own mask plus numeric
  concordance. Reproduction bound, not a deanonymization.
- ¶52's figures are the complaint's rounding ("over 436,000", "~$0.074", "~$32,538"); the receipts
  give exact 436,759.61 / $32,538.34 / $0.07450. Quoted with where the complaint rounds.
- Other wallets' receipts not fetched: their tk-frames are unverifiable, not proven phantom
  (the subject's are receipts-proven). Two cuts are provided for every multiplier.
- The mint/merge mechanism is documented Polymarket-CTF mechanics; nothing here proposes a novel
  decoding. The empirical contribution = receipts as the arbiter of mirrored fills.

## Why this matters for real-time detection
- Anchor flows to settlement receipts; composite mirror legs are cheap to flag (assetId-0 side
  amounts vs USDC.e transfer flows disagree ⇒ mirror).
- One-tx/19-fill batches and same-block first appearances are cheap in-stream features.
- Event-type discipline before anomaly hunting: a mixed-frame position table misstates everyone.