#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枚举 12306 车型图片：按车次号段扫 getCarDetail，按 trainStyle 去重，
每见到一个新车型就把整套图下载到 车型图片/<trainStyle>/ 下。
API 与图床均无需登录态。
"""
import sys, os, re, json, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

DAY = "20260708"
API = ("https://mobile.12306.cn/wxxcx/openplatform-inner/miniprogram/wifiapps/"
       "appFrontEnd/v2/lounge/open-smooth-common/trainStyleBatch/getCarDetail")
IMGBASE = "https://wifi.12306.cn/resourcecenter/cateringimages/"
UA = "okhttp/5.4.0"
OUTROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "车型图片")

seen_style = {}          # trainStyle -> sample trainCode
seen_lock = threading.Lock()
img_cache = set()        # 已下载的图片文件名(跨车型去重)
img_lock = threading.Lock()

def http_get(url, timeout=20, binary=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "ignore")

def get_car_detail(code):
    url = f"{API}?trainCode={code}&runningDay={DAY}&reqType=form&carCode={code}"
    try:
        txt = http_get(url)
    except Exception:
        return None
    try:
        j = json.loads(txt)
    except Exception:
        return None
    c = j.get("content") or {}
    data = c.get("data")
    if not data or c.get("status") not in (0, None):
        return None
    if not isinstance(data, dict):
        return None
    return data

def safe(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()

def download_style(style, cartype, data, code):
    folder = os.path.join(OUTROOT, safe(f"{style}"))
    os.makedirs(folder, exist_ok=True)
    # 元数据
    with open(os.path.join(folder, "_info.json"), "w", encoding="utf-8") as f:
        json.dump({"trainStyle": style, "carType": cartype,
                   "sampleTrainCode": code, "raw": data},
                  f, ensure_ascii=False, indent=2)
    tasks = []  # (localname, filename)
    carpic = data.get("carPic")
    if carpic:
        tasks.append((f"外观_{carpic}", carpic))
    for it in data.get("coachPicList") or []:
        fn = it.get("pictureUrl");  nm = safe(it.get("pictureName", ""))
        if fn: tasks.append((f"车厢_{it.get('picOrder',0):02d}_{nm}_{fn}", fn))
    for it in data.get("coachDetailPicList") or []:
        fn = it.get("pictureUrl");  nm = safe(it.get("pictureName", ""))
        if fn: tasks.append((f"座位_{nm}_{fn}", fn))
    for it in data.get("carInfo") or []:
        fn = it.get("pictureUrl");  nm = safe(it.get("pictureName", ""))
        val = safe(str(it.get("pictureValue", "")))
        if fn: tasks.append((f"信息_{nm}_{val}_{fn}", fn))
    ok = 0
    for localname, fn in tasks:
        dst = os.path.join(folder, safe(localname))
        if os.path.exists(dst):
            ok += 1; continue
        try:
            b = http_get(IMGBASE + fn, timeout=40, binary=True)
            if b and len(b) > 200:
                with open(dst, "wb") as f: f.write(b)
                ok += 1
        except Exception:
            pass
    return len(tasks), ok

def worker(code):
    data = get_car_detail(code)
    if not data:
        return None
    style = data.get("trainStyle") or data.get("carCode") or "UNKNOWN"
    cartype = data.get("carType", "")
    with seen_lock:
        if style in seen_style:
            return None
        seen_style[style] = code
    total, ok = download_style(style, cartype, data, code)
    msg = f"[新车型] {style}  ({cartype})  via {code}  图 {ok}/{total}"
    print(msg, flush=True)
    return style

def gen_codes(spec):
    # spec 例: "G:1-1500,D:1-1500,C:1-800"
    codes = []
    for part in spec.split(","):
        pfx, rng = part.split(":")
        a, b = rng.split("-")
        for n in range(int(a), int(b) + 1):
            codes.append(f"{pfx}{n}")
    return codes

def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "G:1-800,D:1-800,C:1-400"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    codes = gen_codes(spec)
    os.makedirs(OUTROOT, exist_ok=True)
    print(f"扫描 {len(codes)} 个车次, 并发 {workers}, 日期 {DAY}", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker, c) for c in codes]
        for fu in as_completed(futs):
            done += 1
            if done % 500 == 0:
                print(f"  ...进度 {done}/{len(codes)}, 已发现车型 {len(seen_style)}", flush=True)
    print(f"\n完成。发现 {len(seen_style)} 个车型:", flush=True)
    for s, c in sorted(seen_style.items()):
        print(f"  {s}  (via {c})", flush=True)

if __name__ == "__main__":
    main()
