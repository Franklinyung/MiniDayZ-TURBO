#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniDayZ+ Reimagined 2.3.8 —— TURBO v3 生成器
从 data.orig.js（原版备份）读取，生成修改过的 data.js。可反复重跑，不会累积修改。

功能：
  1. 经验收益 ×15（递归处理所有经验表达式，死亡扣分保持原样）
  2. 随机掉落 100% 变成最强枪 PKM 或它的弹药 7.62x54R
  3. 子弹/物品用不完：消耗动作由 -1 变成 +1（越用越多）
  4. 物品堆叠上限解锁到无限（配合 3，避免数量溢出）
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

GUN_ID = 246          # 最强枪 PKM（60-100 伤害 / 650 发每分 / 100 发弹链 / 无附加条件）
AMMO_ID = 13          # 它的弹药 7.62x54R
GUN_EVERY = 3         # 每 N 次随机掉落 1 次是枪，其余是弹药

INFINITE_ITEMS = True # True = 所有可堆叠物品（含子弹）消耗时 +1，用不完
                      # False = 恢复原版消耗
INFINITE_STACK = True # True = 堆叠上限解锁为 31415926（配合上面，数量涨了也不会溢出）

# 背包格(obj6) 的全部数量变量：不同装备槽位的物品数量分开存
CONSUME_VARS = (11, 12, 13, 15, 16)
# ────────────────────────────────────────────────────────────

raw = open(SRC, encoding="utf-8").read()
bom = raw.startswith("\ufeff")
body = raw.lstrip("\ufeff")

# 校验枪/弹药 ID 真的能生成
m = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"Spawn_drop"\]\]\]\]', body)
if m:
    nxt = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"', body[m.end():])
    blk = body[m.start(): m.end() + nxt.start()] if nxt else body[m.start():]
    valid = {int(x) for x in re.findall(r'\[\[0,\[0,0\]\],\[8,0\],\[7,\[0,(\d+)\]\]\]', blk)}
    for tag, i in (("枪", GUN_ID), ("弹药", AMMO_ID)):
        if i not in valid:
            sys.exit(f"[中止] {tag} ID {i} 不在生成表里")
    print(f"[检查] 枪 {GUN_ID} / 弹药 {AMMO_ID} 均可生成 ✓（生成表 {len(valid)} 种）")

data = json.loads(body)
project = data["project"]

S = dict(xp_nodes=0, xp_penalty=0, drops=0, guns=0, ammo=0,
         consume=0, stack=0)


def scale_xp(expr):
    """递归把经验表达式里的正数常量 × XP_MULT（不用任何运算符节点，零歧义）"""
    if isinstance(expr, list):
        # [0, N] 数字常量
        if len(expr) == 2 and expr[0] == 0 and isinstance(expr[1], (int, float)) \
                and not isinstance(expr[1], bool):
            if expr[1] > 0:
                expr[1] = expr[1] * XP_MULT
                S["xp_nodes"] += 1
            else:
                S["xp_penalty"] += 1
            return
        # 其余节点（三元/变量/对象表达式）继续下钻；跳过 [23,"var"] 这类变量引用
        for i, v in enumerate(expr):
            if isinstance(v, list):
                scale_xp(v)


def walk(o):
    if isinstance(o, list):
        # ── 1. 经验动作 [-1,122,null,uid,false,[[11,"expierence_points"],[7,EXPR]]]
        if (len(o) == 6 and o[0] == -1 and o[1] == 122
                and isinstance(o[5], list) and len(o[5]) == 2):
            a, b = o[5]
            if (isinstance(a, list) and len(a) == 2 and a[0] == 11
                    and a[1] == "expierence_points"
                    and isinstance(b, list) and len(b) >= 2 and b[0] == 7):
                scale_xp(b[1])

        # ── 2. 掉落 [189,69,...,[[1,[2,"Spawn_drop"]],[13,...,[7,[0,-1]]]]]
        if (len(o) >= 6 and o[0] == 189 and o[1] == 69
                and isinstance(o[5], list) and len(o[5]) >= 2):
            pars = o[5]
            if (isinstance(pars[0], list) and pars[0] == [1, [2, "Spawn_drop"]]
                    and isinstance(pars[1], list) and pars[1] and pars[1][0] == 13):
                last = pars[1][-1]
                if (isinstance(last, list) and len(last) == 2 and last[0] == 7
                        and last[1] == [0, -1]):
                    S["drops"] += 1
                    if S["drops"] % GUN_EVERY == 0:
                        last[1][1] = GUN_ID
                        S["guns"] += 1
                    else:
                        last[1][1] = AMMO_ID
                        S["ammo"] += 1

        # ── 3. 物品消耗 [0,[5,[21,6,false,null,VAR],[0,1]]]  数量 - 1
        #      背包格(obj6) 有 5 个独立数量变量：var11/12/13/15/16
        #      （对应不同装备槽位，弹药分布在不同变量里），必须全部处理。
        #      把常量 1 改成 -1 → 「数量 - (-1)」= 数量 +1。
        if (len(o) == 2 and o[0] == 0 and isinstance(o[1], list)
                and len(o[1]) == 3 and o[1][0] == 5
                and isinstance(o[1][1], list) and len(o[1][1]) == 5
                and o[1][1][:2] == [21, 6] and o[1][1][4] in CONSUME_VARS
                and o[1][2] == [0, 1]):
            o[1][2][1] = -1
            S["consume"] += 1
            S.setdefault("by_var", {})
            S["by_var"][o[1][1][4]] = S["by_var"].get(o[1][1][4], 0) + 1

        # ── 4. 堆叠上限 [18,[12,[23,"perk_cybb"],[0,1]],[0,31415926],[0,X]] → 恒无限
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

out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(DST, "w", encoding="utf-8").write(("\ufeff" if bom else "") + out)

print(f"[经验] 常量节点 ×{XP_MULT}：{S['xp_nodes']} 个；扣分保持原样 {S['xp_penalty']} 处")
print(f"[掉落] 随机掉落 {S['drops']} 处全部改为必出：枪 {S['guns']} / 弹药 {S['ammo']}")
if INFINITE_ITEMS:
    print(f"[无限] 消耗动作 -1 → +1：{S['consume']} 处  {dict(sorted(S.get('by_var', {}).items()))}")
if INFINITE_STACK:
    print(f"[上限] 堆叠上限解锁：{S['stack']} 处")
print(f"[输出] {DST}  {os.path.getsize(DST) / 1024 / 1024:.1f} MB")
