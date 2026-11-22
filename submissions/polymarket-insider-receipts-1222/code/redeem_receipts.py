#!/usr/bin/env python3
"""Fetch RAW on-chain receipts for the wallet's redemption txs found in the Polymarket
data-api activity (type REDEEM/CONVERT) -> raw/receipts_redeems.json; extend block_ts.json
with their blocks (timestamp via eth_getBlockByNumber).
"""
import json, os, time, datetime, urllib.request

BASE = os.environ.get('BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
RAW = BASE + '/raw'
ENDPOINTS = ['https://polygon.drpc.org', 'https://polygon-bor-rpc.publicnode.com', 'https://polygon.1rpc.io']
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

def utc(ts):
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

items = json.load(open(BASE + '/raw/dataapi_activity.json'))
reds = [i for i in items if i.get('type') in ('REDEEM', 'CONVERT')]
print('REDEEM/CONVERT activity rows:', len(reds))
for i in reds:
    print(json.dumps(i)[:300])

path = RAW + '/receipts_redeems.json'
existing = json.load(open(path)) if os.path.exists(path) else []
have = set(r.get('transactionHash') for r in existing)
for i in reds:
    tx = i.get('transactionHash')
    if not tx or tx in have:
        continue
    r = rpc('eth_getTransactionReceipt', [tx])
    if not r:
        print('SKIP null receipt', tx)
        continue
    existing.append(r)
    b = int(r['blockNumber'], 16)
    blk = rpc('eth_getBlockByNumber', ['0x%x' % b, False])
    print('redeem tx %s... blk %d status %s logs %d ts %s'
          % (tx[:14], b, r.get('status'), len(r.get('logs', [])), utc(int(blk['timestamp'], 16))))
    time.sleep(0.15)

json.dump(existing, open(path, 'w'), indent=1)

if os.path.exists(RAW + '/block_ts.json'):
    bts = json.load(open(RAW + '/block_ts.json'))
    for r in existing:
        b = int(r['blockNumber'], 16)
        if str(b) not in bts:
            blk = rpc('eth_getBlockByNumber', ['0x%x' % b, False])
            ts = int(blk['timestamp'], 16)
            bts[str(b)] = {'ts': ts, 'utc': utc(ts), 'how': 'eth_getBlockByNumber (2026-10-28)'}
    json.dump(bts, open(RAW + '/block_ts.json', 'w'), indent=1)
    print('block_ts.json: %d numeric blocks' % len([k for k in bts if str(k).isdigit()]))
print('receipts_redeems.json: %d receipts' % len(existing))