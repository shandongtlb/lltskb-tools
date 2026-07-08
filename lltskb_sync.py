#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路路通离线交路数据同步器（极简版）。
只认固定地址 an.db（永远指向最新离线数据包），完全不管 App 更新情况：
  下 an.db → 比 sha256 → 变了就解包 + 解析 jlb.dat 交路表 → 更新 latest
版本标签用 zip 内 jlb.dat 的构建日期。解析器自带防呆：格式变了(解析<100条)
报错并保留旧数据，不会用垃圾覆盖。
用法：python3 lltskb_sync.py [--force]
cron 友好：无变化 exit 0 静默。
"""
import sys, os, re, io, json, hashlib, zipfile, shutil, csv
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "lltskb_data")
ARCH = os.path.join(ROOT, "archive")
LATEST = os.path.join(ROOT, "latest")
STATE = os.path.join(ROOT, "state.json")
LOG = os.path.join(ROOT, "sync.log")

ANDB_URLS = [
    "http://down.lltskb.com/an.db",
    "http://223.107.87.50:8011/an.db",
]
UA = "okhttp/5.4.0"
FORCE = "--force" in sys.argv


def log(msg):
    os.makedirs(ROOT, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_first(urls, timeout=120):
    err = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), u
        except Exception as e:
            err = e
    raise RuntimeError(f"全部地址失败: {err}")


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


# ---------- jlb.dat 交路表解析 ----------
# jlb.dat：车辆描述 与 交路链 交替，被控制字节(<0x20)分隔。按切片提取，完整不丢长链。
_CODE = r'(?:DJ|[CDGJKLPSTYZ])?\d{1,5}(?:/\d+)?'   # DJ=动检; 白名单避免描述里 AC380V 误判
_CHAIN = re.compile(_CODE + r'(?:#' + _CODE + r')+')
_CJK = re.compile(r'[一-鿿]')
_CARTYPE = re.compile(r'^\d{2}[A-Z]')


def parse_jlb(raw):
    runs = re.split(rb'[\x00-\x1f]+', raw)
    rows, last = [], ""
    for rb in runs:
        s = rb.decode("utf-8", "ignore")
        if len(s) < 2:
            continue
        m = _CHAIN.search(s)
        if m and '#' in m.group():
            parts = [p for p in m.group().split('#') if p and p != '0']
            if len(parts) >= 2:
                rows.append(('#'.join(parts), last, len(parts)))
            continue
        if _CJK.search(s) or _CARTYPE.match(s):
            last = s.lstrip('+*!"$%&\'().-/ ').strip()
    return rows


def write_csvs(rows, outdir):
    with open(os.path.join(outdir, "车次交路.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["交路链", "车辆描述", "车次数"])
        for chain, desc, cnt in rows:
            w.writerow([chain, desc, cnt])
    codemap = {}
    for chain, desc, cnt in rows:
        for c in chain.split('#'):
            codemap.setdefault(c, (chain, desc))
    with open(os.path.join(outdir, "车次查交路.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["车次", "所在交路链", "车辆描述"])
        for c in sorted(codemap):
            w.writerow([c, codemap[c][0], codemap[c][1]])
    return len(codemap)


def data_version(zf):
    """用 zip 内 jlb.dat 的构建日期做版本标签，取不到则用当天。"""
    for zi in zf.infolist():
        if zi.filename.lower().endswith("jlb.dat"):
            y, m, d = zi.date_time[:3]
            return f"{y:04d}{m:02d}{d:02d}"
    return datetime.now().strftime("%Y%m%d")


def main():
    os.makedirs(ARCH, exist_ok=True)
    st = load_state()

    try:
        andb, src = fetch_first(ANDB_URLS)
    except Exception as e:
        log(f"ERROR 下载 an.db 失败: {e}")
        return 2
    sha = hashlib.sha256(andb).hexdigest()

    if sha == st.get("andb_sha") and not FORCE:
        log(f"无变化 (data={st.get('data')}, sha={sha[:8]})。跳过。")
        return 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(andb))
    except Exception as e:
        log(f"ERROR an.db 不是有效 zip(格式可能变了): {e}")
        return 3
    ver = data_version(zf)
    log(f"检测到更新: sha {(st.get('andb_sha') or '')[:8]}→{sha[:8]}, 数据版本 {ver} (源 {src})")

    outdir = os.path.join(ARCH, ver)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "an.db"), "wb") as f:
        f.write(andb)
    try:
        zf.extractall(outdir)
    except Exception as e:
        log(f"ERROR 解压失败: {e}")
        return 3
    jlb_path = os.path.join(outdir, "jlb.dat")
    if not os.path.exists(jlb_path):
        log("ERROR 包内未找到 jlb.dat(结构可能变了)")
        return 3

    rows = parse_jlb(open(jlb_path, "rb").read())
    # 解析质量校验：链内每个 token 都是合法车次(chain_re 已保证)，再看数量与占比
    codes_per_chain = [c for chain, _, _ in rows for c in chain.split('#')]
    prev_chains = st.get("chains", 0)
    # 回归护栏：绝对下限 + 相对上次骤降(>40%)都判可疑，拒绝覆盖 latest（原始 an.db 已归档可供复核）
    suspicious = (len(rows) < 100) or (prev_chains and len(rows) < prev_chains * 0.6)
    if suspicious:
        log(f"⚠️ 解析结果可疑: 本次 {len(rows)} 链, 上次 {prev_chains} 链 "
            f"(阈值: <100 或 <上次60%)。jlb.dat 结构可能已随 App 更新改变。"
            f"【已保留旧 latest 不覆盖】原始包在 {outdir}/an.db 待复核。")
        # 记录待复核标记，但不动 state/latest
        open(os.path.join(ROOT, "NEEDS_REVIEW.flag"), "w", encoding="utf-8").write(
            f"{datetime.now():%Y-%m-%d %H:%M:%S} 数据版本 {ver} sha {sha[:12]} "
            f"解析仅 {len(rows)} 链(上次 {prev_chains})，疑似结构变更，需更新 parse_jlb。\n"
            f"原始包: {outdir}/an.db\n")
        return 4
    ncodes = write_csvs(rows, outdir)
    # 结构正常则清掉可能存在的旧告警标记
    flag = os.path.join(ROOT, "NEEDS_REVIEW.flag")
    if os.path.exists(flag):
        os.remove(flag)
    log(f"✓ 解析成功: {len(rows)} 交路链 / {ncodes} 车次 → {outdir}")

    if os.path.isdir(LATEST):
        shutil.rmtree(LATEST)
    shutil.copytree(outdir, LATEST)

    json.dump({"data": ver, "andb_sha": sha,
               "updated": datetime.now().isoformat(timespec="seconds"),
               "chains": len(rows), "codes": ncodes},
              open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"✓ 同步完成 → {LATEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
