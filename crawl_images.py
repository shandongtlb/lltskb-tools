#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枚举 12306 车型数据/图片：按车次号段扫 getCarDetail，按 trainStyle 去重，
每见到一个新车型：写 车型图片/<trainStyle>/_info.json（结构化数据）+ 整套图，
跑完自动汇总所有车型 → 车型详情.csv（编组/长度/定员/时速/餐车/各设施车厢
+ 座位类型 + 编组明细，后两列来自 coachDetailPicList/coachPicList）。
副产物：把每趟车的 车次→车型 落 车次车型.csv（零额外请求，捡去重时丢掉的数据），
供 join_cartype.py 离线合到交路表。API 与图床均无需登录态。

用法:
  python3 crawl_images.py "G:1-4000,D:1-6000,C:1-2000" 16   # 指定号段：下图 + _info.json + 汇总CSV
  python3 crawl_images.py --all                              # 全扫全拉(G/D/C 全号段)，下图+CSV
  python3 crawl_images.py --all --no-img                     # 全量但只出CSV，不下图(省~1.8G)
参数：车次号段(前缀:起-止, 逗号分隔)、并发数；
      --all    全扫 G/D/C:1-9000(普速无车型数据，不扫)，可跟并发数 如 `--all 24`；
      --no-img 跳过图片(只抓数据+出CSV)；
      --day YYYYMMDD  覆盖 runningDay(默认当天，某些车次当天不开时指定次日)。
"""
import sys, os, re, json, csv, glob, datetime, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

NO_IMG = False           # --no-img: 只抓 getCarDetail 数据(_info.json)+出CSV，不下图
DAY = datetime.date.today().strftime("%Y%m%d")  # runningDay 默认当天，--day YYYYMMDD 可覆盖

API = ("https://mobile.12306.cn/wxxcx/openplatform-inner/miniprogram/wifiapps/"
       "appFrontEnd/v2/lounge/open-smooth-common/trainStyleBatch/getCarDetail")
IMGBASE = "https://wifi.12306.cn/resourcecenter/cateringimages/"
UA = "okhttp/5.4.0"
OUTROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "车型图片")

seen_style = {}          # trainStyle -> sample trainCode
seen_lock = threading.Lock()
img_cache = set()        # 已下载的图片文件名(跨车型去重)
img_lock = threading.Lock()
code_map = {}            # 车次 -> (trainStyle, carType, 当日carCode)：每趟都记(不去重)，
code_lock = threading.Lock()  # 供 join_cartype.py 离线 join 交路表。零额外请求，纯捡漏。

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
    if NO_IMG:
        return len(tasks), 0
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
    with code_lock:  # 每趟车都记下 车次→车型(捡漏)，不受下面按车型去重影响
        code_map[code] = (style, cartype, data.get("carCode", ""))
    with seen_lock:
        if style in seen_style:
            return None
        seen_style[style] = code
    total, ok = download_style(style, cartype, data, code)
    tag = "仅数据" if NO_IMG else f"图 {ok}/{total}"
    print(f"[新车型] {style}  ({cartype})  via {code}  {tag}", flush=True)
    return style

def _join_names(items, sep):
    """把 coachPicList/coachDetailPicList 的 pictureName 拼成一列。"""
    return sep.join((it.get("pictureName") or "").strip()
                    for it in (items or []) if (it.get("pictureName") or "").strip())


def build_csv():
    """汇总 OUTROOT 下所有 _info.json → 车型详情.csv（一行一车型）。
    列 = 车型/类型/样本车次/样例车底/车厢数 + 动态 carInfo(编组/长度/定员/时速/餐车/各设施)
       + 座位类型(coachDetailPicList，各座别及描述) + 编组明细(coachPicList，各车厢座位分布)。
    后两列数据本就在 _info.json 里(getCarDetail 返回)，零额外请求。"""
    rows, cols = [], []
    for jf in sorted(glob.glob(os.path.join(OUTROOT, "*", "_info.json"))):
        try:
            d = json.load(open(jf, encoding="utf-8"))
        except Exception:
            continue
        raw = d.get("raw", {})
        r = {"车型": d.get("trainStyle"), "类型": d.get("carType"),
             "样本车次": d.get("sampleTrainCode"),
             "样例车底": raw.get("carCode", ""),
             "车厢数": len(raw.get("coachPicList", []))}
        for x in raw.get("carInfo", []):
            k, v = x.get("pictureName"), x.get("pictureValue")
            if k:
                r[k] = v
                if k not in cols:
                    cols.append(k)
        r["座位类型"] = _join_names(raw.get("coachDetailPicList"), "/")
        r["编组明细"] = _join_names(raw.get("coachPicList"), " | ")
        rows.append(r)
    if not rows:
        return None, 0
    header = ["车型", "类型", "样本车次", "样例车底", "车厢数"] + cols + ["座位类型", "编组明细"]
    outpath = os.path.join(os.path.dirname(OUTROOT), "车型详情.csv")
    with open(outpath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return outpath, len(rows)


def write_code_style():
    """把每趟车的 车次→车型 落到 车次车型.csv（脚本同级），供 join_cartype.py 离线合表。
    这是本次扫描的副产物——零额外请求，捡的是 getCarDetail 本就返回、去重时被丢掉的数据。"""
    if not code_map:
        return None, 0
    outpath = os.path.join(os.path.dirname(OUTROOT), "车次车型.csv")
    with open(outpath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["车次", "车型", "类型", "当日车底", "查询日期"])
        for code in sorted(code_map):
            style, cartype, carcode = code_map[code]
            w.writerow([code, style, cartype, carcode, DAY])
    return outpath, len(code_map)


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
    global NO_IMG, DAY
    argv = list(sys.argv[1:])
    if "--no-img" in argv:
        NO_IMG = True; argv.remove("--no-img")
    if "--csv" in argv:  # CSV 默认就会生成，此 flag 仅为语义显式，接受不报错
        argv.remove("--csv")
    if "--day" in argv:  # 覆盖 runningDay(默认当天)，如某些车次当天不开可指定次日
        di = argv.index("--day"); DAY = argv[di + 1]; del argv[di:di + 2]
    if "--all" in argv:  # 全扫全拉：G/D/C 全号段(普速无车型数据，不扫)
        argv.remove("--all")
        spec = "G:1-9000,D:1-9000,C:1-9000"
        workers = int(argv[0]) if argv else 16
    else:
        spec = argv[0] if len(argv) > 0 else "G:1-800,D:1-800,C:1-400"
        workers = int(argv[1]) if len(argv) > 1 else 12
    codes = gen_codes(spec)
    os.makedirs(OUTROOT, exist_ok=True)
    print(f"扫描 {len(codes)} 个车次, 并发 {workers}, 日期 {DAY}"
          f"{'  [--no-img 只抓数据]' if NO_IMG else ''}", flush=True)
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
    outpath, ncsv = build_csv()
    if outpath:
        print(f"\n✓ 车型详情汇总: {ncsv} 车型 → {outpath}", flush=True)
    cpath, ncode = write_code_style()
    if cpath:
        print(f"✓ 车次→车型对应(捡漏): {ncode} 车次 → {cpath}", flush=True)
        print(f"  离线合表交路: python3 join_cartype.py", flush=True)

if __name__ == "__main__":
    main()
