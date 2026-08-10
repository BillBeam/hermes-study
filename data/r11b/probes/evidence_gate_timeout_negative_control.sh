#!/usr/bin/env bash
# 负控:证明 H-R11A-e 的修复真的把「一条超时命令炸掉整轮扫描」拦住了。
#
# 修复前的形态:关卡对每条命令给 TIMEOUT 秒上限,却**不捕 subprocess.TimeoutExpired**。
# 一条跑不完的命令让整个进程带 traceback 退出,**其后的文件一个都没被检查**,
# 而它此前打印出来的仍是一份看起来完整的失败列表 —— 覆盖面是空的,输出看着是满的。
#
# 本脚本造两份夹具:第一份含一条必然超时的命令,第二份含一条**必然不匹配**的命令。
# 断言:跑「超时那份 + 不匹配那份」时,**第二份的差异仍被报出来**。
# 修复前这条断言必然失败(进程在第一份就崩了)。
#
# 不依赖会话专属路径:仓库根从脚本自身位置推出,夹具建在 mktemp -d 里。
# 用法: bash data/r11b/probes/evidence_gate_timeout_negative_control.sh
set -u
ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
check() { if [ "$3" = "$2" ]; then PASS=$((PASS+1)); echo "  PASS  $1"; \
          else FAIL=$((FAIL+1)); echo "  FAIL  $1 (want=$2 got=$3)"; fi; }

# 夹具 A:一条必然超时的命令(关卡的 TIMEOUT 用环境变量压到 2 秒)
cat > "$WORK/a-timeout.md" <<'MD'
# 夹具 A

```verify
sleep 30
```

```text
(不会有输出,因为它会超时)
```
MD

# 夹具 B:一条必然不匹配的命令 —— 这是「超时之后还查不查」的探针
cat > "$WORK/b-mismatch.md" <<'MD'
# 夹具 B

```verify
echo actual-value
```

```text
pasted-value-that-differs
```
MD

echo "== 1. 单跑夹具 B:关卡本来就该报出这处差异(正控) =="
out=$(HERMES_EVIDENCE_TIMEOUT=2 python3 "$ROOT/scripts/verify_evidence_commands.py" "$WORK/b-mismatch.md" 2>&1)
echo "$out" | grep -q "EVIDENCE-DIFF"; check "夹具 B 的差异被报出" 0 $?

echo "== 2. 超时那份排在前面时,后一份仍然被检查(本次修复要保证的) =="
out=$(HERMES_EVIDENCE_TIMEOUT=2 python3 "$ROOT/scripts/verify_evidence_commands.py" \
        "$WORK/a-timeout.md" "$WORK/b-mismatch.md" 2>&1)
rc=$?
echo "$out" | grep -q "EVIDENCE-TIMEOUT"; check "超时被显式报成 EVIDENCE-TIMEOUT" 0 $?
echo "$out" | grep -q "EVIDENCE-DIFF"; check "超时之后,后一份文件仍被检查到" 0 $?
echo "$out" | grep -qE "^Traceback"; check "进程没有以 traceback 崩掉" 1 $?
[ "$rc" -ne 0 ]; check "整体退出码非零(超时算失败,不是静默通过)" 0 $?

echo "== 3. 计数里看得见超时,不被算成通过 =="
echo "$out" | grep -qE "timedout=[1-9]"; check "汇总行报出 timedout 计数" 0 $?

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
