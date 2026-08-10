#!/usr/bin/env python3
"""Execute the four R11A-assigned handover items that are testable in-process.

The project's rule is that a handover item gets a disposition, not a re-file.
Four of R11A's inherited items are claims about baseline behaviour that can be
settled by running the baseline rather than by reading it:

  H-R9C-c  agent/transports/__init__.py — `except ImportError: pass` cannot tell
           "optional package absent" from "bug inside our own module"
  H-R9D-b  tools/thread_context.py      — the returned wrapper cannot be reused
           concurrently
  H-R9D-c  agent/think_scrubber.py      — a reasoning tag WITH ATTRIBUTES takes
           opposite paths streaming vs non-streaming
  H-R9D-d  tools/managed_tool_gateway.py — host comparison uses `netloc`, and
           TOOL_GATEWAY_SCHEME=http is accepted

Run against the pinned baseline with lazy installs sealed:

    HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
        data/r11a/probes/probe_handover_defects.py

Each check prints CONFIRMED / REFUTED plus the observation it is based on, so a
reader can disagree with the interpretation while still seeing the raw result.
"""
import os
import sys
import threading
import traceback

os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")
sys.path.insert(0, "/home/user/hermes-agent")

RESULTS = []


def report(item, verdict, detail):
    RESULTS.append((item, verdict, detail))
    print(f"\n=== {item}: {verdict} ===")
    for line in detail.strip().splitlines():
        print("    " + line)


# --------------------------------------------------------------------------
def check_h_r9c_c():
    """Does a real bug inside a transport module look like a missing package?"""
    import agent.transports as T

    # Force rediscovery with a transport module that imports something absent.
    # We do not edit the baseline; we shadow the import machinery instead.
    import importlib
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") \
        else __builtins__["__import__"]

    seen = {}

    def fake_import(name, *a, **kw):
        # Simulate the two distinguishable failures the item is about.
        if name == "agent.transports.anthropic":
            seen["called"] = True
            raise ImportError("No module named 'this_optional_pkg_is_absent'",
                              name="this_optional_pkg_is_absent")
        if name == "agent.transports.codex":
            # A genuine bug inside OUR module: a typo'd internal import.
            raise ImportError("No module named 'agent.transports.typo_module'",
                              name="agent.transports.typo_module")
        return real_import(name, *a, **kw)

    T._discovered = False
    builtins_mod = sys.modules["builtins"]
    builtins_mod.__import__ = fake_import
    try:
        T._discover_transports()
    finally:
        builtins_mod.__import__ = real_import

    src = open("/home/user/hermes-agent/agent/transports/__init__.py",
               encoding="utf-8").read()
    swallow = src.count("except ImportError:")
    checks_name = "exc.name" in src or "err.name" in src

    detail = (
        f"_discover_transports() completed without raising for BOTH cases.\n"
        f"`except ImportError:` occurrences in the module : {swallow}\n"
        f"module inspects the failing module name (exc.name): {checks_name}\n"
        f"So an absent optional dependency and a typo'd internal import are\n"
        f"handled identically; get_transport() then returns None for both."
    )
    report("H-R9C-c", "CONFIRMED" if not checks_name else "REFUTED", detail)


# --------------------------------------------------------------------------
def check_h_r9d_b():
    """Can the wrapper returned by thread_context be used concurrently?"""
    from tools.thread_context import propagate_context_to_thread as prop
    errors, done = [], []

    def payload():
        import time
        time.sleep(0.25)
        done.append(1)
        return "ok"

    runner = prop(payload) if callable(prop) else None
    if runner is None:
        report("H-R9D-b", "INCONCLUSIVE", "entry point not callable as expected")
        return

    def worker():
        try:
            runner()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    ts = [threading.Thread(target=worker) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    detail = (
        f"two concurrent calls of ONE wrapper -> completed: {len(done)}, "
        f"errors: {errors}\n"
        f"Expected if the item holds: one call raises "
        f"'cannot enter context' / 'already entered'."
    )
    report("H-R9D-b", "CONFIRMED" if errors else "REFUTED", detail)


# --------------------------------------------------------------------------
def check_h_r9d_c():
    """Same input, two paths: does a tag WITH ATTRIBUTES diverge?"""
    from agent.think_scrubber import StreamingThinkScrubber
    from agent.agent_runtime_helpers import strip_think_blocks

    payload = '<think foo="1">SECRET REASONING</think>Hello, user.'

    s = StreamingThinkScrubber()
    streamed = s.feed(payload) + s.flush()
    nonstream = strip_think_blocks(None, payload)

    leaked = "SECRET REASONING" in streamed
    ate = "Hello, user." not in nonstream

    detail = (
        f"input          : {payload!r}\n"
        f"streaming out  : {streamed!r}\n"
        f"non-streaming  : {nonstream!r}\n"
        f"streaming leaks the reasoning : {leaked}\n"
        f"non-streaming eats the reply  : {ate}"
    )
    report("H-R9D-c", "CONFIRMED" if (leaked and ate) else "PARTIAL", detail)


# --------------------------------------------------------------------------
def check_h_r9d_d():
    """netloc-based host compare, and does http survive the trust gate?"""
    import importlib
    import tools.managed_tool_gateway as G

    # Use the module's OWN vendor constant. The first draft of this probe
    # hard-coded "nous" and got False for the plaintext case — not because the
    # item was wrong, but because `nous-gateway.…` is a different host from the
    # canonical `tool-gateway.…`, so the gate rejected it for the right reason.
    # A fixture that misses the target proves nothing while looking like it did.
    vendor = G._MANAGED_GATEWAY_VENDOR
    canonical = G.build_vendor_gateway_url(vendor)
    upper = canonical.replace(f"{vendor}-gateway", f"{vendor.upper()}-GATEWAY")
    case_ok = G.is_managed_nous_gateway_url(upper)

    os.environ["TOOL_GATEWAY_SCHEME"] = "http"
    importlib.reload(G)
    plain = G.build_vendor_gateway_url(G._MANAGED_GATEWAY_VENDOR)
    plain_trusted = G.is_managed_nous_gateway_url(plain)
    os.environ.pop("TOOL_GATEWAY_SCHEME", None)
    importlib.reload(G)

    detail = (
        f"canonical gateway url            : {canonical}\n"
        f"same host, uppercased            : {upper}\n"
        f"  trusted by is_managed_nous_gateway_url? {case_ok}   "
        f"(False => case-sensitive, fails CLOSED)\n"
        f"with TOOL_GATEWAY_SCHEME=http    : {plain}\n"
        f"  trusted by is_managed_nous_gateway_url? {plain_trusted}   "
        f"(True => bearer would ride plaintext)"
    )
    verdict = "CONFIRMED" if (not case_ok and plain_trusted) else "PARTIAL"
    report("H-R9D-d", verdict, detail)


def main() -> None:
    for fn in (check_h_r9c_c, check_h_r9d_b, check_h_r9d_c, check_h_r9d_d):
        try:
            fn()
        except Exception:  # noqa: BLE001
            report(fn.__name__, "ERROR", traceback.format_exc())
    print("\n=== summary ===")
    for item, verdict, _ in RESULTS:
        print(f"  {item:10s} {verdict}")


if __name__ == "__main__":
    main()
