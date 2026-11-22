#!/usr/bin/env python3
"""Frame separated rebuild of the charged wallet's fills, checked against its own receipts.

Input (all checked in under code/raw):
  receipts_15tx.json      the 15 fill transaction receipts (eth_getTransactionReceipt)
  wallet_receipt_cash.json  per tx USDC.e in/out of the wallet (built by receipts_fetch.py)
  token_map.json          token id -> market slug / outcome
  dataapi_activity.json   the wallet's own public activity rows

The OrderFilled rows are decoded from the CTF Exchange logs inside those receipts, so the
check runs from a fresh checkout with no chain scan. Only rows where the charged wallet is
maker or taker are used, and only the charged wallet's figures are printed.

OrderFilled frame:
  maker gives (ma, mi), taker gives (ta, ti); assetId 0 means that side gives USDC.e.
  frame "mk" = wallet is maker on a cash leg (reproduces the receipts exactly)
  frame "tk" = wallet is taker on a cash leg (counterparty fills; phantom cash, see REPORT.md)

Writes case_wallet_stats.txt next to this file and prints the same text.
"""
import json, os, sys
from collections import defaultdict

BASE = os.environ.get('BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
RAW = BASE + '/raw'
W = '0x31a56e9e690c621ed21de08cb559e9524cdb8ed9'
EXCHANGE = '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e'   # CTF Exchange (protocol contract)
ORDER_FILLED = '0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6'
JAN31 = 'maduro-out-by-january-31-2026-318'   # the January Contract (complaint para 52)


def load(name):
    path = os.path.join(RAW, name)
    if not os.path.exists(path):
        sys.exit('missing input %s (run receipts_fetch.py / dataapi.py first)' % path)
    return json.load(open(path))


def decode_fills(receipts):
    """OrderFilled logs of the CTF Exchange -> rows in the polymarket_fetch.py schema."""
    rows = []
    for r in receipts:
        for lg in r.get('logs', []):
            tp = lg.get('topics') or []
            if (lg.get('address') or '').lower() != EXCHANGE or not tp or tp[0] != ORDER_FILLED:
                continue
            words = [int(lg['data'][2 + 64 * i: 2 + 64 * (i + 1)], 16) for i in range(5)]
            rows.append({'b': int(lg['blockNumber'], 16), 'tx': lg['transactionHash'].lower(),
                         'li': int(lg['logIndex'], 16),
                         'mk': '0x' + tp[2][-40:].lower(), 'tk': '0x' + tp[3][-40:].lower(),
                         'ma': words[0], 'ta': words[1], 'mi': words[2], 'ti': words[3]})
    return [j for j in rows if W in (j['mk'], j['tk'])]


def classify(j, tok):
    """(kind, frame, slug, outcome, cash, shares) for the charged wallet on one row."""
    if j['mk'] == W:
        frame, give_a, give_n, get_a, get_n = 'mk', j['ma'], j['mi'], j['ta'], j['ti']
    else:
        frame, give_a, give_n, get_a, get_n = 'tk', j['ta'], j['ti'], j['ma'], j['mi']
    if give_a == 0:                      # wallet's side gives USDC.e -> buy of the other token
        slug, oc = tok.get(str(get_a), {}).get('market_slug'), tok.get(str(get_a), {}).get('outcome')
        return 'buy', frame, slug, oc, give_n / 1e6, get_n / 1e6
    slug, oc = tok.get(str(give_a), {}).get('market_slug'), tok.get(str(give_a), {}).get('outcome')
    return 'sell', frame, slug, oc, get_n / 1e6, give_n / 1e6


def aggregate(rows, tok):
    a = {'rows': defaultdict(int), 'buy_sh': defaultdict(float), 'buy_usd': defaultdict(float),
         'sell_sh': defaultdict(float), 'sell_usd': defaultdict(float),
         'j31_sh': 0.0, 'j31_usd': 0.0}
    for j in rows:
        kind, frame, slug, oc, cash, sh = classify(j, tok)
        a['rows'][frame] += 1
        if kind == 'buy' and oc == 'Yes':
            a['buy_sh'][frame] += sh
            a['buy_usd'][frame] += cash
            if frame == 'mk' and slug == JAN31:
                a['j31_sh'] += sh
                a['j31_usd'] += cash
        elif kind == 'sell':
            a['sell_usd'][frame] += cash
            if oc == 'Yes':
                a['sell_sh'][frame] += sh
    return a


def emission_check(rows):
    """Each tk == wallet row must sit in a tx where the wallet has its own taker row
    (mk == wallet, tk == exchange) whose share amount equals the sum of the tk rows' shares."""
    by_tx = defaultdict(list)
    for j in rows:
        by_tx[j['tx']].append(j)
    n_tk, ok_rows, n_tx, ok_tx = 0, 0, 0, 0
    for tx, rs in by_tx.items():
        tk_rows = [j for j in rs if j['tk'] == W]
        if not tk_rows:
            continue
        own = [j for j in rs if j['mk'] == W and j['tk'] == EXCHANGE]
        own_sh = sum(j['ti'] if j['ma'] == 0 else j['mi'] for j in own)
        cp_sh = sum(j['mi'] if j['ma'] != 0 else j['ti'] for j in tk_rows)
        n_tk, n_tx = n_tk + len(tk_rows), n_tx + 1
        if own and own_sh == cp_sh:
            ok_rows, ok_tx = ok_rows + len(tk_rows), ok_tx + 1
    return n_tk, ok_rows, n_tx, ok_tx


def activity_j31(act):
    yes = [x for x in act if x.get('type') == 'TRADE' and x.get('outcome') == 'Yes'
           and str(x.get('slug', '')).startswith('maduro-out-by-january-31')]
    return sum(float(x['size']) for x in yes), sum(float(x['usdcSize']) for x in yes)


def verdict(ok):
    return 'PASS' if ok else 'FAIL'


def report(rows, tok, recs, act):
    a = aggregate(rows, tok)
    rep = ['=== charged wallet %s, %d OrderFilled rows in its 15 fill txs ===' % (W, len(rows)),
           'rows mk/tk: %d/%d' % (a['rows']['mk'], a['rows']['tk']),
           'Yes bought MK frame: %.1f sh ($%.2f) | TK frame: %.1f sh ($%.2f)' % (
               a['buy_sh']['mk'], a['buy_usd']['mk'], a['buy_sh']['tk'], a['buy_usd']['tk']),
           'Yes sold MK frame: %.1f sh | TK frame: %.1f sh' % (a['sell_sh']['mk'], a['sell_sh']['tk']),
           'sale cash MK frame: $%.2f | TK frame: $%.2f' % (a['sell_usd']['mk'], a['sell_usd']['tk'])]
    n_tk, ok_rows, n_tx, ok_tx = emission_check(rows)
    rep.append('emission rule: %d of %d tk rows in %d of %d txs -> %s' % (
        ok_rows, n_tk, ok_tx, n_tx, verdict(n_tk == ok_rows and n_tx == ok_tx)))
    per_tx = defaultdict(int)
    for j in rows:
        per_tx[j['tx']] += j['tk'] == W
    rep.append('most counterparty (tk) rows in one tx: %d' % max(per_tx.values()))
    out = sum(r['out'] for r in recs)
    inn = sum(r['in'] for r in recs)
    rep.append('SELF CHECK mk buy cash $%.2f vs receipts out $%.6f -> %s' % (
        a['buy_usd']['mk'], out, verdict(abs(a['buy_usd']['mk'] - out) < 0.01)))
    rep.append('SELF CHECK mk sell cash $%.2f vs receipts in $%.6f -> %s' % (
        a['sell_usd']['mk'], inn, verdict(abs(a['sell_usd']['mk'] - inn) < 0.01)))
    j_sh, j_usd = activity_j31(act)
    rep.append('SELF CHECK mk jan31 %.2f sh ($%.2f) vs activity %.2f sh ($%.2f) -> %s' % (
        a['j31_sh'], a['j31_usd'], j_sh, j_usd,
        verdict(abs(a['j31_sh'] - j_sh) < 0.02 and abs(a['j31_usd'] - j_usd) < 0.01)))
    return '\n'.join(rep)


def main():
    rows = decode_fills(load('receipts_15tx.json'))
    txt = report(rows, load('token_map.json'), load('wallet_receipt_cash.json'),
                 load('dataapi_activity.json'))
    open(os.path.join(BASE, 'case_wallet_stats.txt'), 'w').write(txt + '\n')
    print(txt)


if __name__ == '__main__':
    main()
