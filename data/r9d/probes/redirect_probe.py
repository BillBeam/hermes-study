"""Probe: does hermes_cli.nous_billing._request leak Authorization across a
cross-host redirect? Two loopback servers; A 302-redirects to B.
127.0.0.1 and localhost are different origins for url_origin().
"""
import json, sys, threading, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "/home/user/hermes-agent")

captured = {}


def make_handler(name, redirect_to=None):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.setdefault(name, []).append(dict(self.headers))
            if redirect_to:
                self.send_response(302)
                self.send_header("Location", redirect_to + self.path)
                self.end_headers()
            else:
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


srv_b = HTTPServer(("127.0.0.1", 0), make_handler("B"))
port_b = srv_b.server_address[1]
srv_a = HTTPServer(("127.0.0.1", 0), make_handler("A", f"http://localhost:{port_b}"))
port_a = srv_a.server_address[1]
for s in (srv_a, srv_b):
    threading.Thread(target=s.serve_forever, daemon=True).start()

import hermes_cli.nous_billing as nb

nb._token_cache = (9e18, "SECRET-BEARER-TOKEN", f"http://127.0.0.1:{port_a}")
try:
    nb._request("GET", "/api/billing/probe")
except Exception as exc:
    print("request raised:", type(exc).__name__, exc)

print("A saw Authorization:", captured.get("A", [{}])[0].get("Authorization"))
print("B saw Authorization:", captured.get("B", [{}])[0].get("Authorization") if captured.get("B") else "<B never hit>")

# contrast: open_credentialed_url
from hermes_cli.urllib_security import open_credentialed_url
captured.clear()
req = urllib.request.Request(
    f"http://127.0.0.1:{port_a}/api/billing/probe",
    headers={"Authorization": "Bearer SECRET-BEARER-TOKEN", "Accept": "application/json"},
)
with open_credentialed_url(req, timeout=5) as r:
    r.read()
print("[open_credentialed_url] A saw Authorization:", captured.get("A", [{}])[0].get("Authorization"))
print("[open_credentialed_url] B saw Authorization:", captured.get("B", [{}])[0].get("Authorization") if captured.get("B") else "<B never hit>")
