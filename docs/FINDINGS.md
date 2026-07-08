# 逆向发现记录

记录数据来源的格式与关键细节，便于 App 改版后快速修复。

## 1. 离线数据包 `an.db`

- 固定地址：`http://down.lltskb.com/an.db`（镜像 `http://223.107.87.50:8011/an.db`），约 2.2 MB。
- **实为 ZIP**（`PK\x03\x04` 头，尽管扩展名是 `.db`）。解压得全部离线数据文件：
  - `jlb.dat`（交路表，见下）
  - `plat.dat`（站台）、`routes.dat`（经由）、`sp.dat`、`t*.dat` / `s*.dat`（时刻分片）、`station_name.js`、`xw.dat`、`extra.dat` 等。
- 版本标签取 ZIP 内 `jlb.dat` 的构建日期（entry mtime），比 `android.ver` 的 `data` 字段更真实（后者偏向 App 发布日）。

## 2. 交路表 `jlb.dat`

- **明文二进制，未加密**，长度前缀分帧（1 字节长度 `L`(2..63) + `L` 字节 UTF-8 串）。
- 两类关键 token：
  - **车辆描述**：含 `型` / `供风` / `AC380` / `DC600` / `集便`，如 `25T型，AC380V，双管供风，集便`。
  - **交路链**：车次用 `#` 连接，如 `K7232#K7231#K7234#K7233`；`/` 表同一车次的往返编号，如 `Z158/5#Z157/6`。
- 配对规则：每条交路链关联**其前最近一次出现**的车辆描述。
- 规模（2026-07 版）：约 3123 条交路链、覆盖 11483 个车次，含 G/D/C/S/K/Z/T/Y。
- 解析正则：`^[A-Z]?\d{1,5}(?:/\d+)?(?:#[A-Z]?\d{1,5}(?:/\d+)?)+$`
- App 内加载类：`com.lltskb.lltskb.engine.JlbDataMgr`（`JlbDataMgr$JLB`）。

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
