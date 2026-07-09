#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线合表：把 crawl_images.py 顺手落的 车次车型.csv（12306 实际车型，当日快照）
join 到 车次查交路.csv（路路通离线交路 + 描述抽取车型），产出对照表：
  车次 | 所在交路链 | 描述抽取车型(离线) | 实际车型(12306) | 类型 | 当日车底 | 是否一致

——纯离线：只读两张已有 CSV，零联网。
  · 车次查交路.csv 由 lltskb_sync.py / parse_jlb.py 生成（离线交路 + 描述抽取车型）。
  · 车次车型.csv   由 crawl_images.py --all 生成（有网时跑一次，零额外请求捡漏）。
getCarDetail 只覆盖动车组 G/D/C，普速无实际车型 → 该列留空，以描述抽取为准。
「实际车型」是查询当日的车底快照，会随换底/检修变动；描述车型是路路通相对静态的配属。

用法:
  python3 join_cartype.py
  python3 join_cartype.py --route <车次查交路.csv> --style <车次车型.csv> --out <车次车型对照.csv>
"""
import sys, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))


def fuzzy_same(a, b):
    """描述车型 vs 实际车型 是否一致。一方缺 → None(无法判定)。
    允许前缀包含：描述 CR400BF 对实际 CR400BF-S 视为一致（同族，仅粒度差）。"""
    if not a or not b:
        return None
    a, b = a.upper(), b.upper()
    return a == b or a.startswith(b) or b.startswith(a)


def load_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main(argv):
    route = os.path.join(HERE, "lltskb_data", "latest", "车次查交路.csv")
    style = os.path.join(HERE, "车次车型.csv")
    out = os.path.join(HERE, "车次车型对照.csv")
    i = 0
    while i < len(argv):
        if argv[i] == "--route":
            route = argv[i + 1]; i += 2
        elif argv[i] == "--style":
            style = argv[i + 1]; i += 2
        elif argv[i] == "--out":
            out = argv[i + 1]; i += 2
        else:
            i += 1

    if not os.path.exists(route):
        print("找不到交路表: %s\n先跑 lltskb_sync.py 生成 latest/车次查交路.csv" % route)
        return
    if not os.path.exists(style):
        print("找不到 车次车型.csv: %s\n有网时先跑一次 `python3 crawl_images.py --all`"
              "（或 --no-img 只出数据）即可生成该副产物。" % style)
        return

    styles = {r["车次"]: r for r in load_csv(style)}
    routerows = load_csv(route)

    n = same = diff = actual_only = no_online = 0
    mism = []
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["车次", "所在交路链", "描述抽取车型", "实际车型", "类型", "当日车底", "是否一致"])
        for r in routerows:
            code = r["车次"]
            desc_model = r.get("车型", "")
            s = styles.get(code)
            actual = s.get("车型", "") if s else ""
            cartype = s.get("类型", "") if s else ""
            carcode = s.get("当日车底", "") if s else ""
            flag = fuzzy_same(desc_model, actual)   # True/False/None(至少一方缺)
            mark = "" if flag is None else ("✓" if flag else "✗")
            w.writerow([code, r.get("所在交路链", ""), desc_model, actual, cartype, carcode, mark])
            n += 1
            if not actual:                 # 普速或当日无 getCarDetail 数据
                no_online += 1
            elif not desc_model:           # 实际有、路路通描述没抽到车型
                actual_only += 1
            elif flag:
                same += 1
            else:
                diff += 1
                mism.append((code, desc_model, actual))

    print("合表完成: %d 车次 → %s" % (n, out))
    print("  两者都有车型: %d（一致 %d / 不一致 %d）" % (same + diff, same, diff))
    print("  仅实际有(路路通描述未抽到): %d" % actual_only)
    print("  无 12306 实际车型(普速 / 当日不开): %d" % no_online)
    if mism:
        print("  不一致(路路通描述 ≠ 12306 当日实际，多为换代/换底/滞后) 示例:")
        for code, d, a in mism[:15]:
            print("    %-7s 描述[%s]  实际[%s]" % (code, d, a))
        if len(mism) > 15:
            print("    …共 %d 条，详见 CSV「是否一致」列筛 ✗" % len(mism))


if __name__ == "__main__":
    main(sys.argv[1:])
