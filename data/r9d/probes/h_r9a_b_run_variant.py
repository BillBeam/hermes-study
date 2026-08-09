"""补充实验:subprocess.run() 是否同样被降级为 returncode=0。
webhook_filters.py:279 用的是 run(),而不是裸 Popen,所以必须单独证。
手法:用 monkeypatch 在 communicate() 之后、wait() 之前插入抢收,精确制造那个窗口。
"""
import os, subprocess, sys, time
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_cli.kanban_db import reap_worker_zombies

FAIL = [sys.executable, "-c", "import sys; sys.exit(42)"]

# 对照:正常 run()
r0 = subprocess.run(FAIL, capture_output=True)
print(f"[组A 对照] 正常 subprocess.run().returncode      = {r0.returncode}")

# 实验:在 run() 内部 wait() 之前抢收
orig_wait = subprocess.Popen.wait
stolen = []
def patched_wait(self, timeout=None):
    if not stolen:            # 只抢第一次,模拟看板收尸线程刚好在这一刻 tick
        time.sleep(0.05)      # 让子进程确实已退出成僵尸
        stolen.extend(reap_worker_zombies())
    return orig_wait(self, timeout)

subprocess.Popen.wait = patched_wait
try:
    r1 = subprocess.run(FAIL, capture_output=True)
finally:
    subprocess.Popen.wait = orig_wait
print(f"[组B 实验] 抢走 {len(stolen)} 个后 run().returncode = {r1.returncode}")
print()
print(f"webhook_filters.py:279 的判据 'result.returncode != 0'(非零=拒绝该 webhook):")
print(f"  对照组该判据 = {r0.returncode != 0}  -> 拒绝")
print(f"  实验组该判据 = {r1.returncode != 0}  -> {'拒绝' if r1.returncode != 0 else '放行(fail-open)'}")
