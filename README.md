# lltskb-tools · 路路通列车数据工具集

抓取 / 解析 **路路通（12306 第三方时刻表 App，包名 `com.lltskb.lltskb`）** 背后的公开列车数据：

- **车辆交路表**（离线，全网 1.1 万+ 车次 / 3100+ 交路链，含普速 K/Z/T + 动车 G/D/C）
- **车型图片**（复兴号/和谐号全型号：整车外观 + 各车厢平面 + 座位实拍 + 编组信息）
- **车次 → 当日实际车底**（动车组，经 12306 车型接口实时查询）

所有数据源均为 **公开、无需登录态**。App 本身只是入口，接口和数据地址在下方 [数据来源](#数据来源) 列明。

> ⚠️ 仅供个人学习/研究铁路数据使用。数据版权归中国铁路及路路通所有，请勿商用或滥发请求。

---

## 目录

| 脚本 | 作用 | 数据来源 |
|---|---|---|
| **`lltskb_sync.py`** | ⭐ 定期同步离线**交路表**（下 `an.db` → 解包 → 解析 `jlb.dat` → CSV），自带回归护栏 | `down.lltskb.com/an.db`（固定地址） |
| `parse_jlb.py` | 独立解析 `jlb.dat` 交路表（`lltskb_sync` 已内置同款逻辑） | 本地 `jlb.dat` |
| `crawl_images.py` | 下载**车型图片**（按 `trainStyle` 去重，分文件夹） | 12306 `getCarDetail` 接口 + 图床 |
| `crawl_route.py` | 全量查**车次 → 当日车底**，按车底分组还原当日交路 | 12306 `getCarDetail` 接口 |
| `tools/hookmod/` | LSPosed 模块（逆向用）：hook 路路通 OkHttp + `java.net.URL`，抓接口参数与图床地址 | — |

---

## 快速开始

### 1. 交路表离线同步（主工具，推荐）

```bash
python3 lltskb_sync.py            # 有更新才下载解析；无变化静默退出
python3 lltskb_sync.py --force    # 强制重下重解析
```

输出（脚本同级 `lltskb_data/`，已被 `.gitignore` 忽略）：

```
lltskb_data/
├── latest/               # 最新一版
│   ├── jlb.dat           # 原始交路表二进制
│   ├── 车次交路.csv       # 交路链 | 车辆描述 | 车次数
│   ├── 车次查交路.csv     # 车次 → 所在交路链 | 车辆描述
│   └── *.dat / *.js      # an.db 内其余离线数据（时刻/站台/经由…）
├── archive/<YYYYMMDD>/   # 按数据构建日期归档，历史可追溯
├── state.json            # 当前版本 / sha256 / 统计
├── sync.log              # 运行日志
└── NEEDS_REVIEW.flag     # 仅在解析异常时出现（见下）
```

**定期运行**（cron，每天一次足够，数据更新不频繁）：

```cron
37 4 * * * /usr/bin/python3 /path/to/lltskb_sync.py >> /path/to/lltskb_data/cron.out 2>&1
```

#### 设计要点

- **只认固定地址 `an.db`**，完全不管 App 更新/热更/发新 APK——该地址永远指向当前 App 配套的最新数据包。
- **靠 sha256 判变**，不依赖版本号是否 bump；内容一变即重解析。
- **回归护栏**：解析结果 `<100 条` 或 `比上次骤降 >40%` → 判定 `jlb.dat` 结构可能随 App 更新改变 → **保留旧 `latest` 不覆盖** + 写 `NEEDS_REVIEW.flag` + 原始包归档待查。平时该文件不存在 = 一切正常；一旦出现 = 需更新 `parse_jlb` 解析逻辑。

### 2. 车型图片下载

```bash
python3 crawl_images.py "G:1-4000,D:1-6000,C:1-2000" 16
```

参数：车次号段（`前缀:起-止` 逗号分隔）、并发数。按 `trainStyle` 去重，每个新车型下整套图到 `车型图片/<车型>/`（外观/车厢/座位/信息 + `_info.json`）。61 个现役动车组型号约 1.8 GB。

### 3. 车次 → 当日车底（交路，实时）

```bash
# 先备好车次清单 all_train_codes.txt（每行一个车次），可从 12306 全量车次表提取：
#   curl -s http://kyfw.12306.cn/otn/resources/js/query/train_list.js -o train_list.js
#   （解析见 crawl_route 注释；只需 G/D/C/S 前缀）
python3 crawl_route.py
```

输出 `车次交路.csv`（车次→车底）与 `交路_按车底分组.txt`（同车底套跑链）。**注意**：这是单日实时快照，仅覆盖动车组；论完整性首选 `lltskb_sync.py` 的离线交路表。

---

## 数据来源

| 用途 | 地址 / 接口 | 鉴权 |
|---|---|---|
| 离线数据包（含交路表） | `http://down.lltskb.com/an.db`（镜像 `http://223.107.87.50:8011/an.db`） | 无 |
| 版本清单 | `http://down.lltskb.com/android.ver` | 无 |
| 车型详情 | `https://mobile.12306.cn/wxxcx/openplatform-inner/miniprogram/wifiapps/appFrontEnd/v2/lounge/open-smooth-common/trainStyleBatch/getCarDetail?trainCode=G18&runningDay=YYYYMMDD&reqType=form&carCode=G18` | **无** |
| 车型图床 | `https://wifi.12306.cn/resourcecenter/cateringimages/<文件名>` | 无 |
| 全量车次表 | `http://kyfw.12306.cn/otn/resources/js/query/train_list.js` | 无 |

数据格式与逆向细节见 [`docs/FINDINGS.md`](docs/FINDINGS.md)。

---

## tools/hookmod（可选，逆向用）

极简 Java LSPosed 模块，用于在真机上确认接口参数与图床地址（当 App 改版、上述接口失效时重新发现用）。需自建 `app/local.properties` 写 `sdk.dir=...`，离线构建：

```bash
cd tools/hookmod && ./gradlew :app:assembleDebug --offline --no-daemon
```

作用域：仅 `com.lltskb.lltskb`。hook `okhttp3.Response$Builder.build`（抓接口 JSON）与 `java.net.URL` 构造（抓图床，因图片走 Glide 的 HttpURLConnection 不走 OkHttp）。日志写到 App 内部 `files/car_hook.log`。

---

## 依赖

纯 Python 3 标准库（`urllib` / `zipfile` / `csv` …），无第三方包。
