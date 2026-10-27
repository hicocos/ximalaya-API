# 榜单目录与榜单内容

[返回首页](README.md) · [作品接入指南](Catalog_integration.md) · 最近核验：2026-10-27

## 结论：榜单内容已验证，调用条件不同于目录

官网榜单页 [https://www.ximalaya.com/top/](https://www.ximalaya.com/top/) 的匿名浏览器请求可以正常返回作品榜单；不需要账号登录 Cookie，但内容接口需要官网 SDK 正常生成的 **`xm-sign` 请求头**。

最初直接请求 `/revision/rank/v4/element` 得到 `ret=400`、`params can not be null`，不能据此认定接口失效。本次对同一 URL、相同普通请求头作对比：

- 不带 `xm-sign`：HTTP 200、业务 `ret=400`。
- 带同一浏览器正常请求中取得的 `xm-sign`：HTTP 200、业务 `ret=200`、非空 `data.rankList`。
- 浏览器直接打开官网榜单页也实际显示了列表；验证没有登录账号、伪造 SDK 值或绕过验证码。

这说明本次失败与缺少网站附加请求头有关，**不是补登录 Cookie 或增加 `params=JSON` 就能解决**。该头的值可能过期或绑定浏览器环境，本次成功重用不保证跨机器、跨 IP 或长期有效。

## 1. 榜单目录

```text
GET https://www.ximalaya.com/revision/rank/v4/rankTabs?sceneId=1
```

本次无需 Cookie 或 `xm-sign`，成功码 `ret=200`。目录位于 `data.tabLists[]`，每项有 `id`、`name`、`tabWraps[]`，子项有 `rankingId`、`name`。

本次“全站”目录中的部分值：

- 热播：`100006`。
- 新品：`100149`。
- 免费：`100007`。
- 主播：`100907`。

这些是样本，不是永久常量；接入时从目录动态取 ID。

```bash
python3 scripts/ximalaya.py rank-tabs --scene 1
```

## 2. 榜单内容

```text
GET https://www.ximalaya.com/revision/rank/v4/element?rankingId=100006
```

请求头包含官网正常浏览器请求取得的 `xm-sign`。参数：

- `rankingId`：榜单 ID，多个 ID 以英文逗号连接，本次 `100006,100149` 可同时返回两份榜单。
- `pageNum`：**不要当作页码**。虽然官网 JS 名称如此，本次实测它控制“前 N 条”：`1/2/3/10` 分别返回榜单前 `1/2/3/10` 条，与不传该值时返回的列表前缀完全一致。
- 不传 `pageNum`：本次热播榜返回 100 条，`count=100`。其他榜单长度及最大范围不保证相同。
- 没有验证可按偏移量读取下一页的参数，不提供虚假的分页承诺；需要前 N 条时工具用更准确的 `--limit` 命名。

同一请求不应循环传 `pageNum=1,2,3...` 当翻页，否则会不断重复榜首作品。

### 响应路径

```text
data.rankingIds[]
data.rankList[]
  rankId / title / subtitle / contentType / count / ids[] / coverPath
  albums[]
  anchors[]
```

- 本次热播、免费、新品作品榜 `contentType=2`，使用 `albums`。
- 本次主播影响力榜 `contentType=3`，使用 `anchors`；`albums=[]` 并不表示接口失败。
- `count` 随 `pageNum` 改变，是本次返回数量口径，不能当成整个榜单永久总数。
- `ids` 与对应资源 ID 有关，不能把作品 ID、主播 ID 和榜单 ID 混用。
- `currentUid` 是登录相关信息，无需对外输出。

### 作品条目

`data.rankList[].albums[]` 中可用于卡片的字段：

- `id`：作品/专辑 ID，可继续请求作品详情。
- `albumTitle`、`albumUrl`、`cover`。
- `anchorName`、`anchorUrl`。
- `playCount`、`trackCount`、`description`。
- `isPaid`、`categoryId`、`categoryTitle`。
- `lastUpdateTrack`、`lastUpdateTrackUri`、`rankingPositionChange`。

本次 `cover` 是 `storages/...jpeg` 相对路径，图片地址可拼接 `https://imagev2.xmcdn.com/`，不要当成完整 URL。`isPaid` 是作品内容属性，公开榜单不代表获得音频下载许可。

### 主播条目

`data.rankList[].anchors[]` 中可用：`id`、`anchorName`、`anchorUrl`、`cover`、`trackCount`、`albumCount`、`fansCount`、`personalDescription`、`rankingPositionChange`。`id` 在这里是主播 UID，不是专辑 ID。

## 3. 本机复现

1. 用自己的浏览器打开官网 `/top/`，在开发者工具 Network 中找到成功的 `/revision/rank/v4/element` 请求。
2. 只复制其请求头里的 **`xm-sign` 原始值**，不要复制 Cookie、整份 HAR 或“Copy as cURL”后公开粘贴。
3. 在可信本机通过隐藏输入设置环境变量；工具不会输出该值，也不会生成、伪造或永久保存签名。

```bash
# Bash：输入不会显示，也不把值直接写进历史命令
read -r -s -p 'xm-sign: ' XIMALAYA_XM_SIGN; printf '\n'
export XIMALAYA_XM_SIGN

# 默认请求当前榜单列表
python3 scripts/ximalaya.py rank 100006

# 前 10 条，不是第 10 页
python3 scripts/ximalaya.py rank 100006 --limit 10

# 一次获取两份榜单的前 3 条
python3 scripts/ximalaya.py rank '100006,100149' --limit 3

# 主播榜：结果是 anchors 而不是 albums
python3 scripts/ximalaya.py rank 100907 --limit 3
unset XIMALAYA_XM_SIGN
```

没有提供有效值时，工具会直接报缺少 `XIMALAYA_XM_SIGN`，不重复撞接口。值过期或触发风控时停止，回到官网确认，不尝试绕过验证码或复制他人的浏览器会话。`xm-sign` 不是旧教程里可随意替换的固定 MD5 字符串，也不是登录 token。

本次已验证“官网正常匿名浏览器 → 实际请求头 → 同机 API 请求”，**没有验证无人值守自动获取、长期续期或生产客户端的完整集成**。客户端有正常 WebView 时可使用网站本身的 SDK 流程；纯后端接入仍需处理这一条件，不能说成零配置匿名 API。

## 4. 错误处理与旧接口

- HTTP 200 仍需检查 `ret`；`ret=400` 不应静默转为空榜单。
- 作品榜和主播榜要按资源类型分别渲染。
- 官网 JS 使用普通 query 参数；不需要将参数改成已失败的 `params=JSON` 方式。
- 当前站点脚本包含 v1/v2/v3 旧榜路径，其中部分还能返回数据，但不能仅凭非空就认定与当前 v4 实时榜单一致。默认对接本页已验证的 v4，不将旧榜或分类热门推荐冒充当前官网榜单。

## 来源

- [官网榜单页](https://www.ximalaya.com/top/)
- [官网页面实际引用的主脚本 f714bf.js](https://s1.xmcdn.com/yx/ximalaya-web-static/last/dist/scripts/f714bf.js)，其中 `getRankListV4` 构造 `rankingId`、可选 `pageNum`，请求拦截器对榜单内容路径附加 SDK 产生的 `xm-sign`。

文档不保存真实签名、浏览器会话和抓包原始响应；请求头值应仅保留在自己的可信本机。
