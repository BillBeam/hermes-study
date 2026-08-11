#!/usr/bin/env bash
# 阅读层防漂移关卡的负控(R11E)。
#
# 验收项 1 要求两件事:(a) 自造一处源章与派生件不一致,证明关卡拦得住;
# (b) 证明该关卡不是空绿 —— 绿的时候必须真的比对过,红的时候必须点得出是哪一处不对。
#
# 全部操作在 `mktemp -d` 出来的**临时副本**里做,`chapters/` 与仓库工作区一个字节都不动
# —— 本轮边界写死了 `chapters/` 零改动,而一个"临时改一下再改回来"的负控,
# 会在它运行的那几秒里让并发的 git 操作看见一棵被改过的树。
#
# 重跑:bash data/r11e/probes/reading_layer_negative_control.sh
set -uo pipefail

STUDY="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf 'FAIL  %s\n' "$1"; }

# 只复制关卡真正读到的东西,复制面本身就是一份"关卡的输入面"声明。
W="$TMP/w"
mkdir -p "$W/data"
cp -r "$STUDY/chapters" "$W/chapters"
cp -r "$STUDY/scripts"  "$W/scripts"
cp -r "$STUDY/reading"  "$W/reading"
cp -r "$STUDY/data/r11e" "$W/data/r11e"
cp    "$STUDY/data/chapter-order.tsv" "$W/data/chapter-order.tsv"

GATE=(python3 "$W/scripts/verify_reading_layer.py")
BUILD=(python3 "$W/scripts/build_reading_layer.py")

snapshot() { rm -rf "$TMP/snap"; cp -r "$W" "$TMP/snap"; }
restore()  { rm -rf "$W"; cp -r "$TMP/snap" "$W"; }
snapshot

# ---------------------------------------------------------------- NC1 基线为绿,且绿得有读数
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
if [ $RC -eq 0 ]; then ok "NC1 基线副本上关卡为绿(退出码 0)"; else bad "NC1 基线副本上关卡应为绿,实际 rc=$RC:$OUT"; fi
SEC=$(sed -n 's/.*sections=\([0-9]*\).*/\1/p' <<<"$OUT")
PRD=$(sed -n 's/.*products=\([0-9]*\).*/\1/p' <<<"$OUT")
LNK=$(sed -n 's/.*links=\([0-9]*\).*/\1/p' <<<"$OUT")
if [ "${SEC:-0}" -gt 0 ] && [ "${PRD:-0}" -gt 0 ] && [ "${LNK:-0}" -gt 0 ]; then
  ok "NC1b 绿的同时打印了三类比对数 sections=$SEC products=$PRD links=$LNK(都 >0,不是空绿)"
else
  bad "NC1b 关卡判绿却有一类比对数为 0:sections=${SEC:-?} products=${PRD:-?} links=${LNK:-?}"
fi

# ---------------------------------------------------------------- NC2 源章改一个字 → 阻断,并点名
restore
TARGET="$W/chapters/r3-tool-infrastructure.md"
python3 - "$TARGET" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text(encoding='utf-8')
# 只在 TL;DR 节内改一个字符,改动小到人眼扫一遍不会注意到 —— 这正是要防的形态。
i = t.index('## TL;DR'); j = t.index('\n## ', i)
seg = t[i:j].replace('工具', '工具 ', 1)
p.write_text(t[:i] + seg + t[j:], encoding='utf-8')
PY
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
if [ $RC -ne 0 ]; then ok "NC2 源章改一个字 → 关卡阻断(rc=$RC)"; else bad "NC2 源章被改而关卡仍判绿"; fi
grep -q 'SECTION-DRIFT' <<<"$OUT" && ok "NC2b 失败类型是 SECTION-DRIFT" || bad "NC2b 未报 SECTION-DRIFT:$OUT"
grep -q 'r3-tool-infrastructure.md' <<<"$OUT" && ok "NC2c 点名了被改的那一章" || bad "NC2c 没点名被改的章"
grep -q 'TL;DR' <<<"$OUT" && ok "NC2d 点名了被改的那一节(证明比对到了小节粒度)" || bad "NC2d 没点名被改的节"

# ---------------------------------------------------------------- NC3 派生件被手改 → 阻断
restore
python3 - "$W/reading/01-quickread.md" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text(encoding='utf-8')
p.write_text(t.replace('全貌', '全豹', 1), encoding='utf-8')
PY
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
if [ $RC -ne 0 ]; then ok "NC3 派生件被手改一个字 → 关卡阻断(rc=$RC)"; else bad "NC3 派生件被手改而关卡仍判绿"; fi
grep -q 'PRODUCT-STALE' <<<"$OUT" && ok "NC3b 失败类型是 PRODUCT-STALE" || bad "NC3b 未报 PRODUCT-STALE:$OUT"
grep -q '01-quickread.md' <<<"$OUT" && ok "NC3c 点名了被改的那一份产物" || bad "NC3c 没点名产物"

# ---------------------------------------------------------------- NC4 ★ 改源章后"盲目重建"仍然阻断
# 这一条是本关卡的核心:只有"产物重建+比对"这一道锁时,作者可以一句 --write 把新内容
# 刷进产物,而**没有任何人重新读过那一段**。锁二(源节钉)让"我重读过了"成为一次显式动作。
restore
python3 - "$W/chapters/r5-session-state-and-persistence.md" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text(encoding='utf-8')
i = t.index('## TL;DR'); j = t.index('\n## ', i)
p.write_text(t[:i] + t[i:j].replace('会话', '对话', 1) + t[j:], encoding='utf-8')
PY
OUT="$("${BUILD[@]}" --write 2>&1)"; RC=$?
if [ $RC -ne 0 ]; then ok "NC4 生产者自己也拒绝构建(rc=$RC)—— 盲目 --write 刷不进去"; else bad "NC4 生产者在源节钉对不上时仍然写了产物"; fi
grep -q 'SECTION-DRIFT' <<<"$OUT" && ok "NC4b 生产者报的是 SECTION-DRIFT" || bad "NC4b 生产者未报 SECTION-DRIFT:$OUT"
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
if [ $RC -ne 0 ]; then ok "NC4c 关卡同样阻断"; else bad "NC4c 关卡放过了"; fi
# 重钉(= 显式声明"我重读过了")之后,同一棵树才允许重建并转绿
"${BUILD[@]}" --restamp >/dev/null 2>&1
"${BUILD[@]}" --write   >/dev/null 2>&1
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
if [ $RC -eq 0 ]; then ok "NC4d --restamp 后同一棵树转绿(关卡可解除,不是死锁)"; else bad "NC4d 重钉重建后仍不绿:$OUT"; fi

# ---------------------------------------------------------------- NC5 锚点被改坏 → 报 ANCHOR-UNRESOLVED
restore
python3 - "$W/reading/03-problem-index.md" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text(encoding='utf-8')
p.write_text(re.sub(r'\.md#([^\)\s]+)\)', r'.md#\1-不存在的锚点)', t, count=1), encoding='utf-8')
PY
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
grep -q 'ANCHOR-UNRESOLVED' <<<"$OUT" && ok "NC5 锚点指向不存在的标题 → ANCHOR-UNRESOLVED" || bad "NC5 未报 ANCHOR-UNRESOLVED:$OUT"
[ $RC -ne 0 ] && ok "NC5b 该失败阻断" || bad "NC5b 未阻断"

# ---------------------------------------------------------------- NC6 空绿守卫真的会开火
restore
rm -f "$W"/reading/*.md
OUT="$("${GATE[@]}" 2>&1)"; RC=$?
grep -q 'EMPTY-GATE' <<<"$OUT" && ok "NC6 产物全没了 → EMPTY-GATE 开火(拒绝对着空集判绿)" || bad "NC6 未报 EMPTY-GATE:$OUT"
grep -q 'products=0' <<<"$OUT" && ok "NC6b 打印出 products=0" || bad "NC6b 未打印 products=0"
[ $RC -ne 0 ] && ok "NC6c 该失败阻断" || bad "NC6c 未阻断"

# ---------------------------------------------------------------- 收尾:确认真源一个字节没动
restore
if git -C "$STUDY" diff --quiet -- chapters/ 2>/dev/null; then
  ok "NC7 负控全程未改动仓库 chapters/(git diff 为空)"
else
  bad "NC7 仓库 chapters/ 被改动了"
fi

printf '\n负控结果:PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
