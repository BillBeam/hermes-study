#!/usr/bin/env python3
"""R10B slice C probe: the billing refusal-code seam, end to end.

Three closed lists that must line up:
  1. KnownBillingRefusalCode      (apps/shared/src/billing-types.ts)  — the wire enum
  2. BILLING_REFUSAL_POLICY keys  (apps/shared/src/billing-policy.ts) — recovery policy,
     typed as Record<KnownBillingRefusalCode, …> so it is compiler-exhaustive
  3. resolveRefusal() switch arms (apps/desktop/.../billing/errors.ts) — desktop copy;
     NOT compiler-exhaustive (a plain switch with a default), so a code can silently
     fall through to the generic "Billing request failed." presentation.

Also lists the gateway JSON-RPC billing/subscription methods declared in
tui_gateway/methods_session.py vs the ones the desktop BillingApi actually calls.

Usage: python3 data/r10b/probes/probe_c_billing_codes.py /home/user/hermes-agent
"""
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")

types_ts = (repo / "apps/shared/src/billing-types.ts").read_text()
policy_ts = (repo / "apps/shared/src/billing-policy.ts").read_text()
errors_ts = (repo / "apps/desktop/src/app/settings/billing/errors.ts").read_text()
api_ts = (repo / "apps/desktop/src/app/settings/billing/api.ts").read_text()
py = (repo / "tui_gateway/methods_session.py").read_text()

known = re.findall(r"^\s*\|\s*'([a-z_]+)'$", types_ts.split("export type KnownBillingRefusalCode =", 1)[1].split("\n\n", 1)[0], re.M)
policy = re.findall(r"^\s{2}([a-z_]+):\s*\{", policy_ts.split("BILLING_REFUSAL_POLICY", 1)[1], re.M)
arms = re.findall(r"case '([a-z_]+)':", errors_ts)
recovery = dict(re.findall(r"^\s{2}([a-z_]+):\s*\{\s*recovery:\s*'([a-z_]+)'", policy_ts.split("BILLING_REFUSAL_POLICY", 1)[1], re.M))

print(f"KnownBillingRefusalCode  : {len(known)}")
print(f"BILLING_REFUSAL_POLICY   : {len(policy)}   identical set: {set(known) == set(policy)}")
print(f"resolveRefusal switch    : {len(arms)} arms (incl. non-wire 'timeout'/'transport')")
print()
print(f"{'code':<32}{'policy.recovery':<18}{'desktop copy?'}")
for c in known:
    print(f"  {c:<30}{recovery.get(c,'?'):<18}{'yes' if c in arms else 'NO -> generic default'}")
missing = [c for c in known if c not in arms]
extra = [c for c in arms if c not in known]
print(f"\nno bespoke desktop copy: {len(missing)} -> {missing}")
print(f"desktop-only arms      : {extra}")

print("\n=== gateway billing/subscription JSON-RPC ===")
declared = re.findall(r'@method\("((?:billing|subscription)\.[a-z_]+)"\)', py)
called = sorted(set(re.findall(r"requestGateway,\s*'((?:billing|subscription)\.[a-z_]+)'", api_ts)))
print(f"declared in tui_gateway/methods_session.py: {len(declared)} -> {declared}")
print(f"called by desktop BillingApi              : {len(called)} -> {called}")
print(f"declared but NOT called by desktop        : {[m for m in declared if m not in called]}")
