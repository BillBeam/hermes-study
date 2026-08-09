"""H-R9A-b 复现实验:reap_worker_zombies() 的 waitpid(-1) 会不会替别人收尸。

假设:R9A "asyncio 侧三次实测未复现" 是因为**测错了地方**——
asyncio 的 ThreadedChildWatcher 为每个子进程起一条**已经阻塞在 waitpid(pid, 0) 的线程**,
它通常先赢;而普通 subprocess.Popen **没有**这样的线程,只在 .poll()/.wait() 时才收,
于是窗口期内被 waitpid(-1) 抢走。

对照三组:
  1. 基线对照:不抢,Popen.wait() 应得真实退出码 42
  2. 实验组:抢完再 wait(),看 Popen.wait() 报什么
  3. asyncio 组:看 ThreadedChildWatcher 在场时谁赢
"""
import asyncio
import os
import subprocess
import sys
import time

SLEEP_THEN_FAIL = [sys.executable, "-c", "import sys; sys.exit(42)"]


def wait_until_zombie(pid, timeout=5.0):
    """等到子进程真的退出(变僵尸),不靠 sleep 猜。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                state = fh.read().rsplit(b")", 1)[1].split()[0]
            if state == b"Z":
                return True
        except FileNotFoundError:
            return True
        time.sleep(0.01)
    return False


def group1_control():
    p = subprocess.Popen(SLEEP_THEN_FAIL)
    wait_until_zombie(p.pid)
    rc = p.wait()
    return rc


def group2_stolen(reaper):
    p = subprocess.Popen(SLEEP_THEN_FAIL)
    wait_until_zombie(p.pid)
    reaped = reaper()
    rc = p.wait()
    return reaped, rc


async def _group3():
    proc = await asyncio.create_subprocess_exec(*SLEEP_THEN_FAIL)
    wait_until_zombie(proc.pid)
    # 给 watcher 线程一个真实的调度窗口,再去抢
    time.sleep(0.05)
    stolen = []
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        stolen.append((pid, status))
    rc = await proc.wait()
    return stolen, rc


def main():
    sys.path.insert(0, "/home/user/hermes-agent")
    try:
        from hermes_cli.kanban_db import reap_worker_zombies
        reaper = reap_worker_zombies
        which = "真实 reap_worker_zombies()"
    except Exception as exc:  # pragma: no cover - 记录导入失败原因
        print(f"[!] 导入真实函数失败({type(exc).__name__}: {exc}),回落到等价内联实现")

        def reaper():
            out = []
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                out.append(pid)
            return out
        which = "等价内联 waitpid(-1, WNOHANG) 循环"

    print(f"收尸者 = {which}")
    print(f"[组1 对照] 无人抢,     Popen.wait() = {group1_control()}   (真实退出码应为 42)")
    reaped, rc = group2_stolen(reaper)
    print(f"[组2 实验] 抢走 {len(reaped)} 个,Popen.wait() = {rc}   (被抢后属主看到的退出码)")
    stolen, rc3 = asyncio.run(_group3())
    print(f"[组3 asyncio] 抢到 {len(stolen)} 个,proc.wait() = {rc3}   (ThreadedChildWatcher 在场)")


if __name__ == "__main__":
    main()
