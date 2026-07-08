#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量查 车次->车底(carCode)，还原当日交路(同车底套跑的车次链)。"""
import re, json, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DAY = "20260708"
API = ("https://mobile.12306.cn/wxxcx/openplatform-inner/miniprogram/wifiapps/"
       "appFrontEnd/v2/lounge/open-smooth-common/trainStyleBatch/getCarDetail")
UA = "okhttp/5.4.0"

codes = [c.strip() for c in open('all_train_codes.txt') if c.strip()
         and c[0] in ('G', 'D', 'C', 'S')]   # 只查动车组前缀
result = {}          # trainCode -> (carCode, trainStyle, carType)
lock = threading.Lock()

def q(code):
    url = f"{API}?trainCode={code}&runningDay={DAY}&reqType=form&carCode={code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return
    data = (j.get("content") or {}).get("data")
    if not isinstance(data, dict):
        return
    cc = data.get("carCode")
    if cc:
        with lock:
            result[code] = (cc, data.get("trainStyle", ""), data.get("carType", ""))

def main():
    print(f"查询 {len(codes)} 个动车组车次 (日期 {DAY})", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(q, c) for c in codes]
        for _ in as_completed(futs):
            done += 1
            if done % 1000 == 0:
                print(f"  进度 {done}/{len(codes)}, 已获车底 {len(result)}", flush=True)

    # 车次->车底 表
    with open('车次交路.csv', 'w', encoding='utf-8-sig') as f:
        f.write("车次,车底编号,车型,类别\n")
        for code in sorted(result):
            cc, st, ct = result[code]
            f.write(f"{code},{cc},{st},{ct}\n")

    # 按车底分组 = 当日交路链
    groups = {}
    for code, (cc, st, ct) in result.items():
        groups.setdefault(cc, []).append(code)
    multi = {cc: v for cc, v in groups.items() if len(v) > 1}
    with open('交路_按车底分组.txt', 'w', encoding='utf-8') as f:
        f.write(f"# 当日交路 {DAY}: 共 {len(result)} 车次有车底, {len(groups)} 个车底, "
                f"其中 {len(multi)} 个车底当日担当多车次(套跑链)\n\n")
        def keyf(c):
            v = groups[c]
            return (-len(v), c)
        for cc in sorted(groups, key=keyf):
            v = sorted(groups[cc], key=lambda x: (x[0], int(re.sub(r'\D','',x) or 0)))
            st = result[v[0]][1]
            f.write(f"{cc}  [{st}]  ({len(v)}车次): {' → '.join(v)}\n")

    print(f"\n完成: {len(result)} 车次拿到车底; {len(groups)} 个车底; "
          f"{len(multi)} 个车底当日跑多趟(交路链)", flush=True)
    print("输出: 车次交路.csv / 交路_按车底分组.txt", flush=True)
    # 预览套跑最多的前 15
    for cc in sorted(multi, key=lambda c: -len(multi[c]))[:15]:
        v = groups[cc]
        print(f"  {cc} [{result[v[0]][1]}] {len(v)}趟: {' → '.join(sorted(v))}", flush=True)

if __name__ == "__main__":
    main()
