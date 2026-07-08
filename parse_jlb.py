#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析路路通离线交路表 jlb.dat。

jlb.dat 是二进制：车型/车辆描述 与 交路链 交替排列，被控制字节(<0x20)分隔。
交路链 = 若干车次用 '#' 连接（'/' 表同一车次往返编号，如 Z158/5）。
每条交路链关联其前最近出现的车辆描述。

用法: python3 parse_jlb.py [jlb.dat 路径]   默认 ./jlb.dat
输出: 车次交路.csv / 车次查交路.csv（与 jlb.dat 同目录）
"""
import sys, os, re, csv

# 车次前缀白名单：DJ(动检) + 单字母真实前缀(C/D/G/J/K/L/P/S/T/Y/Z)，纯数字车次前缀可空。
# 不能用 [A-Z]? —— 会把描述里的 AC380V/DC600V 当成车次；也不能只用单字母 —— 会把 DJ 截断丢链。
_CODE = r'(?:DJ|[CDGJKLPSTYZ])?\d{1,5}(?:/\d+)?'
CHAIN = re.compile(_CODE + r'(?:#' + _CODE + r')+')
CJK = re.compile(r'[一-鿿]')
CARTYPE = re.compile(r'^\d{2}[A-Z]')


def parse_jlb(raw):
    """返回 [(交路链, 车辆描述, 车次数)]，按控制字节切片，完整不丢长链。"""
    runs = re.split(rb'[\x00-\x1f]+', raw)
    rows, last_desc = [], ''
    for rb in runs:
        s = rb.decode('utf-8', 'ignore')
        if len(s) < 2:
            continue
        m = CHAIN.search(s)
        if m and '#' in m.group():
            # 清理：去掉噪声段(空 / 独立 '0')
            parts = [p for p in m.group().split('#') if p and p != '0']
            if len(parts) >= 2:
                rows.append(('#'.join(parts), last_desc, len(parts)))
            continue
        # 车辆描述：含中文，或形如 25T/25G/25B 的车型代码
        if CJK.search(s) or CARTYPE.match(s):
            # 去掉可能泄漏进来的前导长度字节(单个 ASCII 符号)
            last_desc = s.lstrip('+*!"$%&\'().-/ ').strip()
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
    raw = open(path, "rb").read()
    rows = parse_jlb(raw)
    outdir = os.path.dirname(os.path.abspath(path)) or "."
    ncodes = write_csvs(rows, outdir)
    print(f"交路链: {len(rows)} 条")
    print(f"覆盖车次: {ncodes} 个")
    withdesc = sum(1 for _, d, _ in rows if d)
    print(f"含车辆描述: {withdesc}/{len(rows)}")
    print("样本:")
    for chain, desc, cnt in rows[:8]:
        print(f"  [{cnt}趟] {chain[:60]}{'…' if len(chain) > 60 else ''}  <<  {desc[:24]}")
