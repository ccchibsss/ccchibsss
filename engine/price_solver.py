"""Port of index.html solveEcoInteger; keep behavior aligned, including scans."""
import math

CAP = 10_000_000

def js_round(x):
    return math.floor(x + 0.5)


def solve_integer(initial, metric):
    cache = {}
    def evaluate(price):
        key = max(0, js_round(price))
        if key not in cache:
            value = metric(key)
            cache[key] = value if math.isfinite(value) else -math.inf
        return cache[key]
    start = max(0, min(CAP, js_round(initial)))
    def local_root(x):
        fx = evaluate(x)
        if fx >= 0 and (x == 0 or evaluate(x - 1) < 0): return x
        if fx < 0 and x < CAP and evaluate(x + 1) >= 0: return x + 1
        return None
    def first_crossing(lo, hi):
        if evaluate(lo) >= 0: return lo
        if evaluate(hi) < 0: return None
        width = hi - lo
        step = 25000 if width > 1000000 else 2500 if width > 100000 else 250 if width > 10000 else 25 if width > 1000 else 1
        prev = lo
        p = lo + step
        while True:
            pp = min(p, hi)
            if evaluate(pp) >= 0:
                return pp if pp - prev <= 1 else first_crossing(prev, pp)
            prev = pp
            if pp >= hi: return None
            p += step
    def scan_band(lo, hi):
        if evaluate(lo) >= 0: return lo
        width = hi - lo
        if width <= 0: return None
        step = 25000 if width > 1000000 else 2500 if width > 100000 else 250 if width > 10000 else 25 if width > 1000 else 4 if width > 256 else 1
        prev = lo
        p = lo + step
        while True:
            pp = min(p, hi)
            if evaluate(pp) >= 0: return first_crossing(prev, pp)
            prev = pp
            if pp >= hi: return None
            p += step
    root = local_root(start)
    if root is not None: return root
    if evaluate(start) < 0:
        prev = 0
        for gp in (0, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, CAP):
            if gp == start:
                prev = gp
                continue
            root = scan_band(prev, gp)
            if root is not None: return root
            prev = gp
    f_start = evaluate(start)
    second = min(CAP, max(start + 32, js_round(start * 1.2 + 1))) if f_start < 0 else max(0, js_round(start * 0.8))
    if second != start:
        slope = (evaluate(second) - f_start) / (second - start)
        if slope > 0 and math.isfinite(slope):
            candidate = max(0, min(CAP, js_round(start - f_start / slope)))
            if candidate != start and candidate != second:
                root = local_root(candidate)
                if root is not None: return root
    step = max(16, js_round(abs(start) * 0.25))
    if evaluate(start) >= 0:
        if start == 0 or evaluate(start - 1) < 0: return start
        hi, lo = start, max(0, start - step)
        while evaluate(lo) >= 0:
            hi = lo
            if lo == 0: return 0
            step *= 2
            lo = max(0, lo - step)
    else:
        lo, hi = start, min(CAP, start + step)
        guard = 0
        while evaluate(hi) < 0 and hi < CAP and guard < 40:
            guard += 1
            lo = hi
            step *= 2
            hi = min(CAP, lo + step)
        if evaluate(hi) < 0:
            for lo, hi in ((0, 10000), (10000, 100000), (100000, 1000000), (1000000, CAP)):
                root = scan_band(lo, hi)
                if root is not None: return root
            return CAP
    root = first_crossing(lo, hi)
    return hi if root is None else root


def stable_floor(guess, metric, discontinuity=0):
    edge = math.floor(discontinuity)
    if edge <= 0: return solve_integer(guess, metric)
    if metric(edge + 1) < 0: return solve_integer(edge + 1, metric)
    if metric(edge) < 0: return edge + 1
    if metric(0) >= 0: return 0
    lo, hi = 0, edge
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if metric(mid) >= 0: hi = mid
        else: lo = mid
    return hi
