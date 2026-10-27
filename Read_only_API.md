# 发现、分类、主播与评论接口

[返回首页](README.md) · [作品接入指南](Catalog_integration.md) · 最近核验：2026-10-27

除特别说明，以下均为 **GET**，基址为 `https://www.ximalaya.com`，Web 业务成功码为 `ret=200`。以下数据可用于扩展作品浏览，不需要先获得媒体下载地址。

## 1. 分类目录

```text
/revision/category/v2/allCategory
```

本次匿名返回非空 `data.categories`。条目字段：

- `id`：分类 ID，后续传给 `categoryId`。
- `name`、`title`：分类名称/标题，以实际返回为准。
- `categoryType`、`parentId`、`orderNum`、`isDisplay`：保留原始值；不擅自扩展内部枚举定义。

```bash
python3 scripts/ximalaya.py categories
```

## 2. 分类下的作品列表

```text
/revision/category/v2/albums?categoryId=3&pageNum=1&pageSize=3&sort=1
```

已验证第 1、2 页各返回 3 个作品，且作品 ID 不同。

- `categoryId`：来自分类目录。
- `pageNum`：从 1 开始。
- `pageSize`：本次验证 `3` 可生效，最大值未核实。
- `sort=1`：综合，本次可用；官网 UI 另有 `2=最近更新`、`3=最多播放`，数据语义未做长期验证。
- `metadataValues` 按名称而非 ID 传入，已验证 `女频` 筛选，见[筛选元数据](Album_reviews_and_filters.md#4-新版分类筛选树)。

结果：`data.total`、`data.pageNum`、`data.pageSize`、`data.albums[]`。

作品卡片可用字段：

| 用途 | 字段 |
| --- | --- |
| 作品 ID / 标题 | `albumId` / `albumTitle` |
| 封面路径 | `albumCoverPath` |
| 主播 ID / 名称 | `anchorId` / `albumUserNickName` |
| 播放量 / 集数 | `albumPlayCount` / `albumTrackCount` |
| 简介 | `intro` |
| 作品页 / 主播页 | `albumUrl` / `anchorUrl` |
| 内容属性 | `isPaid`、`isFinished`、`isDeleted` |

**封面格式有区别**：分类列表中的 `albumCoverPath` 本次是 `storages/...jpeg` 这样的纯路径，不是完整 URL；官网使用图片 CDN。可将这种受信任的相对路径拼到 `https://imagev2.xmcdn.com/`。搜索和详情的封面则可能以 `//` 开头，应补 `https:`，不能一律加相同前缀。

```bash
python3 scripts/ximalaya.py category-albums 3 --rows 3
python3 scripts/ximalaya.py category-albums 3 --page 2 --rows 3
```

该接口已经能支持“选择分类 → 作品卡片 → 打开详情”的非搜索入口；不应为了分类展示批量调用每个作品的详情。

## 3. 主播基本资料

```text
/revision/user/basic?uid=3990327
```

本次匿名成功。主要字段在 `data`：

- `uid`、`nickName`、`cover`、`personalSignature`。
- `fansCount`、`followingCount`、`tracksCount`、`albumsCount`。
- `anchorUrl`、`anchorGrade` 等公开主页信息。

注意是 `nickName`，而不是所有接口通用的 `nickname`。作品详情主播模块又使用 `anchorName`，应在适配层统一。

```bash
python3 scripts/ximalaya.py user 3990327
```

这是公开主播资料，不是当前登录账号的 `getCurrentUser`，两者用途与隐私边界不同。

## 4. 主播主页首批作品和声音

```text
/revision/user?uid=3990327
```

本次匿名成功：

- `data.pubPageInfo.totalCount`：公开作品总数。
- `data.pubPageInfo.pubInfoList[]`：首批作品。
- `data.trackPageInfo.totalCount`：声音总数。
- `data.trackPageInfo.trackInfoList[]`：首批声音。

作品条目使用 `id`、`title`、`coverPath`、`description`、`trackCount`、`playCount`、`anchorUid`、`anchorNickName`、`albumUrl`、`isPaid`。声音使用 `trackId`、`albumId`、`title`、`length`（本次为秒数）、`durationAsString`、`playCount`。

本次 `3990327` 返回 5 部作品，但目录、详情统计可能因缓存、可见范围等不完全相同，不要假定几个接口的计数严格一致。主页响应还可能含关注、粉丝、订阅模块，本机工具不输出这些非必要模块。

```bash
python3 scripts/ximalaya.py user-home 3990327
```

**首批不等于全部**：仅有此接口不足以宣称支持主播所有作品分页。分页补充以实际核验的独立接口为准，不要对 `/revision/user` 猜测添加 `page` 后就假定有效。

### 主播作品分页：已验证

```text
/revision/user/pub?uid=3990327&page=1&pageSize=3&keyWord=
```

- `uid`：主播 ID。
- `page`：从 1 开始，**不是 `pageNum`**。
- `pageSize`：请求页大小，已验证 `3`。
- `keyWord`：注意大写 `W`；本次为空，非空关键词过滤效果未核实。
- 结果为 `data.albumList[]`；字段与主页 `pubInfoList` 的作品条目基本一致。
- 分页/统计为 `data.totalCount`、`filterTotalCount`、`page`、`pageSize`、`maxCount`。

本次第 1 页返回 3 个 ID，第 2 页返回另 2 个 ID，覆盖该样本返回的 5 部公开作品。**最后一页响应把 `pageSize` 回填为 `2`，不要用它覆盖原请求页大小 `3`**，否则下一页计算可能重复或漏项。保持请求参数稳定，并在结果为空或已达到总数时结束。

```bash
python3 scripts/ximalaya.py user-albums 3990327 --rows 3
python3 scripts/ximalaya.py user-albums 3990327 --page 2 --rows 3
```

## 5. 单集完整页面信息

```text
/revision/track/trackPageInfo?trackId=47218632
```

本次匿名成功，比 `/revision/track/simple` 多一些适合展示的模块：

- `data.trackInfo`：标题、封面、简介、时长、播放量、评论数。
- `data.albumInfo`：所属作品及集数。
- `data.userInfo`：主播公开资料。
- `data.moreTracks`：其他声音，**本次样本为空数组，不能保证有推荐结果**。
- `data.metas`、`data.category`：分类相关信息。

```bash
python3 scripts/ximalaya.py track-page 47218632
```

它不是媒体播放地址接口，不应让单集详情页面依赖下载解析成功。

## 6. 声音评论与回复

### 评论分页

```text
/revision/comment/queryComments?trackId=47218632&page=1&pageSize=2
```

本次匿名成功，已检查第 1、2 页的非空评论。分页字段在 `data`：`currentPage`、`totalPage`、`totalComment`、`pageSize`；评论列表为 `data.comments[]`。

已观察的评论字段：

- `id`：评论 ID；查询回复时传给 `commentId`。
- `content`：评论文字；按不可信文本展示，不插入任意 HTML。
- `uid`、`nickname`、`smallHeader`：公开作者资料。
- `createAt`：展示用日期字符串。
- `commentTime`：本次为毫秒时间戳**字符串**，不要只按 JSON 数字解析。
- `likes`、`replyCount`、`replies`：点赞数、回复数、内嵌回复。

不要仅靠 `totalComment / pageSize` 推算 `totalPage`，接口统计可能存在口径或缓存差异；优先使用服务端分页字段并在空页时结束。

```bash
python3 scripts/ximalaya.py comments 47218632 --rows 2
python3 scripts/ximalaya.py comments 47218632 --page 2 --rows 2
```

### 回复

```text
/revision/comment/queryReplies?trackId=47218632&commentId=1002074201&page=1&pageSize=2
```

本次返回 `ret=200`，`data.replies=[]`，以及 `currentPage`、`totalPage`、`totalComment`、`pageSize`。**只验证了空回复场景，未核实非空回复条目结构。**

这是声音评论，不是专辑评分或作品评价接口。未提供写评论、点赞、删除或关注功能。

## 7. 榜单：目录已可读，内容需独立判断

```text
/revision/rank/v4/rankTabs?sceneId=1
```

本次匿名成功。`data.tabLists[]` 含 `id`、`name`、`tabWraps[]`；子项含 `rankingId`、`name`。例如本次“全站 → 热播”返回 `rankingId=100006`。榜单 ID 应从目录动态读取，不写死为永久常量。

```bash
python3 scripts/ximalaya.py rank-tabs --scene 1
```

官网 JS 中还有：

```text
/revision/rank/v4/element?rankingId=100006&pageNum=1
```

该最小请求本次返回 `ret=400`、参数为空提示，**未取得榜单作品，不标为可直接接入**。榜单目录成功不等于榜单内容成功，也不应把分类热门作品伪装成已取得的官方榜单。

官网 JS 使用普通查询参数 `rankingId`、`pageNum`，多个 ID 逗号连接，不是已证实需要 `params=JSON`。JSON 包装尝试仍返回同一错误，因此不能把失败简单归因为漏了一层包装。该路径也出现在网站签名调用列表中，但本次没有确认签名与失败的因果关系，不生成签名或尝试绕过。

客户端必须区分“榜单失败”和“榜单正常为空”，不要把 `ret=400` 静默转换为空榜单。

## 8. 新旧搜索不要混淆

本项目已验证的旧搜索：

```text
/revision/search?core=album&kw=...
```

官网新 JS 中还出现 `/revision/search/main`，其响应结构不同：源码读取 `data.album` / `data.track` / `data.user1` / `data.user2`。匿名实测新路径返回 `ret=200`，但 `data.reason="risk invalid"`、`riskLevel=5`，没有正常检索结果，因此不标为成功，不尝试绕过。已有客户端优先参考[已核验的旧搜索说明](Search_API.md)。

## 9. 作品详情页相关推荐

```text
/revision/seo/hotWordAlbums?id=9803351&queryType=1
```

本次匿名 `ret=200`，`data.hotWordAlbums` 返回 20 部作品。官网专辑页按 `id=albumId`、`queryType=1` 调用；这是 **SEO 相关推荐，不是个性化推荐**。
结果可能包含当前作品，展示前排除 `id === albumId`，本机工具已处理；不承诺严格同类或同作者。

条目字段：`id`、`title`、`intro`、`nickname`、`coverPath`、`link`、`playCount`、`trackCount`、`isPaid`、`vipType`。其中 `id` 为可继续打开详情的作品 ID。没有验证可调页大小或分页，不要自行加 `page` 后假定有效。

```bash
python3 scripts/ximalaya.py related-albums 9803351
```

主播页另有推荐：

```text
/revision/rank/user/recommend/album?uid=3990327&clusterTypeId=12&count=3
```

本次返回 `data.rankTitle`、`data.ranks`，`count=3` 返回 3 项。条目使用 `id`、`albumTitle`、`cover`、`anchorName`、`albumUrl`、`playCount`、`trackCount`、`description` 等。**它不是该主播自己的作品**，不能替代 `/revision/user/pub`；`clusterTypeId=12` 的所有可选值和含义未核实。

## 来源与验证级别

上述路径不仅依据旧帖子猜测：官网首页和专辑页面实际引用的脚本可观察到接口调用。脚本会更新或失效，链接用于说明来源，不是稳定版本锁。

- [喜马拉雅官网](https://www.ximalaya.com/)
- [首页引用脚本 f714bf.js](https://s1.xmcdn.com/yx/ximalaya-web-static/last/dist/scripts/f714bf.js)
- [专辑页面](https://www.ximalaya.com/album/74215376)
- [专辑页面引用脚本 c24892.js](https://award.xmcdn.com/yx/ximalaya-web/last/dist/scripts/c24892.js)

“源码里存在”不等于“现在能调用”；本页对源码观察、成功请求、空数据、受限接口分别标注，不把它们混成可用功能清单。
