#!/usr/bin/env bash
# 负控:可跑性检查(R11C 落地,结清 H-R11B-c)真的拦得住坏证据吗?
#
# 一个关卡最坏的失败态不是误报,是**空绿** —— 它跑完、退出码 0、什么都没查。
# R8C 实测过这个形态:5 条引用全部逐字正确、行号全对,只因锚点写在块后并用散文
# 隔开,关卡就报 `UNCHECKED=5` + `OK` + 退出码 0,一条都没校验而输出是绿的。
# 所以本负控不满足于「拿真语料跑一遍是绿的」,而是**自造每一类坏证据**,
# 逐条断言关卡对它变红,并**反向断言**关卡对正当形态不变红。
#
# 不依赖会话专属路径:临时目录用 mktemp,仓库根从本文件位置推出。
#   bash data/r11c/probes/runnability_negative_control.sh
set -u

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
GATE="$ROOT/scripts/verify_evidence_commands.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

# 造一份只含一个 verify 块的底稿。$1=文件名 $2=块内容
fixture() { printf '# fixture\n\n```verify\n%s\n```\n' "$2" > "$TMP/$1"; }

# 跑关卡,回显退出码与输出
run_gate() { python3 "$GATE" "$TMP/$1" 2>&1; }
gate_rc()  { python3 "$GATE" "$TMP/$1" >"$TMP/.out" 2>&1; echo $?; }

expect_red() {  # $1=fixture $2=断言名 $3=期望出现的标记
  local rc; rc=$(gate_rc "$1")
  if [ "$rc" != "0" ] && grep -q "$3" "$TMP/.out"; then ok "$2"
  else bad "$2 (rc=$rc, 未见 $3)"; sed -n '1,6p' "$TMP/.out" | sed 's/^/        /'; fi
}
expect_green() {  # $1=fixture $2=断言名
  local rc; rc=$(gate_rc "$1")
  if [ "$rc" = "0" ]; then ok "$2"
  else bad "$2 (rc=$rc,不该红)"; sed -n '1,6p' "$TMP/.out" | sed 's/^/        /'; fi
}

echo "== A 类:围栏里混进了命令自己的输出 =="
# R11B 实测 22 处。形态是作者把「命令 + 它打印的东西」一起贴进了 verify 围栏。
fixture a.md 'echo hello
hello'
expect_red a.md "A 类(命令与输出混排)被拦下" "EVIDENCE-RUNFAIL"

echo "== B 类:引用了此刻不存在的路径 =="
# R11B 实测 29 处,其中 17 处是上一轮会话的专属目录。
fixture b.md 'cd /home/user/no-such-session-dir-r11c && ls'
expect_red b.md "B 类(路径已不存在)被拦下" "EVIDENCE-RUNFAIL"

echo "== E 类:运行期错误 =="
fixture e.md "python3 -c 'import json; json.loads(\"{oops\")'"
expect_red e.md "E 类(运行期抛异常)被拦下" "EVIDENCE-RUNFAIL"

echo "== C 类反向断言:grep 零命中必须保持绿色 =="
# 这一条是本负控里最要紧的。判据若只看退出码,这 27 块会被判成坏证据,
# 而「零命中」恰恰常常就是作者要证明的结论 —— 关卡会对着正确的证据狂叫。
fixture c.md "grep -c 'zzz-no-such-token-r11c' \"$ROOT/CLAUDE.md\""
expect_green c.md "C 类(零命中、stderr 空)未被误判"

echo "== 正当只读命令保持绿色 =="
fixture ok.md 'echo ok'
expect_green ok.md "正当只读命令不被误判"

echo "== MUTATING 块一律不跑 =="
# 语料里真有往基线里装依赖的命令。跑它 = 关卡自己弄脏基线。
fixture m.md 'pip install some-package-that-must-never-be-installed'
rc=$(gate_rc m.md)
if [ "$rc" = "0" ] && grep -q 'skipped-mutating=1' "$TMP/.out"; then
  ok "MUTATING 被跳过且计数(未执行)"
else bad "MUTATING 未被跳过 (rc=$rc)"; sed -n '1,6p' "$TMP/.out" | sed 's/^/        /'; fi

echo "== 关卡不是空绿:红的时候必须真的跑过 =="
# 与 R8C 那次「输出全绿而一条都没查」对照:断言 ran= 计数确实前进了。
gate_rc a.md >/dev/null
if grep -qE 'runnability +ran=1 +runfail=1' "$TMP/.out"; then
  ok "计数行如实反映跑了 1 条、坏 1 条"
else bad "计数行不对"; grep runnability "$TMP/.out" | sed 's/^/        /'; fi

echo "== --no-runnability 可关闭(且关闭后坏证据不再被拦)=="
python3 "$GATE" --no-runnability "$TMP/a.md" >"$TMP/.out2" 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q 'EVIDENCE-RUNFAIL' "$TMP/.out2"; then
  ok "--no-runnability 退回纯配对口径"
else bad "--no-runnability 未生效 (rc=$rc)"; fi

echo "== 已配对块不受影响(不被当成未配对再跑一遍)=="
printf '# fixture\n\n```verify\necho paired\n```\n\n```text\npaired\n```\n' > "$TMP/p.md"
rc=$(gate_rc p.md)
if [ "$rc" = "0" ] && grep -q 'paired=1  unpaired=0' "$TMP/.out" \
   && grep -q 'ran=0' "$TMP/.out"; then
  ok "已配对块只走比对腿,不进可跑性腿"
else bad "配对块被重复处理 (rc=$rc)"; grep -E 'verify-blocks|runnability' "$TMP/.out" | sed 's/^/        /'; fi

echo "== 基线洁净断言:跑完负控后基线仍干净 =="
BASE="${HERMES_BASELINE:-/home/user/hermes-agent}"
if [ -d "$BASE/.git" ]; then
  if [ -z "$(git -C "$BASE" status --porcelain --untracked-files=no)" ]; then
    ok "基线 tracked porcelain 仍为空"
  else bad "基线被弄脏了"; fi
else
  ok "基线不在本机,跳过(关卡对缺席基线返回 None 而非崩溃)"
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
