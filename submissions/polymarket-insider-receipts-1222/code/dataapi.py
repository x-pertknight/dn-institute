#!/usr/bin/env python3
"""dataapi.py - Polymarket data-api for the indicted wallet: activity + positions.
GET /activity?user=... paginated (type=TRADE,REDEEM,CONVERT...), GET /positions.
Read-only public API.
"""
import json, urllib.request, urllib.parse

W = "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9"

HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://polymarket.com",
        "Referer": "https://polymarket.com/",
        "sec-ch-ua": '"Google Chrome";v="131"',
        "sec-fetch-mode": "cors", "sec-fetch-site": "same-site"}

def get(url):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)

base = "https://data-api.polymarket.com"
items = []
offset = 0
while True:
    q = urllib.parse.urlencode({"user": W, "limit": 500, "offset": offset})
    try:
        chunk = get("%s/activity?%s" % (base, q))
    except Exception as e:
        print("activity FAIL at offset", offset, type(e).__name__, str(e)[:120])
        break
    if not chunk:
        break
    items.extend(chunk)
    offset += 500
    if offset >= 3000:
        break
print("activity items:", len(items))
from collections import Counter
print("types:", Counter(i.get("type") for i in items))
if items:
    print("first date:", items[0].get("timestamp"), " last:", items[-1].get("timestamp"))
    for i in items[:6]:
        print(json.dumps(i)[:240])
    json.dump(items, open("raw/dataapi_activity.json", "w"))
for ep in ("value",):
    try:
        print(ep, json.dumps(get("%s/value?%s" % (base, urllib.parse.urlencode({"user": W}))))[:300])
    except Exception as e:
        print(ep, "FAIL", str(e)[:100])
try:
    pos = get("%s/positions?%s" % (base, urllib.parse.urlencode({"user": W})))
    print("positions:", len(pos))
    json.dump(pos, open("raw/dataapi_positions.json", "w"))
    for p in pos[:8]:
        print(json.dumps({k: p.get(k) for k in ("title", "outcome", "size", "avgPrice", "curPrice", "redeemable")})[:200])
except Exception as e:
    print("positions FAIL", str(e)[:120])