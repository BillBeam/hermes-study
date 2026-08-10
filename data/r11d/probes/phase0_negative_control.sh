#!/usr/bin/env bash
# R11D Phase 0 负控:两道新关卡红的时候真的红,绿的时候是真绿。
# 一个关卡最该被怀疑的性质是「空绿」—— R8C 实测过「输出全绿、退出码 0、一条都没查」。
# 用法:bash data/r11d/probes/phase0_negative_control.sh
set -u
cd "$(git rev-parse --show-toplevel)"
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then echo "  ok   $1 (exit=$2)"; pass=$((pass+1));
        else echo "  FAIL $1 (exit=$2, 期望 $3)"; fail=$((fail+1)); fi }

cp data/chapter-order.tsv /tmp/nc_co.$$ ; cp chapters/r1-what-is-hermes-agent.md /tmp/nc_r1.$$
cp chapters/r11b-the-unwritten-layer.md /tmp/nc_r11b.$$

echo "[基线] 两道关卡当前应为绿"
python3 scripts/verify_chapter_order.py    >/dev/null 2>&1; chk "章序 基线绿" $? 0
python3 scripts/verify_derived_numbers.py  >/dev/null 2>&1; chk "可复算 基线绿" $? 0

echo "[A] 章序:造重号"
sed -i 's|^9\tchapters/r7c|11\tchapters/r7c|' data/chapter-order.tsv
python3 scripts/verify_chapter_order.py >/dev/null 2>&1; chk "重号被拦" $? 1
cp /tmp/nc_co.$$ data/chapter-order.tsv

echo "[B] 章序:造正文重号(r11b 那条真错的形状)"
sed -i 's|平台接驳的主干在第八章|平台接驳的主干在第十一章|' chapters/r11b-the-unwritten-layer.md
python3 scripts/verify_chapter_order.py >/dev/null 2>&1; chk "正文章号错被拦" $? 1
cp /tmp/nc_r11b.$$ chapters/r11b-the-unwritten-layer.md

echo "[C] 章序:删一行落点 -> 未编号 + 不连续"
sed -i '/r8c-dashboard-and-web/d' data/chapter-order.tsv
python3 scripts/verify_chapter_order.py >/dev/null 2>&1; chk "未编号被拦" $? 1
cp /tmp/nc_co.$$ data/chapter-order.tsv

echo "[D] 可复算:把 L1 改回 R8B 那版手抄件"
# 表格行里全是 `|`,不能用 sed 的 | 分隔符 —— 第一版就栽在这里,负控自己先红了一次。
python3 - "chapters/r1-what-is-hermes-agent.md" <<'PYEOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
old, new = "| 563 | 522,207 |", "| 511 | 479,923 |"
assert s.count(old) == 1, s.count(old)
p.write_text(s.replace(old, new), encoding="utf-8")
PYEOF
python3 scripts/verify_derived_numbers.py >/dev/null 2>&1; chk "过期手抄件被拦" $? 1

echo "[E] 关卡不是空绿:红的时候分子分母都动过"
out=$(python3 scripts/verify_derived_numbers.py 2>&1 | grep -o 'declared=18  OK=16  STALE=2')
chk "红时读数为 declared=18 OK=16 STALE=2" "$out" "declared=18  OK=16  STALE=2"
cp /tmp/nc_r1.$$ chapters/r1-what-is-hermes-agent.md

echo "[F] 恢复后两道关卡都回绿"
python3 scripts/verify_chapter_order.py   >/dev/null 2>&1; chk "章序 恢复绿" $? 0
python3 scripts/verify_derived_numbers.py >/dev/null 2>&1; chk "可复算 恢复绿" $? 0

rm -f /tmp/nc_co.$$ /tmp/nc_r1.$$ /tmp/nc_r11b.$$
echo "负控 ${pass}/$((pass+fail))"
[ "$fail" = 0 ]
