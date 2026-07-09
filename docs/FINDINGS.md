# 逆向发现记录

记录数据来源的格式与关键细节，便于 App 改版后快速修复。

## 1. 离线数据包 `an.db`

- 固定地址：`http://down.lltskb.com/an.db`（镜像 `http://223.107.87.50:8011/an.db`），约 2.2 MB。
- **实为 ZIP**（`PK\x03\x04` 头，尽管扩展名是 `.db`）。解压得全部离线数据文件：
  - `jlb.dat`（交路表，见下）
  - `plat.dat`（站台）、`routes.dat`（经由）、`sp.dat`、`t*.dat` / `s*.dat`（时刻分片）、`station_name.js`、`xw.dat`、`extra.dat` 等。
- 版本标签取 ZIP 内 `jlb.dat` 的构建日期（entry mtime），比 `android.ver` 的 `data` 字段更真实（后者偏向 App 发布日）。

## 2. 交路表 `jlb.dat`

- **明文二进制，未加密**。车辆描述 与 交路链 交替排列，之间以控制字节(<0x20)分隔（并夹杂少量长度/序号字节）。
- 两类关键 token：
  - **车辆描述**：含中文（`型`/`供风`/`集便`/`调向`…）或车型代码 `25T`/`25G`/`25B`，如 `25T型，AC380V，双管供风，集便`、`CR400AF型重联`。
  - **交路链**：车次用 `#` 连接，如 `K7232#K7231#K7234#K7233`；`/` 表同一车次的往返编号，如 `Z158/5#Z157/6`。
- 配对规则：每条交路链关联**其前最近一次出现**的车辆描述。
- 规模（2026-07 版）：约 **3659 条交路链、覆盖 16570 个车次**，含 G/D/C/S/K/Z/T/Y/L/P/J/DJ。
- App 内加载类：`com.lltskb.lltskb.engine.JlbDataMgr`（`JlbDataMgr$JLB`）。

**解析踩过的坑（务必按此实现，否则漏数据；每个都是实测漏了具体车次才发现的）：**
1. ❌ 「1 字节长度前缀分帧」逐条读 → **>63 字节的长链（几十站套跑）整条被跳过**，漏 ~15%。
   ✅ 改为**按控制字节 `[\x00-\x1f]+` 切片**再分类。
2. ❌ 车次前缀 `[A-Z]?`（单字母）→ **`DJ`（动检车，如 `DJ5893`）截断整条链**，后半段全丢（漏了 G1078）。
   ❌ 放成 `[A-Z]{0,2}` 又把描述里 `AC380V`/`DC600V` 误当车次。→ ✅ 白名单 `(?:DJ|[CDGJKLPSTYZ])?`。
3. ❌ 交路里有**前导 0 占位符**（`…#0C1022#…`）→ 在 `#0` 处截断。✅ 允许可选前导 `0`，清洗时归一化去掉（`0C1022`→`C1022`）。
4. ❌ 更冷门脏格式：**双斜杠** `D632/3/2`、**全角字母** `Ｄ4595`、**斜杠连两整车次** `C6842/C6843`。
   ✅ 斜杠段用 `(?:/…)*`（多段）；每 run 先 `unicodedata.normalize('NFKC')`（全角→半角）；斜杠段带字母则拆为独立车次、纯数字则当往返简写保留（`Z158/5`）。
- 当前正则（见 `parse_jlb.py` `_CODE`/`CHAIN`）：
  `_CODE = 0?(?:DJ|[CDGJKLPSTYZ])?\d{1,5}(?:/(?:DJ|[CDGJKLPSTYZ])?\d+)*`
- 完整性自检：对比"原始所有 #-链里的车次"与 CSV，残差 ~0（仅极个别畸形记录，<0.03%）。

> 若 App 改版导致此格式变化，`lltskb_sync.py` 的回归护栏会拦下（解析骤降），届时按上述结构在真机 hook `JlbDataMgr` 复核新格式。

## 3. 车型接口 `getCarDetail`

- `GET .../trainStyleBatch/getCarDetail?trainCode=G18&runningDay=YYYYMMDD&reqType=form&carCode=G18`
- **无需任何 cookie/token/签名。** 三个必带：`trainCode`（车次）、`runningDay`（YYYYMMDD，缺它报"系统错误"）、`reqType=form`、`carCode`（=车次号本身）。
- 响应 `content.data`：
  - `trainStyle`（车型，如 `CR400BF-B`）、`carType`（复兴号/和谐号）、`carCode`（当日具体车底，如 `CR400BF-B-5098`）
  - `carPic`（整车外观图文件名）
  - `coachPicList[]`：各车厢平面图 `{picOrder, pictureUrl, pictureName:"01车 商务 17"}`
  - `coachDetailPicList[]`：座位实拍 `{pictureUrl, pictureName:"商务座"}`
  - `carInfo[]`：编组/长度/定员/最高时速/餐车位置等 `{pictureName, pictureValue, pictureUrl}`
- 只覆盖动车组（G/D/C）；普速无数据。

## 4. 图床

- `https://wifi.12306.cn/resourcecenter/cateringimages/<pictureUrl>`
- 上面 JSON 里所有 `pictureUrl` / `carPic` 文件名都拼这个 base。返回 6–7 MB 高清 PNG/JPG。
- App 端图片经 **Glide 默认 `HttpUrlFetcher`（HttpURLConnection）** 加载，不走 OkHttp——故 hook 抓图床要 hook `java.net.URL` 构造函数。

## 5. 其他接口（App 内出现，未深用）

- `mobile.12306.cn/.../queryTrainDiagram`（编组图）、`travelServiceQrcodeTrainInfo`、`bigScreen/queryTrainByStation`
- `an.db` 同级还有 `api.dat`（552B，base64 + 单字节异或 key=0x63，解出为"车站大屏" cx9z.com 配置，与交路无关）。

## 6. 车次时刻表 `t0.dat`~`t19.dat`（纯离线，已完全逆向 + 设备真值验证）

由反编译 App（`com.lltskb.lltskb.engine` 的 `ResMgr` / `DataMgr` / `QueryBase.getTrainTimeDTO`）抄出，非盲猜。解析实现见 `parse_timetable.py`，13716 车次 100% 解出，抽查 G/D/C/普速/往返 对 12306 真值站名+时刻逐站一致。

### 6.1 索引文件 `.i`（Java `DataInputStream` 格式）
- `t.i` / `s.i` 结构 = `readShort()`(记录数) + N×`readUTF()`（每条 = 2 字节大端长度 + UTF-8）。
- `t.i`：**车次全局 index → 车次名**，13716 条，含全类型（G/D/C/S/K/Y/Z/T + 纯数字），往返车次名形如 `4167/4170`、`Z158/5`。
- `s.i`：**站点 index → 站名**，3304 条。**时刻表里的站就用这个 index。**
- `getIndex(name)` App 内是二分查找（`/name/` 拼接比较），本工具用 dict 精确 + 往返分段匹配。

### 6.2 关键编码：路路通 2 字节整数 = **hi×255 + lo**（不是 ×256！）
全库所有 2 字节整数都是 `(b[i]&0xFF)*255 + (b[i+1]&0xFF)`。**这是之前 be16/le16/varint 全部搜不中的根因。** 源自 App `DataMgr.OooOOo0(byte[],int)`。

### 6.3 车次记录定位（桶 + 顺扫）
- **桶号 = (车次全局 index + 1) % 20** → 打开 `t{桶}.dat`（离线包大写 `T{桶}.dat`，同文件）。
- 桶文件 = 连续记录，每条 = `[2B 车次index(hi×255+lo)]` + `trainInfo 体`。
- **下一条偏移 = cur + 17 + 站数×7**（站数 = 记录内 `[15..16]`）。顺扫到记录头 == 目标 index 即命中。
  （源码 `DataMgr.OooO0oO`：`i2 = i2 + 17 + u255(data,i2+15)*7`）

### 6.4 trainInfo 体结构
| 偏移 | 字段 | 说明 |
|---|---|---|
| `[0]` | type | 车次类型码 |
| `[1..2]` | priceNo | 票价表号(hi×255+lo) |
| `[3..6]` | startDate | 7bit×4 打包(`b0+b1×128+b2×16384+b3×2097152`)，解出 = **YYYYMMDD** 开行起 |
| `[7..10]` | endDate | 同上，开行止（如 `20991231`=长期） |
| `[11..12]` | ? | 未定 |
| `[13..14]` | 站数 | hi×255+lo |
| `[15..]` | 站序列 | 每站 **7 字节**，见下 |

### 6.5 站节点（每站 7 字节）
| 偏移 | 字段 | 说明 |
|---|---|---|
| `[0..1]` | 站 index | hi×255+lo → `s.i` 站名 |
| `[2]` | 到达时 | 首站为发车时（App 首站到达显示 ----） |
| `[3]` | 到达分 | |
| `[4]` | 停留分 | **发车时刻 = 到达 + 停留分**；首/末站为 0 |
| `[5..6]` | 里程 km | hi×255+lo，自始发累计（京沪 1461 末站=1463 ✓） |

- `startDate/endDate` 决定车次在某查询日是否有效（App `outOfDateFlag`）；本工具原样解为 YYYYMMDD。
- **未收录的车次**（如某版本已停运/改号的 K1/Z1/T1）在 `t.i` 中根本不存在，不是解析漏项 —— 以 `t.i` 车次全集为准。
- 附带：`sp.dat` = 车次 index → 12306 `train_no`（`0x0c` 分隔，顺序同 `t.i`）。`s0~s9.dat` 车站维度（站→停靠车次）见 §6.7。

### 6.6 站台 `plat.dat`（车次×站 → 站台号）
- 源码 `PlatformMgr`（extends `DataMgr`）。结构：`[4B 条目数]` + N×`([4B 车次idx][4B 站idx][1B 长度][UTF8])`。
  **注意：这里整数是标准大端 4 字节**（`DataMgr.OooOOOO`），不是 hi×255+lo。
- `key = 车次idx + "_" + 站idx → 站台号`；`getPlatform(车次idx, 站idx)`。
- 2026-07 版：128052 条，值全是纯数字站台号（"1"~约"60"，60 种）。**无检票口文字**——检票口/候车厅是在线数据（App `QueryTicketCheck` / `BigScreenModel`）。
- 覆盖率约 73.8% 站次：**高铁/大站基本全覆盖，普速小站常缺**（站台不固定/未收录）。已并入 `parse_timetable.py` 输出「站台」列。

### 6.7 车站反查 `s0~s9.dat`（站 → 停靠车次）
- 源码 `QueryCZ.OooO` + `ResMgr.OooOO0`：**桶 = (站 index + 1) % 10** → `s{桶}.dat`（离线包大写 `S{桶}.dat`）。
- 记录 = `[站idx 2B][车次数 2B][车次idx × N]`（均 hi×255+lo）；顺扫记录头 == 站 index 命中（源码 `DataMgr.OooO0o`：`next = i + 4 + count×2`）。
- **只存车次 index 列表，不含时刻**——App/本工具拿到车次后回 `t*.dat` 用 `getTrainTimeDTO(车次idx, 站idx, 站idx)` 取该站到发时刻（`QueryCZ` 就这么做）。
- 已实现：`parse_timetable.py --station <站名>` → 该站所有停靠车次（到达/发车/站台/始发终到），按到达排序。北京南 552 趟、延吉西 72 趟，与正查交叉一致。

> 数据同 `jlb.dat` 随 `an.db` 每次更新；若 App 大改此格式，先反编译 `ResMgr`/`DataMgr` 复核（本节即由此得来）。
