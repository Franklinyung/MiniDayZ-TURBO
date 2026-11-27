#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniDayZ+ Reimagined 2.3.8 —— TURBO v2 极简爽玩版生成器
从 data.orig.js（原版备份）读取，生成修改过的 data.js。可反复重跑，不会累积修改。

玩法：所有随机掉落 100% 变成「最强枪 或 它的弹药」，经验收益 ×15。

想换枪 / 调强度：改下面的常量，重新 `python3 make_turbo.py` 即可。
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
XP_MULT = 15     # 经验倍率（只放大收益，死亡/重置扣分保持原样）

GUN_ID = 246     # 最强枪：PKM（60-100 伤害，650 发/分，100 发弹链 7.62x54R，无附加条件）
AMMO_ID = 13     # 它的弹药：7.62x54R
                 # 备选最强：GUN_ID=245 (M134 加特林, 60-100, 1000发/分, 300发 .308)
                 #           AMMO_ID=138 (.308 Win)——但加特林需要电池且移速 -10%

GUN_EVERY = 3    # 每 N 次随机掉落里 1 次是枪，其余是弹药。
                 # 3 = 1/3 掉枪、2/3 掉弹；1 = 一半枪一半弹；10 = 十分之一是枪
# ────────────────────────────────────────────────────────────

raw = open(SRC, encoding="utf-8").read()
bom = raw.startswith("\ufeff")
body = raw.lstrip("\ufeff")

# 从 Spawn_drop 函数体提取合法物品 ID，确认枪/弹药 ID 真的可生成
m = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"Spawn_drop"\]\]\]\]', body)
if m:
    nxt = re.search(r'\[189,40,null,\d+,false,false,false,\d+,false,\[\[1,\[2,"', body[m.end():])
    blk = body[m.start(): m.end() + nxt.start()] if nxt else body[m.start():]
    valid = {int(x) for x in re.findall(r'\[\[0,\[0,0\]\],\[8,0\],\[7,\[0,(\d+)\]\]\]', blk)}
    for tag, i in (("枪", GUN_ID), ("弹药", AMMO_ID)):
        if i not in valid:
            sys.exit(f"[中止] {tag} ID {i} 不在 Spawn_drop 生成表里，改用其它 ID")
    print(f"[检查] 枪 ID {GUN_ID} / 弹药 ID {AMMO_ID} 均可生成 ✓（生成表共 {len(valid)} 种）")

data = json.loads(body)
project = data["project"]

stats = dict(xp_simple=0, xp_expr=0, xp_penalty_kept=0, random_total=0, gun=0, ammo=0)


def walk(o):
    if isinstance(o, list):
        # ── 1. 经验：[-1,122,null,uid,false,[[11,"expierence_points"],[7,EXPR]]]
        if (len(o) == 6 and o[0] == -1 and o[1] == 122
                and isinstance(o[5], list) and len(o[5]) == 2):
            a, b = o[5]
            if (isinstance(a, list) and len(a) == 2 and a[0] == 11
                    and a[1] == "expierence_points"
                    and isinstance(b, list) and len(b) >= 2 and b[0] == 7):
                expr = b[1]
                if (isinstance(expr, list) and len(expr) == 2 and expr[0] == 0
                        and isinstance(expr[1], (int, float))):
                    if expr[1] > 0:
                        expr[1] = expr[1] * XP_MULT       # 收益 ×15
                        stats["xp_simple"] += 1
                    else:
                        stats["xp_penalty_kept"] += 1    # 扣分保持原样
                else:
                    # C2 表达式类型 6 = 乘法，包一层 [6,[0,15],原表达式]
                    b[1] = [6, [0, XP_MULT], expr]
                    stats["xp_expr"] += 1

        # ── 2. 掉落：[189,69,...,[[1,[2,"Spawn_drop"]],[13,...,[7,[0,-1]]]]]
        #    末位 -1 = 随机物品 → 全部改为 必出 PKM / 7.62x54R
        if (len(o) >= 6 and o[0] == 189 and o[1] == 69
                and isinstance(o[5], list) and len(o[5]) >= 2):
            pars = o[5]
            if (isinstance(pars[0], list) and pars[0] == [1, [2, "Spawn_drop"]]
                    and isinstance(pars[1], list) and pars[1] and pars[1][0] == 13):
                args = pars[1]
                last = args[-1]
                if (isinstance(last, list) and len(last) == 2 and last[0] == 7
                        and last[1] == [0, -1]):
                    stats["random_total"] += 1
                    if stats["random_total"] % GUN_EVERY == 0:
                        last[1][1] = GUN_ID
                        stats["gun"] += 1
                    else:
                        last[1][1] = AMMO_ID
                        stats["ammo"] += 1

        for v in o:
            walk(v)
    elif isinstance(o, dict):
        for v in o.values():
            walk(v)


walk(project)

out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(DST, "w", encoding="utf-8").write(("\ufeff" if bom else "") + out)

print(f"[经验] 收益 ×{XP_MULT}：简单数值 {stats['xp_simple']} 处 + 复杂表达式 {stats['xp_expr']} 处；"
      f"扣分保持原样 {stats['xp_penalty_kept']} 处")
print(f"[掉落] 随机掉落 {stats['random_total']} 处全部改为必出：枪 {stats['gun']} 处 / 弹药 {stats['ammo']} 处（100%）")
print(f"[输出] {DST}  {os.path.getsize(DST) / 1024 / 1024:.1f} MB")
