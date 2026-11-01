"""Reachable-state fingerprint of every loaded pynecore module (module globals, class attributes, instance dicts/slots,
function closures/defaults/attributes, lru_cache sizes, containers). Returns {path: leaf-hash}.  Used by Gate 2."""
import sys, types, hashlib, functools, collections, weakref, itertools, typing

IMM = (int, float, str, bytes, bool, type(None), complex, range)
MAXN = 400          # elements hashed per container (rest: len only)
MAXD = 9
# pynecore.transformers joins the skip (ruling 2026-10-31): its subtree is
# compile-time cache, ~10k leaves that differ cold vs warm, and walking it
# first recorded refs into it as other keys values (pynecore.types.table:Dict
# was a ref into a transformers path cold, the typing.Dict leaf warm).
SKIPMOD_PREFIX = ("pynecore.cli", "pynecore.transformers")

def _h(x): return hashlib.blake2b(x.encode() if isinstance(x, str) else x, digest_size=8).hexdigest()

def fingerprint(extra_skip_paths=(), mods=None):
    out = {}; seen = {}
    def put(path, desc): out[path] = _h(desc)
    def leafrepr(v):
        if isinstance(v, float) and v != v: return "nan"
        return f"{type(v).__name__}:{v!r}"
    def walk(v, path, d):
        if isinstance(v, IMM): put(path, leafrepr(v)); return
        if isinstance(v, (types.ModuleType,)): return
        vid = id(v)
        if vid in seen:
            put(path, "ref:" + seen[vid]); return
        seen[vid] = path
        if d > MAXD: put(path, "deep"); return
        t = type(v)
        if isinstance(v, functools._lru_cache_wrapper):
            put(path + "<lru.currsize>", str(v.cache_info().currsize)); walk(v.__wrapped__, path + "<wrapped>", d + 1); return
        if isinstance(v, (types.FunctionType, types.MethodType)):
            f = v.__func__ if isinstance(v, types.MethodType) else v
            if isinstance(v, types.MethodType): walk(v.__self__, path + "<self>", d + 1)
            if f.__closure__:
                for nm, cell in zip(f.__code__.co_freevars, f.__closure__):
                    try: c = cell.cell_contents
                    except ValueError: put(path + f"<closure:{nm}>", "empty"); continue
                    walk(c, path + f"<closure:{nm}>", d + 1)
            if f.__defaults__:
                for i, c in enumerate(f.__defaults__): walk(c, path + f"<default:{i}>", d + 1)
            if f.__kwdefaults__:
                for k, c in f.__kwdefaults__.items(): walk(c, path + f"<kwdefault:{k}>", d + 1)
            for k, c in (getattr(f, "__dict__", None) or {}).items(): walk(c, path + f"<fattr:{k}>", d + 1)
            return
        if isinstance(v, (staticmethod, classmethod)): walk(v.__func__, path, d + 1); return
        if isinstance(v, property):
            for nm in ("fget", "fset", "fdel"):
                if getattr(v, nm): walk(getattr(v, nm), path + f"<{nm}>", d + 1)
            return
        if isinstance(v, functools.partial):
            walk(v.func, path + "<func>", d + 1)
            for i, a in enumerate(v.args): walk(a, path + f"<parg{i}>", d + 1)
            for k, a in (v.keywords or {}).items(): walk(a, path + f"<pkw:{k}>", d + 1)
            return
        if isinstance(v, type):
            if not (v.__module__ or "").startswith("pynecore"): return
            for k, a in list(vars(v).items()):
                if k.startswith("__") and k not in ("__slots__",): continue
                if isinstance(a, (types.MemberDescriptorType, types.GetSetDescriptorType, types.WrapperDescriptorType, types.MethodDescriptorType)): continue
                walk(a, path + "." + k, d + 1)
            return
        if isinstance(v, (types.BuiltinFunctionType, types.GeneratorType)): return
        if isinstance(v, (dict, collections.OrderedDict, weakref.WeakValueDictionary, weakref.WeakKeyDictionary, collections.defaultdict)):
            try: items = list(v.items())
            except Exception: items = []
            put(path + "<len>", str(len(items)))
            for k, a in sorted(items[:MAXN], key=lambda kv: repr(kv[0])[:80]):
                walk(a, path + f"[{repr(k)[:60]}]", d + 1)
            return
        if isinstance(v, (list, tuple, collections.deque, set, frozenset)):
            seq = list(v)
            put(path + "<len>", str(len(seq)))
            if isinstance(v, (set, frozenset)): seq = sorted(seq, key=repr)
            for i, a in enumerate(seq[:MAXN]): walk(a, path + f"[{i}]", d + 1)
            return
        # typing alias objects (Dict, Union, Any, ...): leaves by repr, never
        # expanded — expanding them made the walk __pycache__-dependent (a cold
        # venv recorded the alias as a leaf, a warm one as six children), so an
        # inventory written cold always failed a warm check (ruling 2026-10-31)
        if isinstance(v, (typing._GenericAlias, typing._SpecialGenericAlias,
                          typing._SpecialForm)): put(path, repr(v)); return
        if isinstance(v, itertools.count): put(path, repr(v)); return
        if isinstance(v, (bytearray, memoryview)): put(path, _h(bytes(v))); return
        # generic instance
        n = 0
        dd = getattr(v, "__dict__", None)
        if isinstance(dd, dict):
            for k, a in dd.items(): walk(a, path + "." + k, d + 1); n += 1
        for cls in t.__mro__:
            sl = cls.__dict__.get("__slots__", ())
            if isinstance(sl, str): sl = (sl,)
            for k in sl:
                if k in ("__dict__", "__weakref__"): continue
                try: a = getattr(v, k)
                except AttributeError: put(path + "." + k, "unset"); continue
                walk(a, path + "." + k, d + 1); n += 1
        if n == 0:
            r = repr(v)
            put(path, f"{t.__name__}:{'<obj>' if ' at 0x' in r else r[:80]}")
    for name, mod in sorted(sys.modules.items()):
        if mod is None or not name.startswith("pynecore") or name.startswith(SKIPMOD_PREFIX): continue
        if mods and not any(name.startswith(m) for m in mods): continue
        for k, v in list(vars(mod).items()):
            if k.startswith("__") or isinstance(v, types.ModuleType): continue
            if isinstance(v, (types.FunctionType, type)) and getattr(v, "__module__", None) not in (None, name) and not isinstance(v, functools._lru_cache_wrapper):
                continue   # imported from elsewhere: walked at its home
            walk(v, f"{name}:{k}", 0)
    return out

def diff(a, b):
    keys = set(a) | set(b)
    return sorted(k for k in keys if a.get(k) != b.get(k))
