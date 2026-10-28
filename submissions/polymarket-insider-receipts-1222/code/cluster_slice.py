#!/usr/bin/env python3
"""Slice raw/fills.jsonl for the 4 cluster wallets across the FULL scan (Dec 26 - Jan 7)
plus every sister row of the transactions touched, and compute the aggregates.

OrderFilled frame used throughout (documented in SUBMISSION.md):
  mk gives (ma, mi), tk gives (ta, ti); assetId == 0 means the side's asset is USDC.e.
  BUY  via a side: that side's assetId == 0 -> cash = its amount, shares = other side's amount, token = other assetId.
  SELL via a side: that side's assetId != 0 -> shares = its amount, cash = other side's amount, token = own assetId.
Frames kept SEPARATE (they are NOT the same cash):
  frame "mk"  = wallet is maker on a cash leg  (for 0x31a56e this reproduces the receipts exactly)
  frame "tk"  = wallet is taker on a cash leg  (for 0x31a56e these legs are phantom cash: composite
               mint bookkeeping - proven by receipts; kept in the stats for transparency)

Writes:
  claude_pack/fills_cluster_window.jsonl  (original rows, verbatim, sorted by block)
  cluster_stats.txt                       (human-readable summary; also printed to stdout)
"""
import json, os
from collections import defaultdict

BASE = '/Users/marco/inca-1222'
RAW = BASE + '/raw'
PACK = BASE + '/claude_pack'
os.makedirs(PACK, exist_ok=True)

W = '0x31a56e9e690c621ed21de08cb559e9524cdb8ed9'
PREFIXES = ['0x31a56e9e', '0x858d551d', '0xa72db174', '0x6d7776a0']
SCAN_LO, SCAN_HI = 80793979, 81312371
WIN_CFTC = (80966779, 81182771)   # Dec30 00:00Z - Jan4 00:00Z (receipts-anchored)
WIN_UTC = (80966779, 81139571)    # strict UTC Dec30 00:00Z - Jan3 00:00Z

# ---- token map ----
tmap = json.load(open(RAW + '/token_map.json'))
print('token_map.json entries:', len(tmap))
def canon(x):
    s = str(x).strip()
    try:
        return str(int(s, 16)) if s.lower().startswith('0x') else str(int(s))
    except Exception:
        return s
TOK = {}
for k, v in tmap.items():
    TOK.setdefault(k, v)
    c = canon(k)
    if c != k:
        TOK.setdefault(c, v)
for i, (k, v) in enumerate(tmap.items()):
    print('  sample:', str(k)[:34], '->', json.dumps(v)[:110])
    if i >= 1: break

def slug_outcome(tok):
    v = TOK.get(canon(tok)) if tok is not None else None
    if v is None:
        return None, None
    if isinstance(v, dict):
        return v.get('slug') or v.get('market_slug') or v.get('market'), v.get('outcome') or v.get('side')
    return v, None

# ---- schema introspection ----
f = open(RAW + '/fills.jsonl')
first = json.loads(f.readline())
keys = {k.lower(): k for k in first}
def K(*cands):
    for c in cands:
        if c in keys:
            return keys[c]
    return None
KB, KTX, KOH = K('b', 'block'), K('tx', 'txhash'), K('oh', 'orderhash')
KM, KT = K('mk', 'maker'), K('tk', 'taker')
KMA, KTA = K('ma', 'makerassetid'), K('ta', 'takerassetid')
KMI, KTI = K('mi', 'makeramount'), K('ti', 'takeramount')
KEM, KF = K('em', 'emitter'), K('f')
print('schema ok:', {c: K(c) for c in ('b', 'tx', 'oh', 'mk', 'tk', 'ma', 'ta', 'mi', 'ti', 'em', 'f')})

def num(x):
    if x is None: return 0.0
    if isinstance(x, int): return x / 1e6
    try:
        return float(x)
    except Exception:
        return 0.0

# ---- pass 1: cluster rows + full addr discovery ----
found = {}
txset = set()
cluster_rows = []

def is_cluster(v):
    if v is None: return None
    s = str(v).lower()
    if s in found.values():
        return s
    for p in PREFIXES:
        if s.startswith(p):
            found.setdefault(p, s)
            return s
    return None

f.seek(0)
for line in f:
    if not any(p in line.lower() for p in PREFIXES):
        continue
    j = json.loads(line)
    if is_cluster(j.get(KM)) or is_cluster(j.get(KT)):
        cluster_rows.append(j)
        txset.add(str(j.get(KTX)).lower())
f.close()
assert len(found) == 4, 'unresolved wallets: %s' % found
FULL = set(found.values())
print('cluster wallets:', found)

# ---- pass 2: sister rows (same tx, neither side a cluster wallet) ----
f = open(RAW + '/fills.jsonl')
sisters = []
for line in f:
    j = json.loads(line)
    if str(j.get(KTX)).lower() in txset and not (
            str(j.get(KM)).lower() in FULL or str(j.get(KT)).lower() in FULL):
        sisters.append(j)
f.close()

all_rows = sorted(cluster_rows + sisters, key=lambda r: (r.get(KB, 0), str(r.get(KTX))))
with open(PACK + '/fills_cluster_window.jsonl', 'w') as out:
    for r in all_rows:
        out.write(json.dumps(r) + '\n')
print('pack: %d cluster rows + %d sister rows = %d rows -> fills_cluster_window.jsonl'
      % (len(cluster_rows), len(sisters), len(all_rows)))

# ---- frame-aware classification ----
def classify(j, w):
    """Returns (kind, frame, slug, outcome, cash, shares).

    OrderFilled: maker gives (KMA, KMI), taker gives (KTA, KTI).
    assetId 0 = USDC cash; the other side holds the outcome token and its
    amount is SHARES. Cash always flows on the USDC-giving side.
    """
    w = str(w).lower()
    mk, tk = j.get(KM), j.get(KT)
    if str(mk).lower() == w:
        if str(j.get(KMA)) in ('0', '0x0', 'None', ''):          # maker gives USDC -> maker buys
            return 'buy', 'mk', slug_outcome(j.get(KTA))[0], slug_outcome(j.get(KTA))[1], num(j.get(KMI)), num(j.get(KTI))
        return 'sell', 'mk', slug_outcome(j.get(KMA))[0], slug_outcome(j.get(KMA))[1], num(j.get(KTI)), num(j.get(KMI))
    if str(tk).lower() == w:
        if str(j.get(KTA)) in ('0', '0x0', 'None', ''):          # taker gives USDC -> taker buys
            return 'buy', 'tk', slug_outcome(j.get(KMA))[0], slug_outcome(j.get(KMA))[1], num(j.get(KTI)), num(j.get(KMI))
        return 'sell', 'tk', slug_outcome(j.get(KTA))[0], slug_outcome(j.get(KTA))[1], num(j.get(KMI)), num(j.get(KTI))
    return 'none', None, None, None, None, None
# returns (kind frame slug outcome [cash or None] shares_or_cash):

AGG = defaultdict(lambda: {
    'rows_mk': 0, 'rows_tk': 0, 'first_b': 10 ** 12, 'last_b': 0,
    'buy_sh_mk': defaultdict(float), 'buy_usd_mk': defaultdict(float),
    'buy_sh_tk': defaultdict(float), 'buy_usd_tk': defaultdict(float),
    'sell_sh_mk': defaultdict(float), 'sell_sh_tk': defaultdict(float),
    'sell_usd_mk': 0.0, 'sell_usd_tk': 0.0})

def is_yes(oc):
    return oc is not None and str(oc).upper().startswith('YES')

def is_j31(slug):
    # the January Contract (indictment/complaint para 52) = EXACTLY this market;
    # all four Venezuela markets have "january-31" in their slugs, so a substring
    # filter would wrongly include war-powers/invade/us-forces (+24,427.34 sh here)
    return slug == 'maduro-out-by-january-31-2026-318'

for j in cluster_rows:
    b = j.get(KB, 0)
    for p in PREFIXES:
        w = found[p]
        kind, frm, slug, oc, cash, sh = classify(j, w)
        if kind == 'none':
            continue
        a = AGG[w]
        a['first_b'] = min(a['first_b'], b)
        a['last_b'] = max(a['last_b'], b)
        f2 = frm
        if kind == 'buy':
            a['rows_%s' % f2] += 1
            if is_yes(oc) and cash is not None:
                a['buy_sh_%s' % f2][slug] += sh
                a['buy_usd_%s' % f2][slug] += cash
        else:
            key = 'sell_sh_%s' % f2
            if is_yes(oc) and sh is not None:
                a[key][slug] += sh
            if f2 == 'mk':
                a['sell_usd_mk'] += cash if cash is not None else 0.0
            else:
                a['sell_usd_tk'] += cash if cash is not None else 0.0

# ---- window walks (Yes bought) ----
def walk(lo, hi, jan31, frame):
    out = defaultdict(float)
    for j in cluster_rows:
        b = j.get(KB, 0)
        if lo is not None and b < lo: continue
        if hi is not None and b > hi: continue
        for p in PREFIXES:
            w = found[p]
            kind, frm, slug, oc, cash, sh = classify(j, w)
            if kind != 'buy' or frm != frame or cash is None or not is_yes(oc):
                continue
            if jan31 and not is_j31(slug):
                continue
            out[w] += sh
    return out

wins = {
    'scan_full': (None, None, 'scan 26dec-7jan (all blocks in file)'),
    'cftc_window': (WIN_CFTC[0], WIN_CFTC[1], 'Dec30 00:00Z - Jan4 00:00Z (receipts-anchored)'),
    'strict_utc_dec30_jan3': (WIN_UTC[0], WIN_UTC[1], 'strict UTC Dec30-Jan3'),
}
ETS = {}
if os.path.exists(PACK + '/block_ts.json'):
    bts = json.load(open(PACK + '/block_ts.json'))
    if '_et_boundaries' in bts:
        sb, eb = bts['_et_boundaries']['start_block'], bts['_et_boundaries']['end_block_exclusive']
        wins['et_aligned_dec30_jan2'] = (sb, eb - 1,
            'ET-aligned Dec30-Jan2 (RPC-verified boundaries %s->%s)' % (bts['_et_boundaries'].get('start_utc'), bts['_et_boundaries'].get('end_utc')))
        ETS = bts['_et_boundaries']

rep = []
rep.append('=== cluster wallet aggregates, full scan ===')
for p, w in sorted(found.items()):
    a = AGG[w]
    tot_b_mk = sum(a['buy_sh_mk'].values())
    tot_b_tk = sum(a['buy_sh_tk'].values())
    rep.append('%s' % w)
    rep.append('  rows(mk/tk cash-legs): %d/%d  txs-blocks %d..%d' % (a['rows_mk'], a['rows_tk'], a['first_b'], a['last_b']))
    rep.append('  Yes bought MK-frame: %.1f sh ($%.2f)  | TK-frame: %.1f sh ($%.2f)' % (
        tot_b_mk, sum(a['buy_usd_mk'].values()), tot_b_tk, sum(a['buy_usd_tk'].values())))
    rep.append('  Yes sold MK-frame: %.1f sh ($%.2f recv) | TK-frame: %.1f sh ($%.2f recv)' % (
        sum(a['sell_sh_mk'].values()), a['sell_usd_mk'], sum(a['sell_sh_tk'].values()), a['sell_usd_tk']))
    for slug, v in sorted(a['buy_sh_mk'].items(), key=lambda kv: -kv[1])[:8]:
        rep.append('    MK-buy Yes %-44s %12.1f sh   $%10.2f' % (slug, v, a['buy_usd_mk'][slug]))

rep.append('')
rep.append('=== window aggregates: Yes bought per wallet per frame / multipliers vs 436,759.6 ===')
for name, (lo, hi, note) in sorted(wins.items()):
    for frame in ('mk', 'tk'):
        got = walk(lo, hi, False, frame)
        vic = got.get(W, 0.0)
        oth = sum(v for k, v in got.items() if k != W)
        rep.append('%s [%s] %s' % (name, frame, note))
        rep.append('   ' + ' | '.join('%s %.0f' % (p, got.get(found[p], 0.0)) for p in [
            '0x31a56e9e', '0x858d551d', '0xa72db174', '0x6d7776a0']))
        if vic:
            rep.append('   victim %.1f | otherThree %.1f = %.4fx | allFour %.1f = %.4fx' % (vic, oth, oth / vic, vic + oth, (vic + oth) / vic))

rep.append('')
rep.append('=== jan31-only window (multiplier 1.34x check) ===')
for frame in ('mk', 'tk'):
    got = walk(None, None, True, frame)
    vic = got.get(W, 0.0)
    oth = sum(v for k, v in got.items() if k != W)
    rep.append('jan31-only [%s]: victim %.1f | otherThree %.1f | ratio %.4f' % (frame, vic, oth, oth / vic if vic else 0))

rep.append('')
rep.append('=== subject wallet: per-tx table (receipts x fill-frame) ===')
rmap = {r['tx']: r for r in json.load(open(RAW + '/wallet_receipt_cash.json'))}
for j in sorted(cluster_rows, key=lambda r: (r.get(KB, 0), str(r.get(KTX)))):
    tx = str(j.get(KTX))
    if tx not in rmap:
        continue
    kind, frm, slug, oc, cash, sh = classify(j, W)
    r = rmap[tx]
    rep.append('blk %9d %s... in $%9.2f out $%9.2f | %-4s/%-2s %-42s sh %10.1f  frameUSD $%9.2f' % (
        r['b'], tx[:10], r['in'], r['out'], kind, frm, slug or '?', sh if sh and kind == 'buy' else (j.get(KMI, 0) / 1e6 if frm == 'mk' and kind == 'sell' else 0), cash if cash else 0))

rep.append('')
rep.append('=== SELF-CHECK vs receipts (mk-frame must reproduce them) ===')
mk_usd = sum(AGG[W]['buy_usd_mk'].values())
mk_j31 = sum(AGG[W]['buy_sh_mk'].get(s, 0.0) for s in AGG[W]['buy_sh_mk'] if is_j31(s))
mk_j31_usd = sum(AGG[W]['buy_usd_mk'].get(s, 0.0) for s in AGG[W]['buy_sh_mk'] if is_j31(s))
rep.append('mk-frame buy cash: $%.2f vs receipts $33934.34 -> %s' % (mk_usd, 'PASS' if abs(mk_usd - 33934.34) < 5 else 'FAIL'))
rep.append('mk-frame jan31:   %.1f sh ($%.2f) vs 436759.6 ($32538.34) -> %s ; avg $%.4f'
           % (mk_j31, mk_j31_usd, 'PASS' if abs(mk_j31 - 436759.6) < 1 and abs(mk_j31_usd - 32538.34) < 2 else 'FAIL', mk_j31_usd / mk_j31 if mk_j31 else 0))

txt = '\n'.join(rep)
open(BASE + '/cluster_stats.txt', 'w').write(txt)
print(txt)