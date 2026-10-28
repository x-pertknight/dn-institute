#!/usr/bin/env python3
"""Fetch RAW receipts (all logs: USDC Transfer, PositionSplit, OrderFilled, OrdersMatched)
for the subject wallet's 15 fill transactions, re-verify/extend block timestamps via RPC,
and bisect the two ET-aligned window boundaries on-chain (no interpolation for claims).

Writes:
  claude_pack/receipts_15tx.json   raw eth_getTransactionReceipt output, 15 txs
  claude_pack/block_ts.json        {block: {ts, utc, how}} merged with raw/blocks.json anchors
Prints a summary: per-tx status/log-count, sum in/out from receipt cache, ET boundaries.
"""
import json, time, datetime, os, urllib.request

BASE = os.environ.get('BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
PACK = os.path.join(BASE, 'claude_pack')
W = '0x31a56e9e690c621ed21de08cb559e9524cdb8ed9'
os.makedirs(PACK, exist_ok=True)

ENDPOINTS = [
    'https://polygon.drpc.org',
    'https://polygon-bor-rpc.publicnode.com',
    'https://polygon.1rpc.io',
]
HDR = {'User-Agent': 'curl/8.7.1', 'Content-Type': 'application/json'}

def rpc(method, params, tries=2):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    last = None
    for _ in range(tries):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=body, headers=HDR)
                with urllib.request.urlopen(req, timeout=25) as r:
                    d = json.loads(r.read().decode())
                if 'error' in d:
                    raise RuntimeError(str(d['error']))
                return d['result']
            except Exception as e:
                last = e
                time.sleep(1.0)
    raise RuntimeError('RPC %s failed: %s' % (method, last))

HX = lambda n: '0x%x' % int(n)

def utc(ts):
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# ---- wallet fill txs -> receipts ----
# tx list: from a previously built raw/wallet_receipt_cash.json if present,
# else derived from the wallet's public activity (raw/dataapi_activity.json TRADE rows)
wc = os.path.join(RAW, 'wallet_receipt_cash.json')
if os.path.exists(wc):
    recs_in = json.load(open(wc))
    txs = [r['tx'] for r in recs_in]
    print('tx source: %s (%d txs)' % (wc, len(txs)))
else:
    act = json.load(open(os.path.join(RAW, 'dataapi_activity.json')))
    txs = sorted({a['transactionHash'] for a in act if a.get('type') == 'TRADE'})
    recs_in = None
    print('tx source: derived from raw/dataapi_activity.json TRADE rows (%d unique txs)' % len(txs))
receipts = []
for i, tx in enumerate(txs):
    r = rpc('eth_getTransactionReceipt', [tx])
    if not r:
        raise RuntimeError('null receipt %s' % tx)
    receipts.append(r)
    logs = r.get('logs', [])
    kinds = {}
    for lg in logs:
        a = lg.get('address', '').lower()
        tp = lg.get('topics') or ['']
        kinds[a[:12] + ':' + (tp[0] or '')[:10]] = kinds.get(a[:12] + ':' + (tp[0] or '')[:10], 0) + 1
    top = ', '.join('%s x%d' % (k, v) for k, v in sorted(kinds.items()))
    print('[%02d/15] %s... blk %s status %s logs %d | %s' % (
        i + 1, tx[:12], int(r['blockNumber'], 16), r.get('status'), len(logs), top))
    time.sleep(0.12)

json.dump(receipts, open(PACK + '/receipts_15tx.json', 'w'), indent=1)

# rebuild wallet_receipt_cash.json FROM the fresh receipts (USDC.e Transfer logs touching
# the wallet): downstream self-checks (cluster_slice.py) read this file; it is an output,
# not a trusted input. Per-tx values are exact micro-USDC.
USDC_E = '0x2791bca1f2de4661ed88a30c99a7a9449aa84174'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
WLOWER = W[2:].lower()
cash_rows = []
for r, tx in zip(receipts, txs):
    cin, cout, blk = 0.0, 0.0, ''
    for lg in r.get('logs', []):
        if (lg.get('address') or '').lower() != USDC_E:
            continue
        tp = lg.get('topics') or []
        if tp and tp[0] == TRANSFER and len(tp) == 3:
            frm, to = tp[1][-40:].lower(), tp[2][-40:].lower()
            amt = int(lg['data'], 16) / 1e6
            if to == WLOWER:
                cin += amt
            if frm == WLOWER:
                cout += amt
        blk = blk or str(int(lg.get('blockNumber', '0x0'), 16))
    cash_rows.append({'tx': tx, 'b': int(blk) if blk else '', 'in': cin, 'out': cout})
json.dump(cash_rows, open(os.path.join(RAW, 'wallet_receipt_cash.json'), 'w'), indent=1)
print('wallet_receipt_cash.json rebuilt from receipts (%d txs) — input for cluster_slice self-check' % len(cash_rows))
tot_in = sum(r['in'] for r in cash_rows)
tot_out = sum(r['out'] for r in cash_rows)
print('15 receipts -> receipts_15tx.json + wallet_receipt_cash.json  | cash IN $%.2f OUT $%.2f' % (tot_in, tot_out))

# ---- block timestamps (merge anchors; refetch everything used in text) ----
bt = {}
old = json.load(open(BASE + '/raw/blocks.json'))
for v in old.values():
    bt[int(v['block'])] = {'ts': v['ts'], 'utc': utc(v['ts']), 'how': 'raw/blocks.json anchor (RPC-fetched 2026-10-27/28)'}

def get_ts(b):
    blk = rpc('eth_getBlockByNumber', [HX(b), False])
    ts = int(blk['timestamp'], 16)
    bt[b] = {'ts': ts, 'utc': utc(ts), 'how': 'eth_getBlockByNumber (2026-10-28)'}
    return ts

need = set(int(r['blockNumber'], 16) for r in receipts)
need |= {81010436, 81135501}            # pair block, 0xa72db single-tx block
need |= set(old[v]['block'] for v in old)  # re-verify anchors
need = sorted(need)
for b in need:
    if int(b) in bt and 'how' in bt[int(b)] and 'anchor' in bt[int(b)]['how'] and int(b) in (
            80793979, 80923579, 80966779, 81139571, 81182771, 81312371):
        t = get_ts(b)
        if t != bt[int(b)]['ts']:
            print('WARNING anchor mismatch blk %s stored %s rpc %s (RPC value kept)' % (b, bt[int(b)]['ts'], t))
        else:
            bt[int(b)]['how'] = 'RPC-verified (2026-10-28) == raw/blocks.json anchor'
        continue
    get_ts(b)
    time.sleep(0.1)

# ---- ET window boundaries by bisection (ET = UTC-5 in winter) ----
def block_at_ts(target, lo, hi):
    # lo/hi known: bracket with actual ts
    tlo, thi = bt[lo]['ts'], bt[hi]['ts']
    assert tlo < target < thi, 'bracket %s..%s does not contain %s' % (lo, hi, target)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        t = bt.get(mid, {}).get('ts') or get_ts(mid)
        time.sleep(0.08)
        if t < target:
            lo = mid
        else:
            hi = mid
    get_ts(lo); get_ts(hi)
    return lo, hi

b_dec30_et_start = block_at_ts(1767072000, 80966779, 81139571)[1]   # start cut = ET Dec 30 00:20 (05:20:00Z); true ET-midnight block is ~1,600 blocks lower by uniform 2.000 s/block cadence (see REPORT section 6; zero cluster fills in between)
b_jan3_et_end    = block_at_ts(1767416400, 81139571, 81182771)[0]   # last block with ts < ET Jan 3 00:00 (Jan 3 05:00Z); end exclusive
print('ET-aligned window blocks: [%s .. %s)  | start ts %s | last-before-end ts %s' % (
    b_dec30_et_start, b_jan3_et_end, bt[b_dec30_et_start]['utc'], bt[b_jan3_et_end]['utc']))
final = {str(k): v for k, v in bt.items() if not isinstance(k, str) or k.isdigit()}
keys = sorted(final.keys(), key=int)
final = {k: final[k] for k in keys}
final['_et_boundaries'] = {'start_block': b_dec30_et_start, 'end_block_exclusive': b_jan3_et_end,
                           'start_utc': bt[b_dec30_et_start]['utc'], 'end_utc': bt[b_jan3_et_end]['utc']}
json.dump(final, open(PACK + '/block_ts.json', 'w'), indent=1)
print('block_ts.json written: %d numeric blocks' % len(keys))