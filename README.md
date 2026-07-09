# lltskb-tools · 路路通列车数据工具集

抓取 / 解析 **路路通（12306 第三方时刻表 App，包名 `com.lltskb.lltskb`）** 背后的公开列车数据：

- 🟢 **车次时刻表**（**纯离线**，13716 车次：经停站 / 到达 / 发车 / 停留 / 里程 / **站台** / 开行期）
- 🟢 **按车站反查**（**纯离线**，某站停靠的全部车次，含到发时刻 / 站台 / 始发终到）
- 🟢 **车辆交路表**（**离线**，全网 1.6 万+ 车次 / 3600+ 交路链，含普速 K/Z/T + 动车 G/D/C）
- **车型图片**（复兴号/和谐号全型号：整车外观 + 各车厢平面 + 座位实拍 + 编组信息）
- **车次 → 当日实际车底**（动车组，经 12306 车型接口实时查询）

标 🟢 的三项**完全离线、断网可用**（数据来自 `an.db` 离线包，格式经反编译 App 逆向，见 [`docs/FINDINGS.md`](docs/FINDINGS.md)）；车型图片与当日车底走 12306 公开接口。所有数据源均 **公开、无需登录态**，地址见下方 [数据来源](#数据来源)。

> ⚠️ 仅供个人学习/研究铁路数据使用。数据版权归中国铁路及路路通所有，请勿商用或滥发请求。

---

## 目录

| 脚本 | 作用 | 数据来源 |
|---|---|---|
| **`lltskb_sync.py`** | ⭐ 定期同步离线**交路表**（下 `an.db` → 解包 → 解析 `jlb.dat` → CSV），自带回归护栏 | `down.lltskb.com/an.db`（固定地址） |
| `parse_jlb.py` | 独立解析 `jlb.dat` 交路表（`lltskb_sync` 已内置同款逻辑） | 本地 `jlb.dat` |
| **`parse_timetable.py`** | ⭐ **纯离线**解析**车次时刻表**：车次→经停站/到达/发车/停留/里程/**站台**/开行期；`--station` **按车站反查**停靠车次。零联网 | 本地 `t.i`+`s.i`+`t*.dat`+`plat.dat`+`s*.dat` |
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
│   ├── t*.dat / s*.dat   # 车次时刻 / 车站→车次（parse_timetable.py 用）
│   ├── plat.dat s.i t.i  # 站台 / 站名索引 / 车次索引
│   └── *.dat / *.js      # an.db 内其余离线数据（见「内容一览」）
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

### 2. 车次时刻表 / 车站反查（纯离线，零联网）⭐

从 `lltskb_sync.py` 同步下来的 `latest/` 里直接解析 `t0~t19.dat`，**完全不联网**——正合断网现场使用。

```bash
python3 parse_timetable.py G1              # 查单个车次经停(站/到达/发车/停留/里程/站台/开行期)
python3 parse_timetable.py G1 C1001 1461   # 一次查多个
python3 parse_timetable.py --station 北京南  # 按车站反查停靠车次(-s 亦可)
python3 parse_timetable.py --all           # 全量导出 latest/车次时刻表.csv (13716车次/12万站次, ~1s)
python3 parse_timetable.py --data DIR G1    # 指定数据目录
```

按车站反查输出示例（`--station 延吉西`，按到达排序）：

```
═ 延吉西 停靠车次 72 趟（按到达排序） ═
 车次      到达    发车    站台  始发→终到
 C1002     始发      05:55   1     延吉西→长春
 C1004     06:34   06:37   1     珲春→长春
 C1001     07:40   终到      4     长春→延吉西
 …
```

单查输出示例（`G1`）：

```
═ G1  (index=5936 桶=17 type=6 站数=7  开行 20260127~20501231) ═
 序 站名          到达    发车    停留  里程km 站台
  1 北京南         ----    06:30     -       0  17
  2 沧州西         07:18   07:20    2分     210  2
  …
  7 上海虹桥        11:24   ----      -    1318  14
```

- **数据来源全离线**：`t.i`(车次名) + `s.i`(站名) + `t0~t19.dat`(时刻) + `plat.dat`(站台) + `s*.dat`(车站→车次)，无任何网络请求。
- **全量 CSV 字段**：`车次, 序号, 站名, 到达, 发车, 停留分, 里程km, 站台`（约 12 万站次，可直接导入 Excel / SQLite / DuckDB 二次查询）。
- **站台号**并入输出（覆盖约 74% 站次，高铁/大站全、普速小站常缺）；纯数字站台号，**检票口/候车厅需 12306 在线**，离线库不含。
- 13716 车次 100% 解出；抽查 G/D/C/普速/往返对 12306 真值站名+时刻逐站一致（逆向来自反编译 App，见 [FINDINGS §6](docs/FINDINGS.md)）。
- 车次全集以 `t.i` 为准；已停运/改号车次（如 K1/Z1/T1）本就不在库中。

### 3. 车型图片下载

```bash
python3 crawl_images.py "G:1-4000,D:1-6000,C:1-2000" 16
```

参数：车次号段（`前缀:起-止` 逗号分隔）、并发数。按 `trainStyle` 去重，每个新车型下整套图到 `车型图片/<车型>/`（外观/车厢/座位/信息 + `_info.json`）。61 个现役动车组型号约 1.8 GB。

### 4. 车次 → 当日车底（交路，实时）

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
| 离线数据包（含交路表 + **车次时刻表** `t*.dat` + 站名 `s.i`） | `http://down.lltskb.com/an.db`（镜像 `http://223.107.87.50:8011/an.db`） | 无 |
| 版本清单 | `http://down.lltskb.com/android.ver` | 无 |
| 车型详情 | `https://mobile.12306.cn/wxxcx/openplatform-inner/miniprogram/wifiapps/appFrontEnd/v2/lounge/open-smooth-common/trainStyleBatch/getCarDetail?trainCode=G18&runningDay=YYYYMMDD&reqType=form&carCode=G18` | **无** |
| 车型图床 | `https://wifi.12306.cn/resourcecenter/cateringimages/<文件名>` | 无 |
| 全量车次表 | `http://kyfw.12306.cn/otn/resources/js/query/train_list.js` | 无 |

数据格式与逆向细节见 [`docs/FINDINGS.md`](docs/FINDINGS.md)。

---

## 离线包 `an.db` 内容一览

`an.db` 实为 ZIP（约 2.2MB），解包即全部离线数据。格式经反编译 App 逆向（`ResMgr`/`DataMgr`/`QueryCC`/`QueryCZ`/`PlatformMgr` 等），细节见 [`docs/FINDINGS.md`](docs/FINDINGS.md) §6。关键编码：多字节整数是 **hi×255 + lo**（非 ×256）。

| 文件 | 内容 | 状态 |
|---|---|---|
| `t.i` / `s.i` | 车次名 / 站名索引（`readShort` + N×`readUTF`） | ✅ 已解 |
| `t0~t19.dat` | 车次时刻（桶=`(车次idx+1)%20`，每站 7B） | ✅ `parse_timetable.py` |
| `s0~s9.dat` | 车站→停靠车次（桶=`(站idx+1)%10`） | ✅ `--station` |
| `plat.dat` | 站台号（`车次idx_站idx`→站台，覆盖~74%站次） | ✅ 已并入 |
| `sp.dat` | 车次→12306 `train_no`（`0x0c` 分隔） | ✅ 已解析 |
| `jlb.dat` | 交路（车底套跑） | ✅ `lltskb_sync.py` |
| `station_name.js` | 站名 / 电报码明文 | ✅ 已用 |
| `routes.dat` (1.1M) | 铁路线路→站序+电报码+里程 | 🟡 结构已探明，未做工具 |
| `extra.dat` (89K) | 车次附加：复兴号型号 + 担当企业 | 🟡 部分可见 |
| `xw.dat` (93K) | 新闻/公告文本 | 🟡 未做 |
| `p0~p4.dat` / `pk0~pk9.dat` | 票价系数（普速/动车，受 `isShowPrice` 开关） | 🟡 小，票价在线更准 |
| `ts.dat` / `sch.dat` | 临时票价 / 停运加开调度 | ⚪ **本版为 0 字节（空）** → 离线判不了某车某天停运，需在线 |
| `sn.dat`·`ime.dat`·`t.rule`·`cdn.dat`·`api.dat`·`ver.txt` | 站名子集 / 拼音索引 / 规则 / CDN 配置 / 大屏配置 / 版本号 | ⚪ 配置类，无查询价值 |

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
