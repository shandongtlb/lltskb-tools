#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析路路通离线交路表 jlb.dat：长度前缀分帧，配对(车辆描述, 交路链)。"""
import re, csv

raw = open('andb/jlb.dat', 'rb').read()

# 长度前缀扫描：位置 i 处取 1 字节 L(1..63)，其后 L 字节若为合法可读串则作为 token
def is_readable(b):
    try:
        s = b.decode('utf-8')
    except Exception:
        return None
    # 允许中文、字母数字、常见标点
    if all(ord(ch) >= 0x20 or ch in '' for ch in s):
        if not any(ord(ch) < 0x20 for ch in s):
            return s
    return None

tokens = []  # (pos, str)
i, n = 0, len(raw)
while i < n:
    L = raw[i]
    if 2 <= L <= 63 and i + 1 + L <= n:
        s = is_readable(raw[i+1:i+1+L])
        if s and len(s) >= 2:
            tokens.append((i, s))
            i += 1 + L
            continue
    i += 1

# 分类
chain_re = re.compile(r'^[A-Z]?\d{1,5}(?:/\d+)?(?:#[A-Z]?\d{1,5}(?:/\d+)?)+$')
def is_chain(s):
    return bool(chain_re.match(s))
def is_desc(s):
    return ('型' in s) or ('供风' in s) or ('AC380' in s) or ('DC600' in s) or ('集便' in s)

# 配对：每条链关联最近一次出现的描述
rows = []
last_desc = ''
for pos, s in tokens:
    if is_desc(s):
        last_desc = s
    elif is_chain(s):
        codes = s.split('#')
        rows.append((s, last_desc, len(codes)))

# 输出 CSV
with open('车次交路_路路通离线.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交路链', '车辆描述', '车次数'])
    for chain, desc, cnt in rows:
        w.writerow([chain, desc, cnt])

# 车次->交路链 反查表
codemap = {}
for chain, desc, cnt in rows:
    for c in chain.split('#'):
        codemap.setdefault(c, []).append((chain, desc))
with open('车次查交路_路路通离线.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['车次', '所在交路链', '车辆描述'])
    for c in sorted(codemap):
        chain, desc = codemap[c][0]
        w.writerow([c, chain, desc])

allcodes = set(codemap)
from collections import Counter
pref = Counter(re.match(r'([A-Z]?)', c).group(1) or '数字' for c in allcodes)
print(f"交路链: {len(rows)} 条")
print(f"覆盖车次: {len(allcodes)} 个")
print(f"车次首字母分布: {dict(pref)}")
print(f"含车辆描述的链: {sum(1 for _,d,_ in rows if d)} / {len(rows)}")
print("\n样本(链 | 描述):")
for chain, desc, cnt in rows[:12]:
    print(f"  [{cnt}趟] {chain}  <<  {desc[:30]}")
print("\n输出: 车次交路_路路通离线.csv / 车次查交路_路路通离线.csv")
