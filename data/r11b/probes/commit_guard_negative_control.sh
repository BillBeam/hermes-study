#!/usr/bin/env bash
# 负控:证明 in-flight 提交守卫在「完成信号未到」时确实拦得住一次误提交。
#
# 为什么要负控:一个从来没拦住过任何东西的关卡,和一个不存在的关卡,在报告里长得一模一样。
# R11A 的引用扩展名关卡就配了负控(自造漂移锚点),这里沿用同一条规矩。
#
# 本脚本不依赖任何会话专属路径:仓库根从脚本自身位置推出,工作区用 mktemp -d。
# 它克隆的是 HEAD,所以测的是**已提交**的守卫,不是工作区里的草稿。
#
# 用法: bash data/r11b/probes/commit_guard_negative_control.sh
# 退出码 0 = 全部断言通过。
set -u

STUDY_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0
check() {  # check <描述> <期望:ok|blocked> <实际退出码>
    local desc=$1 want=$2 rc=$3
    if { [ "$want" = ok ] && [ "$rc" -eq 0 ]; } || { [ "$want" = blocked ] && [ "$rc" -ne 0 ]; }; then
        PASS=$((PASS+1)); echo "  PASS  $desc"
    else
        FAIL=$((FAIL+1)); echo "  FAIL  $desc (want=$want rc=$rc)"
    fi
}

git clone -q "$STUDY_ROOT" "$WORK/clone"
cd "$WORK/clone" || exit 1
git config user.email probe@example.invalid
git config user.name probe

echo "== 0. 钩子安装(克隆里 .git/hooks 是空的,这本身是被测的一环) =="
test -x .git/hooks/pre-commit; check "克隆后钩子默认不存在" blocked $?
python3 scripts/install_hooks.py >/dev/null 2>&1
test -x .git/hooks/pre-commit; check "install_hooks.py 装上了 pre-commit" ok $?

echo "== 1. 正控:无 claim 时,提交照常通过 =="
echo hi > notes/probe-unclaimed.md
git add notes/probe-unclaimed.md
git commit -q -m "probe: unclaimed file" >/dev/null 2>&1
check "无 claim 时提交成功" ok $?

echo "== 2. 负控主体:claim 为 OPEN 时,被声明的路径提交被拦 =="
cat > data/inflight/probe.claim <<'CLAIM'
agent: probe · 负控用假生产者
dispatched: (negative control)
signal: OPEN
path: notes/probe-inflight.md
path: data/probe-glob/*.tsv
CLAIM
echo "正在写入中" > notes/probe-inflight.md
git add notes/probe-inflight.md
before=$(git rev-parse HEAD)
git commit -q -m "probe: should be blocked" >/dev/null 2>&1
check "OPEN claim 覆盖的路径被拒绝提交" blocked $?
after=$(git rev-parse HEAD)
[ "$before" = "$after" ]; check "被拒绝后 HEAD 未前进(没有半个提交)" ok $?

echo "== 3. 通配符也算数 =="
mkdir -p data/probe-glob
echo x > data/probe-glob/a.tsv
git add data/probe-glob/a.tsv
git commit -q -m "probe: glob should be blocked" >/dev/null 2>&1
check "通配符 path: 覆盖的路径同样被拒" blocked $?

echo "== 4. 守卫不是全局冻结:OPEN 期间无关文件照常可提交 =="
git reset -q
echo hi > notes/probe-other.md
git add notes/probe-other.md data/inflight/probe.claim
git commit -q -m "probe: unrelated file plus the claim itself" >/dev/null 2>&1
check "无关文件 + claim 文件自身可提交" ok $?

echo "== 5. 放行腿:signal 改 RELEASED 后,同一条提交能过 =="
git add notes/probe-inflight.md
git commit -q -m "probe: still blocked before release" >/dev/null 2>&1
check "放行前仍被拦(确认第 4 步没有意外放行)" blocked $?
sed -i 's/^signal: OPEN$/signal: RELEASED 任务完成通知 probe-0000/' data/inflight/probe.claim
git add notes/probe-inflight.md data/inflight/probe.claim
git commit -q -m "probe: released" >/dev/null 2>&1
check "RELEASED 后同一条提交成功" ok $?

echo "== 6. 如实申报:--no-verify 绕得过(钩子不是权限系统) =="
sed -i 's/^signal: RELEASED.*$/signal: OPEN/' data/inflight/probe.claim
echo again > notes/probe-inflight.md
git add notes/probe-inflight.md
git commit -q --no-verify -m "probe: bypassed on purpose" >/dev/null 2>&1
check "--no-verify 确实绕过(已知口子,故意断言它存在)" ok $?

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
