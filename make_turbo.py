#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniDayZ+ Reimagined 2.3.8 —— TURBO v4 生成器
从 data.orig.js（原版备份）读取，生成修改过的 data.js。可反复重跑，不会累积修改。

改动：
  1. 经验收益 ×15（递归处理表达式树，死亡扣分不变）
  2. 约 80% 的随机掉落点改成「枪 + 配套弹药」成对掉落（37 把枪全覆盖）
     剩 20% 保持原版随机，保留物资多样性
  3. 物品消耗 -1 → +1（子弹/药品/食物越用越多）
  4. 堆叠上限解锁到 31415926
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
XP_MULT = 15          # 经验倍率
LOOT_GUN_RATE = 0.80  # 用于「枪+弹药」配对的掉落点比例（0~1）

INFINITE_ITEMS = True # 物品消耗 -1 → +1
INFINITE_STACK = True # 堆叠上限解锁

# 枪 → 它用的弹药（ID 均已校验存在于 Spawn_drop 生成表）
GUN_AMMO = {
    151: 12,   # FNX 45          → .45 ACP
    152: 12,   # 柯尔特 1911       → .45 ACP
    156: 13,   # 莫辛-纳甘         → 7.62x54R
    158: 11,   # M4A1            → 5.56x45
    159: 14,   # AKM             → 7.62x39
    160: 15,   # AK-74           → 5.45x39
    161: 15,   # AKs-74u         → 5.45x39
    167: 16,   # M92 连发步枪      → .357 M
    168: 13,   # SVD 德拉贡诺夫     → 7.62x54R
    169: 69,   # MP5K            → 9x19 P
    172: 13,   # 短管莫辛          → 7.62x54R
    173: 12,   # UMP-45          → .45 ACP
    174: 13,   # RPK             → 7.62x54R
    175: 138,  # FN-FAL          → .308 Win
    176: 12,   # 雕花柯尔特        → .45 ACP
    177: 11,   # AUG A1          → 5.56x45
    178: 17,   # Saiga-12K       → 12 号霰弹
    181: 100,  # PM 手枪         → 9x18 M
    182: 100,  # PB 手枪         → 9x18 M
    185: 101,  # VSS 消音狙击枪    → 9x39
    191: 11,   # 柯尔特 M16A2     → 5.56x45
    193: 11,   # M4A1            → 5.56x45
    194: 14,   # AKM             → 7.62x39
    196: 17,   # Saiga-12K       → 12 号霰弹
    197: 13,   # RPK             → 7.62x54R
    198: 11,   # M16A2           → 5.56x45
    199: 11,   # AUG A1          → 5.56x45
    230: 105,  # Milkor MGL      → 40mm 榴弹
    232: 11,   # FAMAS F1        → 5.56x45
    233: 11,   # Mini-14         → 5.56x45
    234: 105,  # M79             → 40mm 榴弹
    237: 15,   # AK-74           → 5.45x39
    238: 15,   # AKs-74u         → 5.45x39
    240: 101,  # AS-VAL          → 9x39
    241: 11,   # M249 SAW        → 5.56x45
    245: 138,  # M134 加特林      → .308 Win
    246: 13,   # PKM             → 7.62x54R
}
GUN_ORDER = sorted(GUN_AMMO)

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
        sys.exit(f"[中止] 这些枪/弹药不在生成表里: {bad}")
    print(f"[检查] {len(GUN_AMMO)} 把枪及其弹药均可生成 ✓（生成表 {len(valid)} 种）")

data = json.loads(body)
project = data["project"]

S = dict(xp_nodes=0, xp_penalty=0, consume=0, stack=0)
drop_slots = []   # 收集所有「随机掉落」的末位参数引用


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

        # 2. 收集随机掉落点（之后统一配对）
        if (len(o) >= 6 and o[0] == 189 and o[1] == 69
                and isinstance(o[5], list) and len(o[5]) >= 2):
            pars = o[5]
            if (isinstance(pars[0], list) and pars[0] == [1, [2, "Spawn_drop"]]
                    and isinstance(pars[1], list) and pars[1] and pars[1][0] == 13):
                last = pars[1][-1]
                if (isinstance(last, list) and len(last) == 2 and last[0] == 7
                        and last[1] == [0, -1]):
                    drop_slots.append(last[1])

        # 3. 物品消耗 -1 → +1
        if (len(o) == 2 and o[0] == 0 and isinstance(o[1], list)
                and len(o[1]) == 3 and o[1][0] == 5
                and isinstance(o[1][1], list) and len(o[1][1]) == 5
                and o[1][1][:2] == [21, 6] and o[1][1][4] in CONSUME_VARS
                and o[1][2] == [0, 1]):
            o[1][2][1] = -1
            S["consume"] += 1

        # 4. 堆叠上限解锁
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

# ── 掉落配对：前 80% 的点改成「枪 + 对应弹药」相邻成对 ──
total = len(drop_slots)
paid = int(total * LOOT_GUN_RATE)
if paid % 2:
    paid -= 1                       # 保证成对
gun_pos = 0
for idx in range(paid):
    gun = GUN_ORDER[gun_pos % len(GUN_ORDER)]
    if idx % 2 == 0:
        drop_slots[idx][1] = gun              # 枪
    else:
        drop_slots[idx][1] = GUN_AMMO[gun]    # 这把枪的弹药
        gun_pos += 1
pairs = paid // 2
print(f"[掉落] 随机掉落点 {total} 个：{paid} 个（{paid*100//total}%）改为枪+弹药成对（{pairs} 对，覆盖 {len(GUN_ORDER)} 把枪），"
      f"剩 {total - paid} 个保持随机")

out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(DST, "w", encoding="utf-8").write(("\ufeff" if bom else "") + out)

print(f"[经验] 常量节点 ×{XP_MULT}：{S['xp_nodes']} 个；扣分保持原样 {S['xp_penalty']} 处")
if INFINITE_ITEMS:
    print(f"[无限] 消耗动作 -1 → +1：{S['consume']} 处")
if INFINITE_STACK:
    print(f"[上限] 堆叠上限解锁：{S['stack']} 处")
print(f"[输出] {DST}  {os.path.getsize(DST) / 1024 / 1024:.1f} MB")
