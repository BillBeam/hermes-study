import os, sys, tempfile, contextvars, concurrent.futures
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-probe-")
for v in ("HERMES_GATEWAY_SESSION","HERMES_INTERACTIVE","HERMES_SESSION_KEY","HERMES_SESSION_PLATFORM"):
    os.environ.pop(v, None)
sys.path.insert(0, "/home/user/hermes-agent")
from gateway import session_context as sc
import tools.approval as ap

def probe(tag):
    return {
        "tag": tag,
        "session_key": ap.get_current_session_key(),
        "is_gateway": ap._is_gateway_approval_context(),
        "profile": sc.get_session_env("HERMES_SESSION_PROFILE", "<none>"),
        "approved": ap._run_approval_gate(
            pattern_key="probe_pattern",
            description="probe dangerous action",
            display_target="rm -rf /home/user/probe",
            cron_deny_message="cron-deny",
            autoapprove_log_prefix="PROBE",
        )["approved"],
    }

sc.set_session_vars(platform="telegram", chat_id="42", session_key="telegram:42", profile="work")
ap.set_current_session_key("telegram:42")
print("PARENT  ", probe("parent-thread"))
ex = concurrent.futures.ThreadPoolExecutor(max_workers=2)
print("BARE    ", ex.submit(probe, "bare-submit").result())
ctx = contextvars.copy_context()
print("COPYCTX ", ex.submit(ctx.run, probe, "copy_context-submit").result())
ex.shutdown()
PY
