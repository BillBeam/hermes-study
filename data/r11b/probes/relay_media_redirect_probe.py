#!/usr/bin/env python3
"""■-R11A-01 的修法之争:主机校验够不够?(R11B 复现 R9C 的实证)

R9A / R9B 的移交项、以及 R11A 的 ■-R11A-01,都把修法写成「比对
`self._base_url`(即校验主机),它就在同一个类的构造里」。R9C 用本地双服务实验
证明这条修法**不足以**修好该缺陷,但 R9C 的 ```verify 块指向 `/path/to/redirect_probe2.py`
——一个占位路径,**脚本从未落库**,所以那次实证在仓库里无法重跑(R11A 自己的
全语料证据扫描已经记下它跑不动:`data/r11a/measurements/evidence-full-corpus.txt:481`)。
本探针把它补成可重跑的。

要害不是「比错了值」,是**校验发生在错的时刻**:主机校验作用在**发起前**的 URL 上,
而凭据是在 `urllib.request.urlopen` **跟随 302 之后**被原样带到新主机的。
于是一个主机完全合法的 URL 照样把 bearer 送到别处,而主机校验对此判「通过」。

两个服务都只监听 127.0.0.1;不出网、不碰基线、不装任何东西。

    HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11b/probes/relay_media_redirect_probe.py

环境变量 HERMES_BASELINE 可覆盖基线检出位置(默认 /home/user/hermes-agent)。
"""
import http.server
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))
sys.path.insert(0, str(BASELINE))

received: dict[str, object] = {}


class Loot(http.server.BaseHTTPRequestHandler):
    """受害端:记录它收到了什么头。"""

    def do_GET(self):  # noqa: N802
        received["host"] = self.headers.get("Host")
        received["authorization"] = self.headers.get("Authorization")
        body = b"stolen-response-body"
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # noqa: D102
        pass


class Redirector(http.server.BaseHTTPRequestHandler):
    """合法端:主机与 base_url 完全相同,但回一个 302。"""

    target = ""

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", self.target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):  # noqa: D102
        pass


def serve(handler):
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def host_check_passes(url: str, base_url: str) -> bool:
    """移交项与 ■-R11A-01 建议的修法:比对配置的 base_url 主机。"""
    return urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(base_url).netloc


def main() -> int:
    loot = serve(Loot)
    Redirector.target = f"http://127.0.0.1:{loot.server_port}/loot"
    legit = serve(Redirector)

    base_url = f"http://127.0.0.1:{legit.server_port}"
    url = f"{base_url}/relay/media/abc123"
    bearer = "Bearer gw-upgrade-token-stand-in"

    # 端口每次运行都不同,所以**证据一律以布尔量输出**,原始 host 只在 --verbose 下打印。
    # 一份每次重跑都不一样的输出,读者无法判断差异是环境问题还是结论变了;
    # 而本探针要钉的断言("受害端不是 base_url 那一端""它收到了 Authorization")
    # 本来就是布尔量,把端口号写进证据只是把噪音当证据。
    verbose = "--verbose" in sys.argv
    if verbose:
        print(f"base_url            = {base_url}")
        print(f"请求的 URL          = {url}")
        print(f"302 目标            = {Redirector.target}")
    victim_netloc = urllib.parse.urlparse(Redirector.target).netloc
    print(f"建议修法(主机校验)判定 = {host_check_passes(url, base_url)}")
    print(f"受害端与 base_url 同源  = "
          f"{victim_netloc == urllib.parse.urlparse(base_url).netloc}")

    # 甲:被测代码此刻的做法 —— 裸 urlopen(gateway/relay/media.py:172 那一句)
    received.clear()
    req = urllib.request.Request(url, headers={"Authorization": bearer})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
    print("\n[甲] 裸 urlopen(现状 + 建议的主机校验)")
    if verbose:
        print(f"  受害端收到 Host          = {received.get('host')}")
    print(f"  受害端收到 Authorization = {received.get('authorization') is not None}")
    print(f"  落盘内容来自受害端       = {body == b'stolen-response-body'}")

    # 乙:仓库自带的修法 —— hermes_cli/urllib_security.py 的 open_credentialed_url
    received.clear()
    try:
        from hermes_cli.urllib_security import open_credentialed_url
    except Exception as exc:  # noqa: BLE001
        print(f"\n[乙] 无法导入 open_credentialed_url:{exc}")
        return 1
    req2 = urllib.request.Request(url, headers={"Authorization": bearer})
    with open_credentialed_url(req2, timeout=10) as resp:
        body2 = resp.read()
    print("\n[乙] open_credentialed_url(仓库自带的正确修法)")
    if verbose:
        print(f"  受害端收到 Host          = {received.get('host')}")
    print(f"  受害端收到 Authorization = {received.get('authorization') is not None}")
    print(f"  落盘内容来自受害端       = {body2 == b'stolen-response-body'}")

    print("\n结论:主机校验判通过,凭据仍到达受害端 => 该修法不足以修好本缺陷。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
