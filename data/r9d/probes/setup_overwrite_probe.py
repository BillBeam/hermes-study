"""Probe: does `hermes secrets bitwarden setup` overwrite a WORKING token in
.env with a bad paste before the token has been validated?

Contrast with cmd_token, whose docstring promises "only then persists it to
.env — so a bad paste never bricks the working token".
"""
import argparse, os, sys, tempfile, types
from pathlib import Path

home = tempfile.mkdtemp(prefix="hermes-home-")
os.environ["HERMES_HOME"] = home
os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")
sys.path.insert(0, "/home/user/hermes-agent")

from hermes_cli.config import get_env_path, save_env_value
import hermes_cli.secrets_cli as sc

# 1) a working token is already on disk
save_env_value("BWS_ACCESS_TOKEN", "0.GOOD-WORKING-TOKEN")
print("before        :", get_env_path().read_text().strip())

# 2) stub out everything that would touch the network / the bws binary
sc.bw.find_bws = lambda install_if_missing=False: Path("/usr/bin/bws")
sc.bw.install_bws = lambda force=False: Path("/usr/bin/bws")
sc._bws_version = lambda _p: "1.0.0"


def _fail_fetch(**kw):
    raise RuntimeError("401 Unauthorized: access token is invalid")


sc.bw.fetch_bitwarden_secrets = _fail_fetch

args = argparse.Namespace(
    access_token="0.BAD-PASTED-TOKEN",
    project_id="11111111-2222-3333-4444-555555555555",
    server_url="https://vault.bitwarden.eu",
)
rc = sc.cmd_setup(args)
print("cmd_setup rc  :", rc)
print("after         :", get_env_path().read_text().strip())
print("good token still on disk:", "GOOD-WORKING-TOKEN" in get_env_path().read_text())
