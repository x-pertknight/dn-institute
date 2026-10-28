#!/usr/bin/env python3
"""Inca challenge #1222 rebuild — Polymarket OrderFilled fetch pipeline.

Public unauthenticated endpoints only. No API keys.

Subcommands:
  --meta              resolve the 4 events / markets / token ids via Gamma API
                      -> raw/gamma_events.json, raw/markets.json, raw/token_map.json
  --blocks            binary-search block boundaries for the scan window
                      -> raw/blocks.json
  --probe             RPC health probe + eth_getLogs format support check
  --scan START END    scan blocks [START, END) for V1 OrderFilled/OrdersMatched,
                      checkpoint/resume via raw/scan_state.json,
                      appends matched rows to raw/fills.jsonl
  --ts                fetch timestamps for every block referenced in fills.jsonl
                      (batched eth_getBlockByNumber) -> raw/block_ts_cache.json

Pacing: one in-flight request per RPC, per-RPC minimum gap, cooldowns on
429/403/quota errors, 100-block getLogs chunks on drpc (the workload of the
original Oct 23 run).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
os.makedirs(RAW, exist_ok=True)

# ---------------------------------------------------------------- constants
GAMMA = "https://gamma-api.polymarket.com"

# Event slugs under investigation (from the challenge / CFTC Release 9217-26).
EVENT_SLUGS = [
    "maduro-out-in-2025",
    "will-the-us-invade-venezuela-in-2025",
    "us-forces-in-venezuela-by",
    "trump-invokes-war-powers-against-venezuela-by",
]

# Scan window (UTC) — superset of the CFTC bet window; matches the original
# run's P0+P1+P2 coverage (Dec 26 2025 -> Jan 7 2026).
WINDOW_START_UTC = datetime(2025, 12, 26, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END_UTC = datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc)

sys.path.insert(0, HERE)
from keccak_lib import topic0, ORDER_FILLED_V1_SIG, ORDERS_MATCHED_V1_SIG  # noqa: E402

TOPIC_ORDER_FILLED = topic0(ORDER_FILLED_V1_SIG)
TOPIC_ORDERS_MATCHED = topic0(ORDERS_MATCHED_V1_SIG)

RPC_POOL = [
    {"url": "https://polygon.drpc.org", "chunk": 100, "gap": 0.30, "cd": 45.0},
    {"url": "https://polygon-bor-rpc.publicnode.com", "chunk": 50, "gap": 0.15, "cd": 45.0},
    {"url": "https://1rpc.io/matic", "chunk": 100, "gap": 0.30, "cd": 90.0},
    {"url": "https://polygon.rpc.subsquid.io", "chunk": 300, "gap": 0.30, "cd": 60.0},
]


def log(msg):
    print("[%s] %s" % (datetime.now(timezone.utc).strftime("%H:%M:%S"), msg), flush=True)


# ---------------------------------------------------------------- HTTP layer
def rpc_post(url, payload, timeout=30):
    """POST a JSON-RPC payload. Returns (result, error_string)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            # some public RPCs sit behind Cloudflare and 403 (error 1010) bare clients
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()[:300]
        except Exception:
            detail = ""
        return None, "HTTP %d %s" % (e.code, detail)
    except Exception as e:  # network/timeout
        return None, "NET %s" % str(e)[:200]
    if "error" in body and body["error"]:
        err = body["error"]
        return None, "RPC %s %s" % (err.get("code"), str(err.get("message"))[:250])
    return body.get("result"), None


def rpc_call(url, method, params, timeout=30):
    return rpc_post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout)


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "inca-1222-rebuild/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------- --meta
def load_markets():
    """Resolve the 4 events and every market live during the scan window."""
    events_out = []
    for slug in EVENT_SLUGS:
        url = "%s/events?slug=%s" % (GAMMA, slug)
        data = http_get_json(url)
        if not data:
            raise SystemExit("gamma: no event for slug %s" % slug)
        ev = data[0]
        events_out.append(ev)
        log("event %s: %d market(s)" % (slug, len(ev.get("markets", []))))
        for m in ev.get("markets", []):
            log("  market %-70s negRisk=%s created=%s closed=%s vol=%.2f" % (
                m.get("slug"), m.get("negRisk"), m.get("createdAt"),
                m.get("closedTime") or m.get("endDate"), float(m.get("volume") or 0)))
    with open(os.path.join(RAW, "gamma_events.json"), "w") as f:
        json.dump(events_out, f, indent=1)

    def parse_ts(s):
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

    markets = []
    for ev in events_out:
        for m in ev.get("markets", []):
            end = parse_ts(m.get("closedTime") or m.get("endDate"))
            start = parse_ts(m.get("startDate") or m.get("createdAt"))
            # live at any point during the scan window?
            if end and start and start < WINDOW_END_UTC and end > WINDOW_START_UTC:
                markets.append(m)
            elif end is None and start and start < WINDOW_END_UTC:
                markets.append(m)
    with open(os.path.join(RAW, "markets.json"), "w") as f:
        json.dump(markets, f, indent=1)

    token_map = {}
    for m in markets:
        ids_raw = m.get("clobTokenIds")
        if isinstance(ids_raw, str):
            ids = json.loads(ids_raw)
        else:
            ids = ids_raw or []
        outcomes = m.get("outcomes")
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        for tid, outcome in zip(ids, outcomes or ["YES", "NO"]):
            token_map[str(int(tid))] = {
                "market_slug": m["slug"],
                "event_slug": m.get("slug", "").split(m.get("slug", ""))[0] or None,
                "outcome": outcome,
                "condition_id": m.get("conditionId"),
            }
    for k, v in token_map.items():
        v.pop("event_slug", None)
    with open(os.path.join(RAW, "token_map.json"), "w") as f:
        json.dump(token_map, f, indent=1)
    log("markets live in window: %d; token ids: %d" % (len(markets), len(token_map)))
    for m in markets:
        log("  live: %s" % m["slug"])


# ---------------------------------------------------------------- --blocks
def block_ts(url, block):
    res, err = rpc_call(url, "eth_getBlockByNumber", [hex(block), False])
    if err or res is None:
        raise RuntimeError("block fetch failed: %s" % err)
    return int(res["timestamp"], 16)


def find_block_for_ts(url, target_ts):
    """Smallest block number whose timestamp >= target_ts."""
    res, err = rpc_call(url, "eth_blockNumber", [])
    if err:
        raise RuntimeError(err)
    tip = int(res, 16)
    lo, hi = 70_000_000, tip  # Dec 2025 blocks are ~80.8M
    # invariant: ts(lo) < target <= ts(hi)
    if block_ts(url, hi) < target_ts:
        raise RuntimeError("tip block older than target ts?")
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if block_ts(url, mid) < target_ts:
            lo = mid
        else:
            hi = mid
    return hi


def cmd_blocks():
    url = RPC_POOL[0]["url"]
    targets = {
        "scan_start_dec26": WINDOW_START_UTC,
        "dec29": datetime(2025, 12, 29, 0, 0, 0, tzinfo=timezone.utc),
        "cftc_start_dec30": datetime(2025, 12, 30, 0, 0, 0, tzinfo=timezone.utc),
        "cftc_end_jan3": datetime(2026, 1, 3, 0, 0, 0, tzinfo=timezone.utc),
        "p0_end_jan4": datetime(2026, 1, 4, 0, 0, 0, tzinfo=timezone.utc),
        "scan_end_jan7": WINDOW_END_UTC,
    }
    out = {}
    for name, dt in targets.items():
        b = find_block_for_ts(url, int(dt.timestamp()))
        out[name] = {"block": b, "ts": int(dt.timestamp()), "utc": dt.isoformat()}
        log("%s -> block %d (ts %d = %s)" % (name, b, block_ts(url, b),
                                             datetime.fromtimestamp(block_ts(url, b), timezone.utc).isoformat()))
    with open(os.path.join(RAW, "blocks.json"), "w") as f:
        json.dump(out, f, indent=1)


# ---------------------------------------------------------------- --probe
def cmd_probe():
    for r in RPC_POOL:
        res, err = rpc_call(r["url"], "eth_blockNumber", [], timeout=15)
        tip = int(res, 16) if res else None
        log("%-45s blockNumber %s %s" % (r["url"], tip, ("ERR " + err) if err else ""))
    url = RPC_POOL[0]["url"]
    # format A: topic0 list (OrderFilled OR OrdersMatched)
    res, err = rpc_call(url, "eth_getLogs", [{
        "fromBlock": hex(80_966_779), "toBlock": hex(80_966_878),
        "topics": [[TOPIC_ORDER_FILLED, TOPIC_ORDERS_MATCHED]],
    }])
    if err:
        log("topic0-list format NOT supported: %s" % err)
    else:
        log("topic0-list format OK: %d logs over 100 blocks" % len(res))
        addrs = {}
        for lg in res:
            addrs[lg["address"]] = addrs.get(lg["address"], 0) + 1
        for a, n in sorted(addrs.items(), key=lambda kv: -kv[1]):
            log("  emitter %s: %d" % (a, n))
    # sanity: our token should appear quickly from the known window
    with open(os.path.join(RAW, "token_map.json")) as f:
        tm = json.load(f)
    res, err = rpc_call(url, "eth_getLogs", [{
        "fromBlock": hex(80_966_779), "toBlock": hex(80_967_078),
        "topics": [[TOPIC_ORDER_FILLED, TOPIC_ORDERS_MATCHED]],
    }])
    if res is not None:
        hits = 0
        for lg in res:
            w = lg["data"][2:]
            words = [w[64 * i:64 * i + 64] for i in range(len(w) // 64)]
            ma, ta = int(words[0], 16), int(words[1], 16)
            if str(ma) in tm or str(ta) in tm:
                hits += 1
        log("token-map hits in first 300 blocks of P0: %d" % hits)


# ---------------------------------------------------------------- --scan
def decode_and_filter(logs, token_map, out_of, out_om):
    kept = 0
    for lg in logs:
        topics = lg["topics"]
        t0 = topics[0].lower()
        w = lg["data"][2:]
        words = [w[64 * i:64 * i + 64] for i in range(len(w) // 64)]
        ma = int(words[0], 16)
        ta = int(words[1], 16)
        if str(ma) not in token_map and str(ta) not in token_map:
            continue
        row = {
            "k": "OF" if t0 == TOPIC_ORDER_FILLED else "OM",
            "b": int(lg["blockNumber"], 16),
            "tx": lg["transactionHash"],
            "li": int(lg["logIndex"], 16),
            "oh": topics[1],
            "mk": "0x" + topics[2][-40:],
            "ma": ma, "ta": ta,
            "mi": int(words[2], 16), "ti": int(words[3], 16),
            "em": lg["address"].lower(),
        }
        if row["k"] == "OF":
            row["tk"] = "0x" + topics[3][-40:]
            row["f"] = int(words[4], 16)
            out_of.append(json.dumps(row, separators=(",", ":")))
        else:
            row["tk"] = None
            row["f"] = 0
            out_om.append(json.dumps(row, separators=(",", ":")))
        kept += 1
    return kept


class State:
    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)
        else:
            self.data = {"ranges": {}}

    def get_pos(self, key):
        return self.data["ranges"].get(key)

    def set_pos(self, key, pos):
        self.data["ranges"][key] = pos
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)


def cmd_scan(start, end):
    with open(os.path.join(RAW, "token_map.json")) as f:
        token_map = json.load(f)
    state_path = os.path.join(RAW, "scan_state.json")
    state = State(state_path)
    key = "%d-%d" % (start, end)
    pos = state.get_pos(key)
    if pos is None:
        pos = start
        state.set_pos(key, pos)
    log("scan %s: resuming at %d (coverage %.1f%%)" % (
        key, pos, 100.0 * (pos - start) / (end - start)))

    fills_path = os.path.join(RAW, "fills.jsonl")
    om_path = os.path.join(RAW, "orders_matched.jsonl")
    fo = open(fills_path, "a")
    mo = open(om_path, "a")

    rpcs = []
    for r in RPC_POOL:
        rpcs.append(dict(r, next_ok=0.0, fails=0, ok=0))
    t0 = time.time()
    scanned0 = pos
    n_chunks = 0
    while pos < end:
        now = time.time()
        rpc = None
        for r in rpcs:
            if r["next_ok"] <= now:
                rpc = r
                break
        if rpc is None:
            time.sleep(0.05)
            continue
        chunk = min(rpc["chunk"], end - pos)
        res, err = rpc_call(rpc["url"], "eth_getLogs", [{
            "fromBlock": hex(pos), "toBlock": hex(pos + chunk - 1),
            "topics": [[TOPIC_ORDER_FILLED, TOPIC_ORDERS_MATCHED]],
        }])
        if err:
            rpc["fails"] += 1
            cd = rpc["cd"]
            low = err.lower()
            if "quota" in low or "-32001" in low:
                cd = 1800.0
            elif "429" in low or "403" in low:
                cd = rpc["cd"] * min(4, 1 + rpc["fails"])
            log("ERR %s pos=%d: %s (cooldown %.0fs)" % (rpc["url"], pos, err, cd))
            rpc["next_ok"] = time.time() + cd
            continue
        rpc["fails"] = 0
        rpc["ok"] += 1
        rpc["next_ok"] = time.time() + rpc["gap"]
        rows_of, rows_om = [], []
        kept = decode_and_filter(res, token_map, rows_of, rows_om)
        for s in rows_of:
            fo.write(s + "\n")
        for s in rows_om:
            mo.write(s + "\n")
        fo.flush()
        mo.flush()
        os.fsync(fo.fileno())
        pos += chunk
        state.set_pos(key, pos)
        n_chunks += 1
        if n_chunks % 25 == 0:
            el = time.time() - t0
            rate = (pos - scanned0) / max(el, 0.001)
            eta = (end - pos) / max(rate, 1e-9)
            log("pos=%d (%.1f%%) kept=%d rate=%.0f blk/s eta=%.0fs rpc_ok=%s" % (
                pos, 100.0 * (pos - start) / (end - start), kept, rate, eta,
                ",".join("%s:%d" % (r["url"].split("//")[1].split("/")[0], r["ok"]) for r in rpcs)))
    fo.close()
    mo.close()
    log("scan COMPLETE %s: %d..%d, chunks=%d, %.0fs" % (key, start, end, n_chunks, time.time() - t0))


# ---------------------------------------------------------------- --ts
def cmd_ts():
    fills_path = os.path.join(RAW, "fills.jsonl")
    cache_path = os.path.join(RAW, "block_ts_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
    need = set()
    with open(fills_path) as f:
        for line in f:
            row = json.loads(line)
            b = str(row["b"])
            if b not in cache:
                need.add(row["b"])
    om_path = os.path.join(RAW, "orders_matched.jsonl")
    if os.path.exists(om_path):
        with open(om_path) as f:
            for line in f:
                row = json.loads(line)
                if str(row["b"]) not in cache:
                    need.add(row["b"])
    need = sorted(need)
    log("blocks needing timestamps: %d (cached: %d)" % (len(need), len(cache)))
    url = RPC_POOL[0]["url"]
    B = 10
    for i in range(0, len(need), B):
        batch = need[i:i + B]
        payload = [{"jsonrpc": "2.0", "id": j, "method": "eth_getBlockByNumber",
                    "params": [hex(b), False]} for j, b in enumerate(batch)]
        res, err = rpc_post(url, payload, timeout=60)
        if err:
            log("batch err at %d: %s; retrying once" % (batch[0], err))
            time.sleep(5)
            res, err = rpc_post(url, payload, timeout=60)
            if err:
                raise RuntimeError(err)
        for item in res:
            blk = int(item["result"]["number"], 16)
            cache[str(blk)] = int(item["result"]["timestamp"], 16)
        if (i // B) % 50 == 0:
            with open(cache_path + ".tmp", "w") as f:
                json.dump(cache, f)
            os.replace(cache_path + ".tmp", cache_path)
            log("ts progress: %d/%d" % (i + B, len(need)))
        time.sleep(0.15)
    with open(cache_path + ".tmp", "w") as f:
        json.dump(cache, f)
    os.replace(cache_path + ".tmp", cache_path)
    log("timestamps cached: %d" % len(cache))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--blocks", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--scan", nargs=2, type=int, metavar=("START", "END"))
    ap.add_argument("--ts", action="store_true")
    args = ap.parse_args()
    if args.meta:
        load_markets()
    if args.blocks:
        cmd_blocks()
    if args.probe:
        cmd_probe()
    if args.scan:
        cmd_scan(args.scan[0], args.scan[1])
    if args.ts:
        cmd_ts()


if __name__ == "__main__":
    main()