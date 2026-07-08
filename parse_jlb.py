#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析路路通离线交路表 jlb.dat（交路表解析的唯一实现；lltskb_sync.py 直接 import 本模块）。

jlb.dat 是明文二进制：车型/车辆描述 与 交路链 交替排列，被控制字节(<0x20)分隔。
交路链 = 若干车次用 '#' 连接。每条链关联其前最近出现的车辆描述。

用法: python3 parse_jlb.py [jlb.dat 路径]   默认 ./jlb.dat
输出: 车次交路.csv / 车次查交路.csv（与 jlb.dat 同目录）

—— 解析踩过的坑（详见 docs/FINDINGS.md），改前务必看：
  1. 长度前缀分帧 → >63 字节长链整条被跳过。改为按控制字节切片。
  2. 车次前缀 [A-Z]? → DJ(动检)双字母前缀截断丢链；[A-Z]{0,2} 又误吞描述里 AC380V。
     用白名单 (?:DJ|[CDGJKLPSTYZ])?。
  3. 前导 0 占位符(#0C1022) → 在 #0 处截断。允许可选前导 0 并归一化去掉。
  4. 双斜杠 D632/3/2、全角字母 Ｄ、斜杠连整车次 C6842/C6843 → 分别用 (?:/…)* 多斜杠、
     NFKC 归一化、斜杠段带字母则拆为独立车次。
"""
import sys, os, re, csv, unicodedata

# 车次: 可选前导0 + (DJ|单字母白名单)? + 1-5位数字 + 若干斜杠段(带字母=整车次/纯数字=往返简写)
_CODE = r'0?(?:DJ|[CDGJKLPSTYZ])?\d{1,5}(?:/(?:DJ|[CDGJKLPSTYZ])?\d+)*'
CHAIN = re.compile(_CODE + r'(?:#' + _CODE + r')+')
_LEAD0 = re.compile(r'^0(?=(?:DJ|[CDGJKLPSTYZ])?\d)')
_LETTER = re.compile(r'[A-Z]')
_CJK = re.compile(r'[一-鿿]')
_CARTYPE = re.compile(r'^\d{2}[A-Z]')


def _expand(part):
    """斜杠段带字母=独立车次拆开(C6842/C6843→两条)；纯数字=往返简写保留(Z158/5)。"""
    out, cur = [], None
    for seg in part.split('/'):
        if cur is None:
            cur = seg
        elif _LETTER.search(seg):
            out.append(cur); cur = seg
        else:
            cur = cur + '/' + seg
    if cur is not None:
        out.append(cur)
    return out


def parse_jlb(raw):
    """返回 [(交路链, 车辆描述, 车次数)]。"""
    runs = re.split(rb'[\x00-\x1f]+', raw)
    rows, last = [], ""
    for rb in runs:
        s = unicodedata.normalize('NFKC', rb.decode('utf-8', 'ignore'))  # 全角→半角
        if len(s) < 2:
            continue
        m = CHAIN.search(s)
        if m and '#' in m.group():
            parts = []
            for p in m.group().split('#'):
                for e in _expand(p):
                    e = _LEAD0.sub('', e)
                    if e and e != '0':
                        parts.append(e)
            if len(parts) >= 2:
                rows.append(('#'.join(parts), last, len(parts)))
            continue
        if _CJK.search(s) or _CARTYPE.match(s):
            last = s.lstrip('+*!"$%&\'().-/ ').strip()
    return rows


def write_csvs(rows, outdir):
    with open(os.path.join(outdir, "车次交路.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["交路链", "车辆描述", "车次数"])
        for chain, desc, cnt in rows:
            w.writerow([chain, desc, cnt])
    codemap = {}
    for chain, desc, cnt in rows:
        for c in chain.split('#'):
            codemap.setdefault(c, (chain, desc))
    with open(os.path.join(outdir, "车次查交路.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["车次", "所在交路链", "车辆描述"])
        for c in sorted(codemap):
            w.writerow([c, codemap[c][0], codemap[c][1]])
    return len(codemap)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "jlb.dat"
    rows = parse_jlb(open(path, "rb").read())
    outdir = os.path.dirname(os.path.abspath(path)) or "."
    ncodes = write_csvs(rows, outdir)
    print(f"交路链: {len(rows)} 条")
    print(f"覆盖车次: {ncodes} 个")
    print(f"含车辆描述: {sum(1 for _, d, _ in rows if d)}/{len(rows)}")
    for chain, desc, cnt in rows[:6]:
        print(f"  [{cnt}趟] {chain[:56]}{'…' if len(chain) > 56 else ''}  <<  {desc[:22]}")
