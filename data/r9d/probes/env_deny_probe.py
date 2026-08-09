"""Probe: is the file secrets_cli lands the BWS token in (~/.hermes/.env)
covered by the agent read-deny list? And what mode does it get?
"""
import os, stat, sys, tempfile
from pathlib import Path

home = tempfile.mkdtemp(prefix="hermes-home-")
os.environ["HERMES_HOME"] = home
os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")
sys.path.insert(0, "/home/user/hermes-agent")

from hermes_cli.config import get_env_path, save_env_value
from agent.file_safety import get_read_block_error, is_write_denied

save_env_value("BWS_ACCESS_TOKEN", "0.deadbeef.secret-token-value")

p = get_env_path()
print("env path      :", p)
print("exists        :", p.exists())
print("mode          :", oct(stat.S_IMODE(p.stat().st_mode)))
print("content       :", p.read_text().strip())
print("read_blocked  :", bool(get_read_block_error(str(p))))
print("write_denied  :", is_write_denied(str(p)))
print("block msg     :", (get_read_block_error(str(p)) or "")[:90])

# a project-local .env elsewhere on disk
other = Path(tempfile.mkdtemp()) / ".env"
other.write_text("X=1\n")
print("project .env read_blocked:", bool(get_read_block_error(str(other))))

# contrast with the bitwarden caches R9C examined
for rel in ("cache/bws_cache.json", "cache/bws_cache.enc.json", "cache/op_cache.json"):
    fp = Path(home) / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("{}")
    print(f"{rel:28s} read_blocked={bool(get_read_block_error(str(fp)))} write_denied={is_write_denied(str(fp))}")
