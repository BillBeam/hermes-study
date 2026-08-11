#!/usr/bin/env python3
"""R11E · 把本轮测试失败面与 R11D 的逐个比对(验收项 8)。

R11D 已把 43 份文件(31 个有失败 + 12 个零执行)逐个归入九类环境或纪律成因。
本轮**不改基线一个字节**,所以如果失败面**逐个文件相同**,那份诊断可以直接引用;
但**必须先证明它们相同**,不能因为总数相同就假定集合相同 —— 31 和 31 可以是两个不同的 31。

判据:从本轮 run_tests.sh 的完整日志里抽出两组文件名,与 R11D 报告 §6.1 那张表
(12 个零执行)以及 R11D 报的两个数(31 文件 / 75 用例)逐个比对。

    python3 data/r11e/probes/test_failure_delta.py <本轮完整日志>
"""
import re
import sys
from pathlib import Path

# R11D 报告 §6.1 逐个点名的 12 个零执行文件(逐字抄自该表的第一列)
R11D_ZERO = {
    "tests/acp/test_server.py", "tests/acp/test_tools.py", "tests/acp/test_events.py",
    "tests/acp/test_mcp_e2e.py", "tests/acp/test_named_provider_catalogs.py",
    "tests/acp/test_permissions.py", "tests/acp/test_entry.py",
    "tests/acp/test_ping_suppression.py", "tests/acp_adapter/test_acp_images.py",
    "tests/acp_adapter/test_acp_mcp_discovery.py", "tests/acp_adapter/test_acp_commands.py",
    "tests/gateway/test_teams.py",
}
R11D_FAIL_FILES, R11D_FAIL_TESTS = 31, 75

FAIL_HDR = re.compile(r"=== (\d+) files with test failures \((\d+) tests failed\) ===")
ZERO_HDR = re.compile(r"=== (\d+) files where no tests ran")
ITEM = re.compile(r"^\s{2}(\S+\.py)")


def main():
    log = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").split("\n")
    fail, zero, mode = [], [], None
    nf = nt = nz = None
    for line in log:
        m = FAIL_HDR.search(line)
        if m:
            mode, nf, nt = "fail", int(m.group(1)), int(m.group(2))
            continue
        m = ZERO_HDR.search(line)
        if m:
            mode, nz = "zero", int(m.group(1))
            continue
        if mode and line.startswith("==="):
            mode = None
            continue
        it = ITEM.match(line)
        if mode and it:
            (fail if mode == "fail" else zero).append(it.group(1))

    print(f"本轮:有失败的文件 {nf} 份 / 失败用例 {nt} 个 / 零执行文件 {nz} 份")
    print(f"R11D:有失败的文件 {R11D_FAIL_FILES} 份 / 失败用例 {R11D_FAIL_TESTS} 个 / 零执行 12 份")
    ok = True
    if (nf, nt) != (R11D_FAIL_FILES, R11D_FAIL_TESTS):
        print("  [DIFF] 失败文件数或用例数与 R11D 不同 —— 不得引用 R11D 的诊断,须重新逐条归类")
        ok = False
    z = set(zero)
    only_now, only_r11d = z - R11D_ZERO, R11D_ZERO - z
    if only_now or only_r11d:
        ok = False
        for f in sorted(only_now):
            print(f"  [ONLY-R11E] 零执行新增:{f}")
        for f in sorted(only_r11d):
            print(f"  [ONLY-R11D] 零执行消失:{f}")
    else:
        print("零执行 12 份**逐个文件相同**(集合相等,不只是总数相等)。")
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
