"""ADVERSARIAL INJECTION (P7). Not part of PyneCore. Per-run state in five hiding places, selected by env ADV."""
import os
class Counter:            # A: class attribute counter
    n = 0
class Latent:             # E: class attribute never read
    n = 0
def _mk():                # B: closure-captured dict
    cache = {}
    def memo(key, val):
        if key in cache: return cache[key]
        cache[key] = val
        return val
    return memo
_memo = _mk()
_box = (0, {})            # C: mutable dict inside a module-level tuple (lowercase name)
ADV_CACHE = {}            # D: ALLCAPS module-level dict
def _memo_in(d, key, val):
    if key in d: return d[key]
    d[key] = val
    return val
def hook(value, bi, length):
    m = os.environ.get("ADV", "")
    key = (bi, length)
    if m == "A":
        Counter.n += 1
        return value + Counter.n * 1e-9
    if m == "B": return _memo(key, value)
    if m == "C": return _memo_in(_box[1], key, value)
    if m == "D": return _memo_in(ADV_CACHE, key, value)
    if m == "E":
        Latent.n += 1
    return value
