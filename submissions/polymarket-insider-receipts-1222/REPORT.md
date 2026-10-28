# Report: Insider Trading Detection on Polymarket (Challenge #1222)

Candidate: Marco Amendola. Receipt-anchored rebuild from public, unauthenticated data (Polymarket
activity API + Polygon RPC logs + Gamma market resolution). First pass 2026-10-23; corrected,
receipt-anchored rebuild 2026-10-28; independently re-verified same day (fresh-context recomputation
from raw files; fixes applied - see section 6).

## TL;DR
We rebuilt CFTC v. Van Dyke, No. 1:26-cv-03369 (CFTC Release 9217-26) against "Burdensome-Mix" (complaint mask `0x31a5***...8ed9`, para 48/para 57
= `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9`, the only dataset wallet matching) to the cent,
with every dollar backed by an on-chain USDC.e receipt (`eth_getTransactionReceipt`, no keys):

- **13 buys = indictment "13 separate occasions" (para 11)**: $96.00, $1,238.34, $85.00, $1,000.00,
  $100.00, $5,000.00, $100.00, $6,000.00, $50.00, $6,000.00, $50.00, $7,000.00, $7,215.00 =
  **$33,934.34** (indictment para 10 "approximately $33,934"; on-chain sum in
  `data/receipts_summary.csv`). Secondary sources disagree on the printed figure: the DOJ SDNY
  press release prints $33,034
  (https://www.justice.gov/usao-sdny/pr/us-soldier-charged-using-classified-information-profit-prediction-market-bets)
  while the indictment prints $33,934 (para 10, p. 5; the indictment ships in the submission
  pack); we do not attribute an "erratum" to any document without quoting its primary text. The
  on-chain receipts total is $33,934.34 exactly.
- **maduro-out-by-january-31: 436,759.61 Yes for $32,538.34 (avg $0.07450) = complaint para 52**
  (rounded there as ">436,000 / ~$0.074 / ~$32,538").
- **Funding ladder = complaint para 50**: 14,619.33 shares on Dec 30 evening ET (2 txs, 19:20/22:02 ET);
  73,685.38 on Jan 1 evening (18:57 ET); 90,347.29 the morning of Jan 2 (11:49 ET);
  **258,107.60 > 250,000 across three txs at Jan 2 20:38 / 21:15 / 21:58 ET** ("between 8:30 and
  10:00 PM ET").
- **All four para 11 dollar groups are receipt-exact**: (a) $96; (b) $1,238.34 + $85.00; (c) ~$6,100
  (Jan 1: $1,000.00 + $100.00 + $5,000.00); (d) ~$6,150 = $6,000.00 + $150.00 (3,618.73
  war-powers shares = $100.00 + $50.00). An earlier draft flagged para 11(c) as overstating -
  that was our parse error (para 11(c) vs (d)); withdrawn. Also para 11(d)'s $7,050 = $7,000
  (87,500 shares) + a separate $50.00 US-forces buy 14 seconds earlier.
- **Proceeds: $443,815.29 in** = redemption 436,759.61 USDC.e (Jan 3 13:41:49Z = 8:41 AM ET, ~4h21m
  after the ~4:21 AM EST announcement (4h20m49s), para 13) + redemption 1,197.77 (20:25:23Z) + sales
  $5,857.90 (17,857.88 invade @ $0.176 + 5,371.68 war-powers @ $0.5054, Jan 4 00:02-00:03Z = the
  evening of Jan 3 ET, para 56). Components are shown rounded to the cent and sum to 443,815.28;
  the total 443,815.29 comes from unrounded micro-USDC receipt values (see
  `data/receipts_summary.csv`), as does the funding ladder's 436,759.61 (its rounded parts sum
  to 436,759.60). Rounding note, not a discrepancy.
- **Profit: $409,880.95 = DOJ para 15 "approximately $409,881"**; jan31-only
  436,759.61 - 32,538.34 = **$404,221.27 = CFTC para 53 "more than $404,000"**.
- **13 buy occasions + 2 sale transactions = the 15 receipted transactions** (para 11 counts buy
  occasions; fills.jsonl contains 15 wallet txs; the 2 redemptions are 2 more).

## The detection finding: composite transactions poison naive fills-only parsers
Polymarket's CTF Exchange emits one OrderFilled per maker order (tk = owner of the taker order)
plus one for the taker order itself (tk = exchange). Rows where a wallet appears as tk are its
counterparties' fills, already netted in the wallet's own taker-order row. In MINT/MERGE matches
those counterparty rows show the complementary token, so a naive parser books phantom No sales
and phantom buys: in the accused wallet's own transactions, fill rows attribute ~$6,080 of
cash-buys and ~$348,000 of "sale receipts" to it that its USDC.e receipts prove never moved
(e.g. tx 0x845d5e6b: a counterparty pays $80,500 while the wallet pays $7,000 in the same
transaction - the PositionSplit stakeholder in that tx is the exchange itself and the tx sender
is operator 0xcbd48cc9c6c9272dc4008c52f6e4f326ddd88832, not the wallet; a merge sale books the
wallet "buying" No at $0.8312 implied (share-weighted 9,954.79 USDC over 11,976.19 counterparty
shares; legs 0.765-0.838 each, tx 0xde1f1ed8) in a market the complaint notes resolved to No,
para 56). This is documented CTF Exchange mechanics, not a novel decoding.

The receipt-anchored frame (maker-side cash legs only) reproduces every receipt exactly
(self-check: buys $33,934.34 PASS, sells $5,857.90 PASS; jan31 436,759.6/$32,538.34 PASS). **Rule for detectors: anchor
per-wallet flows to USDC.e settlement receipts; treat composite-tx counterparty legs as
non-cash-attributable until receipts arbitrate them.**

## The other wallets (full scan, maker-cash frame; window multipliers below)
| wallet | Yes bought mk (sh / USD) | tk-frame sh | note |
|---|---|---|---|
| 0x31a56e9e...8ed9 = "Burdensome-Mix" | 461,186.9 / $33,934.34 | 88,573.7 | tk rows = counterparty fills; their cash attribution to the wallet is receipts-proven phantom |
| 0x858d551d...1047 | 322,939.5 / $92,027.08 | 79,935.8 | 7 distinct markets bought; jan31 = 258,256.2 sh ($88,969.20) |
| 0xa72db174...ebd4 | 80,764.9 / $5,782.66 | 36,915.6 | 80,764.9 Yes / $5,782.66 in one order, filled against 70 counterparty orders (71 OrderFilled rows), block 81,135,501, ~$0.0716 avg, no other fills in 12 days |
| 0x6d7776a0...b72c | 506,023.7 / $28,738.20 | 40,626.9 | bulk = maduro-out-in-2025 (322,116.4 sh / $8,464.31), not the January contract |

Multipliers, "other three vs the accused", receipt-true on both sides (all-mk frame):
CFTC window **1.1090x**; jan31-only **1.0280x** (448,977.7 vs 436,759.6 shares - all four wallets
measured inside the CFTC window; an earlier 1.1108x mixed a full-scan other-three jan31 total of
485,144.5 with the victim's jan31 window). Our ET-aligned window, Dec 30 00:00 ET -> Jan 3
05:00Z **end-exclusive** (RPC-anchored cuts 80,976,379 -> 81,148,571; block 81,148,570 has ts
04:59:59Z and belongs inside; zero cluster fills in it, so the figure is unchanged; the start cut
sits at 00:20 ET - the true midnight block ~80,975,77x by the observed uniform 2.000 s/block
cadence, not RPC-anchored; zero cluster fills in between; uniform cadence, no chain gap)
**0.5644x** - the accused alone bought ~1.8x (1.77x) the other three combined. This is our
ET-aligned window, not para 10's (Dec 27 - Jan 2, 9:58 PM EST - a longer window under which the
others bought more). The other wallets' cash legs are fill-frame only; their receipts are not
fetched (3 more eth_getTransactionReceipt rounds, ~30 txs). Our 2026-10-23 first-pass
multipliers (1.49x/1.34x/2.0x) mixed the frames across wallets and are corrected here.

## Heuristics (H1-H6)
- **H1 - composite-tx cash mismatch (receipt-arbitrated)**: fill rows attribute cash the wallet's
  USDC.e ledger contradicts in the same transaction. The emission rule is fill-decidable and
  verified exactly: across the four cluster wallets, every tk == wallet row (976 of 976) sits in
  a transaction where the wallet has its own taker row (mk == wallet, tk == exchange) with shares
  conserved per tx (79/79 transactions) - so tk-rows are counterparties' fills, already netted in
  the wallet's own row; in MINT/MERGE matches they carry the complementary token. Naive parsing
  books: +$6,080.06 phantom buys, +$347,865.64 phantom sale receipts, +9,858.6 sh phantom
  "sells". Implied-price sanity checks do NOT catch this ($0.8312 implied USD per No share,
  share-weighted across 17 counterparty legs; legs clear 0.765-0.838). Detector without
  receipts: flag legs whose cash side disagrees with the wallet's USDC.e ledger; with receipts,
  arbitrate per-tx.
- **H2 - event-proximate accumulation ladder**: stepwise share accumulation up to >250,000 shares
  in one evening on the target market (funding ladder para 50), followed by the event.
- **H3 - account/first-fill adjacency**: first fill ~1 day after wallet creation (para 9), on the
  target-market family, at extreme-low prices.
- **H4 - full exit on announcement/resolution**: 1:1 redemption within ~4h21m of the public
  announcement (para 13) + adjacent-market sells the same evening (para 56).
- **H5 - single-market, low-price conviction**: $32,538.34 into 436,759.61 shares of one
  far-future market at avg $0.0745 (para 52); single-order entry variants: one order for
  80,764.9 Yes / $5,782.66 filled against 70 counterparty orders in one transaction (71
  OrderFilled rows, block 81,135,501, 0xa72db174).
- **H6 - resolution-family adjacency**: the wallet's activity clusters inside one
  resolution family (maduro/jan31, invade, us-forces, war-powers) rather than a diverse portfolio.

## Ranking (evidence-weighted)
Score = fraction of heuristics met **with data verified to that wallet's own evidence**
(H1 is only creditable where receipts exist; the others score on behavioral evidence only -
an intentional limitation, stated as such). Details in `data/ranking.csv`.

1. **0x31a56e9e...8ed9 (Burdensome-Mix) - 6/6, score 1.0** - every heuristic met and
   receipt-verified; the indictment's own wallet.
2. **0xa72db174...ebd4 - 3/6** - announcement-day single transaction: one order, 80,764.9 Yes
   / $5,782.66 (~$0.0716 avg), 71 OrderFilled rows vs 70 counterparties, block 81,135,501; no
   other activity in 12 days; receipts not fetched (open work).
3. **0x858d551d...1047 - 2/6** - large jan31 position (258,256.2 sh, rank 5 full-scan), 7 markets
   in the family, but avg entry $0.344 (not the low-price conviction pattern).
4. **0x6d7776a0...b72c - 1/6** - resolution-family adjacency only; bulk is the 2025 contract.

Full-scan note: the biggest jan31 buyers overall (0x94cff0a6 761,883.2 sh; 0xc5adc0dc 620,819.3
sh) outrank the accused by position size and merit the receipt-fetch next step; the accused is
the 3rd-largest jan31 buyer in the full 124,850-fill scan.

## Method
1. Gamma (no auth): market resolution; 32 token IDs across the Maduro/Venezuela family.
2. OrderFilled/OrdersMatched **topic0-filtered scan with no emitter allow-list**, Polygon
   public RPC (drpc/publicnode/1rpc), Dec 26 - Jan 7, ~124,850 fills. The cluster's fills are
   all emitted by the **CTF Exchange** `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e`: one
   OrderFilled per maker order (tk = owner of the taker order) plus one for the taker order
   itself (tk = exchange); composite mint/merge legs route through the adapter
   `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296`; `0x4d97dcd97e...` is the ConditionalTokens
   contract, not an exchange. The counterparty tk-rows this creates are covered in "The
   detection finding". Documented CTF Exchange mechanics, not a novel decoding. Dec 30 - Jan 4
   window shown; Dec 26-29 rows outside the wallet's funding/activity range excluded from
   artifacts.
   (blocks 80,793,979-81,312,371), checkpointed, 124,850 fills.
3. USDC.e receipts for the wallet's 15 fill txs + 2 redemptions; timestamps for 57 anchor blocks.
4. Frame-separated classification + receipts self-check (`cluster_slice.py`: buys PASS, sells PASS, jan31 shares PASS vs activity).

## Data & artifacts
`data/`: wallet_activity.csv, receipts_summary.csv, redemptions.csv,
fills_cluster_window.csv.gz (2,013 rows), window_multipliers.csv, funding_ladder.csv,
ranking.csv, SHA256SUMS (pinned). `code/`: polymarket_fetch.py (full chain scan),
dataapi.py, receipts_fetch.py, redeem_receipts.py, analyze.py, cluster_slice.py,
build_artifacts.py (generates all data/ CSVs + SHA256SUMS from `code/raw/` input JSONs plus
the verified literal tables; RAW_DIR/DATA_DIR env overrides). `code/raw/` holds the evidence
files (receipts, activity, token map, block timestamps, the 2,013-row cluster slice) so the
build reruns from a fresh checkout; `raw/fills.jsonl` (the 124,850-fill scan) is regenerated
by the scan command, not checked in.

## 6. Verification trail: what adversarial recomputation changed
An independent fresh-context recomputation pass (against the raw files, not our printed stats)
verified the receipt-anchored core exactly (15/15 txs to the micro-USDC; all four all-mk
multipliers reproduced) and caught three of our v2 errors, fixed here:
- The ET-window story: block 80,976,379 is Dec 30 00:20 ET, not midnight; the claimed
  "~20-min Polygon gap" was our boundary error dressed as a chain halt (RPC probes show uniform
  2.000 s/block cadence). Figure unaffected (zero cluster fills in the span); window relabeled.
- Two mixed-frame multipliers used the wrong denominator (jan31-only victim instead of the
  window victim): corrected 1.492 -> 1.4145 and 0.730 -> 0.6924. (The mixed frame itself was
  later withdrawn; see the 2026-10-28 fix-pass bullet below.)
- "para 11(c) overstates" withdrawn: our para-parse error; all four para 11 groups are receipt-exact.
- Smaller: "second-largest jan31 buyer" for 0x858d was cluster-scoped (rank 5 full-scan); the
  redemption elapsed time is ~4h21m, not ~5h20m; 549,127 (v1 artifact) is not mk+tk (mk+tk =
  549,760.6); "precedes account creation" was backwards.
- 2026-10-28 author-review fix pass: the neg-risk "taker is the tx initiator" story was replaced
  by the documented OrderFilled emission (one row per maker order, tk = the taker order's owner,
  plus one taker row, tk = exchange; fill-decidable and verified on all 976 tk==wallet rows);
  the mixed-frame multiplier column was withdrawn and the jan31 multiplier restated from 1.1108
  (full-scan other-three) to 1.0280 (CFTC window on both sides); the 0xa72db174 entry was
  corrected to its single order (80,764.9 Yes / $5,782.66, 71 OrderFilled rows vs 70
  counterparties); the ET-window end cut was restated end-exclusive 81,148,571 (block
  81,148,570 has ts 04:59:59Z and is inside; zero cluster fills in it).

## Honesty notes
- Identity is not claimed: the wallet-to-account linkage is the complaint's own mask plus numeric
  concordance. Reproduction bound, not a deanonymization.
- para 52's figures are the complaint's rounding ("over 436,000", "~$0.074", "~$32,538"); the receipts
  give exact 436,759.61 / $32,538.34 / $0.07450. Quoted with where the complaint rounds.
- Other wallets' receipts not fetched: their cash legs are fill-frame only (the subject's is
  receipts-proven). The tk-rows themselves are fill-decidable and verified (emission rule,
  above).
- The mint/merge mechanism is documented Polymarket-CTF mechanics; nothing here proposes a novel
  decoding. The empirical contribution = receipts as the arbiter of mirrored fills.

## Why this matters for real-time detection
- Anchor flows to settlement receipts; composite counterparty legs are cheap to flag (assetId-0
  side amounts vs USDC.e transfer flows disagree => a mirrored fill).
- One-tx multi-order batches (70 counterparty orders in one tx) and same-block first appearances
  are cheap in-stream features.
- Event-type discipline before anomaly hunting: a mixed-frame position table misstates everyone.