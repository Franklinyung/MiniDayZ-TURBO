#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniDayZ+ Reimagined 2.3.8 —— TURBO v7 生成器
从 data.orig.js（原版备份）读取，生成修改过的 data.js。可反复重跑，不会累积修改。

关键修正（v7）：
  Spawn_drop 调用是 Spawn_drop(物品ID, x, y, 变体) ——
  **第一个参数才是物品 ID**，之前改的第四个参数是耐久/变体，所以枪一直刷不出来。
  本版改为修改参数 1。

改动：
  1. 90% 的物资生成点改成「枪 + 它对应的弹药」成对（37 把枪全覆盖）
  2. 所有弹药数量固定 100 发（19 种口径/投射物）
  3. 经验收益 ×15（死亡扣分不变）
  4. 物品消耗 -1 → +1（越用越多）
  5. 堆叠上限解锁到 31415926
"""
import json
import re
import sys
import os

sys.setrecursionlimit(20000)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data.orig.js")
DST = os.path.join(HERE, "data.js")

# ───────────────────────── 可调参数 ─────────────────────────
XP_MULT = 15
LOOT_GUN_RATE = 0.90      # 多少比例的物资生成点改成枪+弹药配对（1.0 = 全部）
ALL_AMMO_COUNT = 100      # 所有弹药固定数量

INFINITE_ITEMS = True
INFINITE_STACK = True

# 枪 → 它用的弹药
GUN_AMMO = {
    151: 12, 152: 12, 156: 13, 158: 11, 159: 14, 160: 15, 161: 15, 167: 16,
    168: 13, 169: 69, 172: 13, 173: 12, 174: 13, 175: 138, 176: 12, 177: 11,
    178: 17, 181: 100, 182: 100, 185: 101, 191: 11, 193: 11, 194: 14, 196: 17,
    197: 13, 198: 11, 199: 11, 230: 105, 232: 11, 233: 11, 234: 105, 237: 15,
    238: 15, 240: 101, 241: 11, 245: 138, 246: 13,
}
GUN_ORDER = sorted(GUN_AMMO)

# 弹药物品对象 ID（按 ammo_* 图片逐个核实）
AMMO_OBJECTS = [
    30,    # 5.56x45
    29,    # .45 ACP
    31,    # 7.62x54R
    58,    # 7.62x39
    57,    # 5.45x39
    59,    # .357 M
    28,    # 12 号霰弹
    444,   # .22 LR
    566,   # 9x19 P
    137,   # 9x18 M
    138,   # 9x39
    941,   # 40mm 榴弹
    942,   # VOG-25 榴弹
    1102,  # .308 Win
    1369,  # 12.7x108
    1441,  # 40mm 瘟疫榴弹
    927,   # 50 BMG 弹药箱
    393,   # 自制箭
    396,   # 复合箭
]
AMMO_OBJ_SET = set(AMMO_OBJECTS)

CONSUME_VARS = (11, 12, 13, 15, 16)
# ────────────────────────────────────────────────────────────

raw = open(SRC, encoding="utf-8").read()
bom = raw.startswith("\ufeff")
body = raw.lstrip("\ufeff")

m = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"Spawn_drop"\]\]\]\]', body)
if m:
    nxt = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"', body[m.end():])
    blk = body[m.start(): m.end() + nxt.start()] if nxt else body[m.start():]
    valid = {int(x) for x in re.findall(r'\[\[0,\[0,0\]\],\[8,0\],\[7,\[0,(\d+)\]\]\]', blk)}
    bad = [(g, a) for g, a in GUN_AMMO.items() if g not in valid or a not in valid]
    if bad:
        sys.exit(f"[中止] 枪/弹药不在生成表: {bad}")
    print(f"[检查] {len(GUN_AMMO)} 把枪及其弹药均可生成 ✓（生成表 {len(valid)} 种）")

data = json.loads(body)
project = data["project"]

S = dict(xp_nodes=0, xp_penalty=0, consume=0, stack=0, ammo=0)
spawn_calls = []     # 所有 Spawn_drop 调用的参数列表


def scale_xp(expr):
    if isinstance(expr, list):
        if len(expr) == 2 and expr[0] == 0 and isinstance(expr[1], (int, float)) \
                and not isinstance(expr[1], bool):
            if expr[1] > 0:
                expr[1] = expr[1] * XP_MULT
                S["xp_nodes"] += 1
            else:
                S["xp_penalty"] += 1
            return
        for v in expr:
            if isinstance(v, list):
                scale_xp(v)


def walk(o):
    if isinstance(o, list):
        # 1. 经验
        if (len(o) == 6 and o[0] == -1 and o[1] == 122
                and isinstance(o[5], list) and len(o[5]) == 2):
            a, b = o[5]
            if (isinstance(a, list) and len(a) == 2 and a[0] == 11
                    and a[1] == "expierence_points"
                    and isinstance(b, list) and len(b) >= 2 and b[0] == 7):
                scale_xp(b[1])

        # 2. 收集 Spawn_drop 调用（参数列表 [13, p1, p2, p3, p4]）
        if (len(o) >= 6 and o[0] == 189 and o[1] == 69
                and isinstance(o[5], list) and len(o[5]) >= 2):
            pars = o[5]
            if (isinstance(pars[0], list) and pars[0] == [1, [2, "Spawn_drop"]]
                    and isinstance(pars[1], list) and len(pars[1]) >= 2
                    and pars[1][0] == 13):
                args = pars[1]
                p1 = args[1]
                # 只处理「参数1 是数字常量」的调用（物品 ID 固定）
                if (isinstance(p1, list) and len(p1) == 2 and p1[0] == 7
                        and isinstance(p1[1], list) and len(p1[1]) == 2
                        and p1[1][0] == 0 and isinstance(p1[1][1], int)):
                    spawn_calls.append(p1[1])

        # 3. 所有弹药：数量固定
        if (len(o) >= 5 and isinstance(o[0], int) and o[0] in AMMO_OBJ_SET
                and o[1] == 88 and isinstance(o[5], list) and len(o[5]) == 2
                and o[5][0] == [10, 1]):
            val = o[5][1]
            if isinstance(val, list) and val[0] == 7:
                old = val[1]
                if not (isinstance(old, list) and old[0] == 20):
                    val[1] = [0, ALL_AMMO_COUNT]
                    S["ammo"] += 1

        # 4. 弹药数量加成归零
        if (len(o) >= 5 and isinstance(o[0], int) and o[0] in AMMO_OBJ_SET
                and o[1] == 83 and isinstance(o[5], list) and len(o[5]) == 2
                and o[5][0] == [10, 1]
                and isinstance(o[5][1], list) and o[5][1][0] == 7
                and isinstance(o[5][1][1], list) and o[5][1][1][0] == 0):
            o[5][1] = [7, [0, 0]]

        # 5. 物品消耗 -1 → +1
        if (len(o) == 2 and o[0] == 0 and isinstance(o[1], list)
                and len(o[1]) == 3 and o[1][0] == 5
                and isinstance(o[1][1], list) and len(o[1][1]) == 5
                and o[1][1][:2] == [21, 6] and o[1][1][4] in CONSUME_VARS
                and o[1][2] == [0, 1]):
            o[1][2][1] = -1
            S["consume"] += 1

        # 6. 堆叠上限解锁
        if (len(o) == 4 and o[0] == 18
                and o[1] == [12, [23, "perk_cybb"], [0, 1]]
                and o[2] == [0, 31415926]):
            o.clear()
            o.extend([0, 31415926])
            S["stack"] += 1
            return

        for v in o:
            walk(v)
    elif isinstance(o, dict):
        for v in o.values():
            walk(v)


walk(project)

# ── 核心：把 Spawn_drop 的参数1（真正的物品 ID）改成枪 / 对应弹药 ──
total = len(spawn_calls)
paid = int(total * LOOT_GUN_RATE)
if paid % 2:
    paid -= 1
gun_pos = 0
for idx in range(paid):
    gun = GUN_ORDER[gun_pos % len(GUN_ORDER)]
    if idx % 2 == 0:
        spawn_calls[idx][1] = gun              # 枪
    else:
        spawn_calls[idx][1] = GUN_AMMO[gun]    # 该枪的弹药
        gun_pos += 1

out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(DST, "w", encoding="utf-8").write(("\ufeff" if bom else "") + out)

print(f"[掉落] 物资生成点 {total} 个：{paid} 个（{paid*100//total}%）改为枪+弹药成对"
      f"（{paid//2} 对，覆盖 {len(GUN_ORDER)} 把枪）")
print(f"[弹药] {len(AMMO_OBJECTS)} 种口径数量固定 {ALL_AMMO_COUNT} 发（{S['ammo']} 处赋值，加成归零）")
print(f"[经验] 常量节点 ×{XP_MULT}：{S['xp_nodes']} 个；扣分保持原样 {S['xp_penalty']} 处")
if INFINITE_ITEMS:
    print(f"[无限] 消耗动作 -1 → +1：{S['consume']} 处")
if INFINITE_STACK:
    print(f"[上限] 堆叠上限解锁：{S['stack']} 处")
print(f"[输出] {DST}  {os.path.getsize(DST) / 1024 / 1024:.1f} MB")
