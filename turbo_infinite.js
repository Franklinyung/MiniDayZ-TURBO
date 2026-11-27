/*
 * MiniDayZ 2.3.8 TURBO —— 无限子弹补丁
 *
 * 为什么需要它：
 *   改 data.js 能搞定背包弹药（换弹不消耗），但「枪上的数字」（弹匣内子弹）
 *   的递减逻辑在武器实例的运行时状态里，data.js 的事件树里找不到对应的写入点。
 *   所以这里在运行时直接托管武器实例的弹药变量：只允许增加，不允许减少。
 *
 * 原理：
 *   武器对象类型 = obj1030，其实例变量数组里索引 3 是「弹匣内弹药数」。
 *   每 50ms 快照一次，若发现数值变小就还原。
 *   装弹时数值变大 → 保留（正常装填）。
 *   开枪时数值变小 → 还原（相当于无限弹匣）。
 */
(function () {
  'use strict';

  var WEAPON_TYPE_ID = 1030;   // 武器对象类型索引
  var AMMO_VAR_INDEX = 3;      // 实例变量索引：弹匣内弹药
  var TICK_MS = 16;        // 约每帧一次，避免肉眼看得出数字回落
  var MAX_LOCK_DROP = 5;   // 只拦截「小幅减少」（开枪 -1/-3）；归 0 的大幅下降放行（换弹/打空）

  var lastValue = new WeakMap();
  var started = false;

  // 从实例上找到那个「长度 20~30 的纯数字数组」（实例变量数组）
  function findVarArray(inst) {
    var keys = Object.keys(inst);
    for (var i = 0; i < keys.length; i++) {
      var v = inst[keys[i]];
      if (Array.isArray(v) && v.length >= 20 && v.length <= 30 && typeof v[0] === 'number') {
        return v;
      }
    }
    return null;
  }

  function tick() {
    var rt = window.cr_getC2Runtime && window.cr_getC2Runtime();
    if (!rt || !rt.S) return;
    var type = rt.S[WEAPON_TYPE_ID];
    if (!type) return;

    var list = type.instances || type.q || [];
    for (var i = 0; i < list.length; i++) {
      var inst = list[i];
      if (!inst) continue;
      var arr = findVarArray(inst);
      if (!arr) continue;

      var cur = arr[AMMO_VAR_INDEX];
      var prev = lastValue.get(inst);

      if (typeof prev === 'number' && typeof cur === 'number' && cur < prev) {
        // 小幅减少 = 开枪扣弹 → 还原成旧值（无限弹匣）
        // 大幅减少/归零 = 换弹或打空 → 放行，让正常换弹流程工作
        if (prev - cur <= MAX_LOCK_DROP) {
          arr[AMMO_VAR_INDEX] = prev;
          continue;
        }
      }
      lastValue.set(inst, arr[AMMO_VAR_INDEX]);
    }
  }

  function start() {
    if (started) return;
    if (!(window.cr_getC2Runtime && window.cr_getC2Runtime())) {
      setTimeout(start, 500);   // 等游戏运行时就绪
      return;
    }
    started = true;
    setInterval(tick, TICK_MS);
    console.log('[TURBO] 无限子弹补丁已启用');
  }

  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
})();
