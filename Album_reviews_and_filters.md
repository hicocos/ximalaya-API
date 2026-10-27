# 作品评分、评价与分类筛选

[返回首页](README.md) · [作品接入指南](Catalog_integration.md) · 最近核验：2026-10-27

本页补充作品详情的评分、评价区，以及发现页的分类筛选。以下均为只读 GET；作品评价与单集评论是不同的数据源，不能混用 ID、分页字段或成功码。

## 1. 作品评分

```text
GET https://www.ximalaya.com/revision/comment/albumStatistics/24448864
```

本次匿名成功：

```json
{
  "ret": 200,
  "msg": "success",
  "data": {
    "isAlbumCommentShow": true,
    "albumScore": 9.0,
    "totalCommentCount": 4312
  }
}
```

- 作品 ID 放在路径中，而不是 `albumId` 查询参数。
- 展示评价区时尊重 `isAlbumCommentShow`；评分和人数也会变化。
- 评分不是作品详情中必定自带的字段，需要此独立请求。

```bash
python3 scripts/ximalaya.py album-rating 24448864
```

## 2. 作品评价：最热 / 最新

```text
GET https://mobile.ximalaya.com/album-comment-mobile/web/album/comment/list/query/{timestampMs}
```

`{timestampMs}` 按官网调用方式取当前 Unix 毫秒时间戳，**不是令牌或账号 ID**。本机工具自动生成，复制历史完整 URL 时不要永久复用旧时间戳。

请求参数：

- `albumId`：作品 ID。
- `order=content-score-desc`：最热；`order=time-desc`：最新，两者均验证成功。
- `pageId`：从 1 开始。
- `pageSize`：官网默认 10，本次验证 3。

**成功码是 `ret=0`，不是 Web 的 `200`。** 本次匿名可读，`data` 主要结构：

```text
data.albumScore
data.albumValidScoreNum
data.allCommentsCount
data.labelList[]
data.scoreDiagram
data.isCommentsFolded
data.comments.list[]
data.comments.pageId / pageSize / maxPageId / totalCount
```

- `scoreDiagram` 中 `fiveStar`、`fourStar`、`threeStar`、`twoStar`、`oneStar` 本次为评分比例数值，不应按人数理解。
- `labelList`、折叠标记、近期评分字段可能因排序而缺失，需可选处理。
- `comments.list[]` 含 `commentId`、`content`、`nickname`、`smallHeader`、`createdAt`、`likes`、`replyCount`，以及可能存在的 `newAlbumScore`。
- **最新评价不一定有 `newAlbumScore`**，不要把缺失显示成 0 分。
- `createdAt` 本次为毫秒级数值，和单集评论的 `createAt` 日期字符串不同。
- 最热样本 `comments.totalCount=1932`，最新为 `4312`，而 `allCommentsCount=4312`；这与评价折叠有关。不要把最热分页总数标成全部评价数量。
- 部分原始字段含设备或用户附加信息；客户端应白名单映射展示字段，不透传整条对象到日志。

```bash
python3 scripts/ximalaya.py album-reviews 24448864 --rows 3
python3 scripts/ximalaya.py album-reviews 24448864 --order time-desc --rows 3
```

## 3. 作品评价回复

```text
GET https://mobile.ximalaya.com/album-comment-mobile/ipad/album/comment/reply/list/query/{timestampMs}
```

参数：`albumId`、`commentId`、`pageId`、`pageSize`。本次用实际评价 ID `7821759` 成功读取非空回复。

- 业务成功为 `ret=0`。
- 原评论：`data.RootComment`，注意大写 `R`。
- 回复分页：`data.commentReplys.list[]` 及同层的 `pageId`、`pageSize`、`maxPageId`、`totalCount`。
- **键名就是 `commentReplys`，不要改为 `commentReplies`。**
- 回复条目含 `replyId`、`content`、`nickname`、`createdAt`、`parentReplyId`、`parentReplyNickName` 等。
- 原始条目另有 `clientInfo`，不适合公开展示或写入普通日志；本机工具不会输出。

```bash
python3 scripts/ximalaya.py review-replies 24448864 7821759 --rows 3
```

没有实现发布评价、回复或点赞。免费读取公开评价不代表有权下载作品音频。

## 4. 新版分类筛选树

```text
GET https://www.ximalaya.com/revision/category/v2/metadata/info?categoryId=3
```

本次匿名 `ret=200`，返回 `data.metadata[]`。节点可能递归：

```text
{id, displayName, name, metadataValues:[...]}
```

本次有声书分类包含男频、女频、情节、播讲形式等。按真实树渲染，不写死固定层数或把树节点 ID 当请求筛选值。

```bash
python3 scripts/ximalaya.py category-metadata 3
```

将选中节点的 **`name`** 逗号连接，作为分类作品接口的 `metadataValues`：

```text
GET https://www.ximalaya.com/revision/category/v2/albums?categoryId=3&pageNum=1&pageSize=3&sort=1&metadataValues=%E5%A5%B3%E9%A2%91
```

- 本次名称 `女频` 返回非空作品，数字 ID 不能替代名称。
- 多级组合由官网源码观察到使用名称逗号串；本次只验证单个筛选值，未穷举所有组合。
- 排序在官网 UI 对应 `1=综合`、`2=最近更新`、`3=最多播放`；本次三种均可返回非空作品，但排序的数据语义未做长期验证。
- 返回结构与[分类作品列表](Read_only_API.md#2-分类下的作品列表)相同。

```bash
python3 scripts/ximalaya.py category-albums 3 --metadata-values '女频' --rows 3
```

## 5. 旧分类元数据与完结状态

```text
GET https://www.ximalaya.com/revision/category/detailCategoryPageInfo?category=youshengshu
```

本次匿名可读。`data.subcategories`、`data.metadata` 是另一套旧结构：元数据子项叫 `metaValues`，不是新版的 `metadataValues`。

旧元数据明确给出：

- 元数据 `131`：是否完本；值 `2559` 对应 `name/code="1"`、连载中；`2560` 对应 `"2"`、已完本。
- 元数据 `132`：是否付费；值 `2721` 付费、`2722` 免费。

结合官网作品卡片 UI 的 `isFinished === 2` 完本判断，可将本次 Web 专辑相关字段的 `1/2` 分别用于“连载 / 完本”展示；未知值仍需保留并降级，不能对别的同名字段盲目套用，也不能按布尔值解析。

旧列表路径 `/revision/category/queryCategoryPageAlbums` 的 `meta` 格式为 `元数据ID_值ID`，多项以 `-` 连接，例如 `131_2560-132_2722`。但本次带完本筛选和不带筛选的基线都只返回空列表，因此**不推荐它作为已验证可用的完本筛选方案**。

新版本次有声书筛选树未见完本条件。可以展示列表中的 `isFinished`，但不应仅过滤当前一页后声称获得全站“全部已完本作品”，更不要将旧版 `meta` 传给新版 `metadataValues`。

## 6. 相关推荐显示约定

[作品页相关推荐](Read_only_API.md#9-作品详情页相关推荐)可能包含当前作品。官网 UI 会先过滤掉 `id === albumId`；本机 CLI 也会排除当前作品。不要把本作品重复展示为“相似作品”，也不承诺这些结果严格同分类或同作者。

`/revision/recommend/album/kw?albumId=24448864` 本次返回成功但 `data.recKw.recommendText=[]`；这是推荐关键词，不是作品列表。空时隐藏该模块，不生成虚构关键词。

## 来源

除主站公共脚本，还从专辑页面路由引用的以下脚本核实了参数构造、UI 排序和字段消费；链接可能随官网更新失效。

- [主脚本 c24892.js](https://award.xmcdn.com/yx/ximalaya-web/last/dist/scripts/c24892.js)
- [详情页 09a18e.js](https://s1.xmcdn.com/yx/ximalaya-web-static/last/dist/scripts/09a18e.js)
- [评价页 fabf28.js](https://s1.xmcdn.com/yx/ximalaya-web-static/last/dist/scripts/fabf28.js)
- [旧分类页 56ef5f.js](https://s1.xmcdn.com/yx/ximalaya-web-static/last/dist/scripts/56ef5f.js)
