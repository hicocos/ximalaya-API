# 作品浏览与详情接入

[返回首页](README.md)

这份指南面向“已有搜索、下载，需要补上作品浏览”的客户端。喜马拉雅的 **album 对应整部作品/专辑，track 对应单集/单条声音，uid 对应主播**。它们是不同 ID，不能在请求里互换。

## 页面与接口怎么对应

| 页面/操作 | 优先接口 | 用途 |
| --- | --- | --- |
| 搜索作品、作品卡片 | `/revision/search?core=album` | 标题、封面、主播、集数、播放量、付费属性。 |
| 打开作品详情 | `/revision/album?albumId=...` | 一次取得作品介绍、主播资料和首批目录。 |
| 较轻量的作品简介 | `/revision/album/v1/simple?albumId=...` | 不需要首批目录和完整主播模块时使用。 |
| 分集分页 / 正倒序 | `/revision/album/getTracksList` | 30 条/页，本次支持 `sort=0/1`。 |
| 单集详情 | `/revision/track/simple?trackId=...` | 单集封面、标题、简介、时长、所属作品。 |
| 主播全部公开作品分页 | `/revision/user/pub?uid=...` | 主播作品列表，使用 `page`、`pageSize`。 |
| 作品相关推荐 | `/revision/seo/hotWordAlbums?id=...&queryType=1` | 非个性化 SEO 相关作品。 |
| 作品评分 | `/revision/comment/albumStatistics/{albumId}` | 评分、评价数与评价显示开关。 |
| 最热 / 最新作品评价 | `mobile.ximalaya.com/album-comment-mobile/...` | 与声音评论分开，见专门说明。 |
| 检查可下载地址 | 旧移动 `/mobile/playlist/album/page` | 这一步独立于作品展示；受 Cookie 与权限影响。 |

发现页、分类、榜单、主播作品与评论见[其他只读接口](Read_only_API.md)。不是所有补充接口都已满足可直接接入条件，按各节状态处理。
作品评价、评分和分类筛选见[评分与筛选说明](Album_reviews_and_filters.md)。

## 示例：从搜索到作品详情，再到分集

以公开作品 `9803351` 为例：

```bash
# 搜索结果提供作品 ID 和卡片字段
python3 scripts/ximalaya.py search '编程' --rows 5

# 打开作品页：返回标题、封面、完整介绍、主播、首批分集
python3 scripts/ximalaya.py album-detail 9803351

# 用户切换倒序，或目录翻到下一页
python3 scripts/ximalaya.py tracks 9803351 --sort 1
python3 scripts/ximalaya.py tracks 9803351 --page 2

# 点开单集详情（不是取得媒体播放地址）
python3 scripts/ximalaya.py track 47218632

# 主播其他作品与详情页相关推荐
python3 scripts/ximalaya.py user-albums 3990327 --rows 3
python3 scripts/ximalaya.py related-albums 9803351
```

免费样本总共 18 集，Web 第 2 页为空；需要测试多页目录时可用 `74215376` 的公开元数据，其本次总集数为 810。后者属于付费作品，公开目录不代表可以下载全部内容。

## 作品卡片的字段映射

搜索 `data.result.response.docs[]`：

| 客户端展示字段 | 上游字段 | 注意 |
| --- | --- | --- |
| 作品 ID | `id` | 仅当 `core=album`；声音搜索的 `id` 是声音 ID。 |
| 作品标题 | `title` | 纯文本展示，不要用 `richTitle` 直接插 HTML。 |
| 封面 | `cover_path` | `//` 开头补 `https:`；缺失时用占位图。 |
| 主播名称 / ID | `nickname` / `uid` | 点击主播应携带主播 ID。 |
| 集数 | `tracks` | 可能变动。 |
| 播放量 | `play` | 数值展示，缺失不是 0。 |
| 短介绍 | `intro` | 可能被截断，不可当全文。 |
| 付费标记 | `is_paid` | 与详情的 `isPaid` 命名不同；不等于账号购买状态。 |

不要为了画每张卡片都额外调用一次详情接口。卡片先用列表给出的字段，详情只在用户打开作品时请求。

## 作品详情的字段映射

完整详情的对象根为 `data`，作品模块为 `data.mainInfo`：

- 标题：`mainInfo.albumTitle`。
- 封面：`mainInfo.cover`。
- 完整介绍：优先 `mainInfo.detailRichIntro`；`richIntro` 可能只有预览内容，`shortIntro` 是缩略文本。
- 主播：`anchorInfo.anchorId`、`anchorInfo.anchorName`、`anchorInfo.anchorCover`。
- 主播简介和统计：`anchorInfo.personalIntroduction`、`anchorAlbumsCount`、`anchorTracksCount`、`anchorFansCount`。
- 总集数：`tracksInfo.trackTotalCount`。
- 播放量 / 订阅量：`mainInfo.playCount` / `mainInfo.subscribeCount`。
- 分类：`mainInfo.crumbs.categoryId`、`categoryTitle`；子分类信息也在 `crumbs` 中。
- 标签：`mainInfo.tags`、`mainInfo.metas`；可能为空数组，勿写死固定长度或结构。
- 创建 / 更新日期：`mainInfo.createDate` / `mainInfo.updateDate`，本次为格式化日期字符串，不是毫秒时间戳。
- 完结与价格类型：`isFinished`、`isPaid` 等。本次官网 UI 和分类元数据支持 Web 专辑 `1=连载`、`2=完本`，未知值保留降级，不要按布尔类型解析，详见[字段依据](Album_reviews_and_filters.md#5-旧分类元数据与完结状态)。

`v1/simple` 的主要模块名是 **`data.albumPageMainInfo`**，不是 `mainInfo`。它还直接提供 `anchorUid`、`anchorName`、`categoryId`、`categoryTitle`，但不带完整的主播与目录模块。适配层应分别读取，不能只替换 URL 不改解析。

简介富文本包含 HTML。网页端须净化，桌面端可转纯文本；不要执行脚本、内联事件或任意外部内容。

## 目录与选集

- 完整详情中的 `tracksInfo.tracks` 只是首批目录，不能用它的长度当总集数。
- 后续目录接口返回 `data.tracks`，与详情的路径不同。
- 页码是 `pageNum`，从 `1` 开始；移动接口则使用 `pageId`。
- Web 实测每页 30，移动为 20，不能共用固定分页大小。
- 排序切换时清空旧页缓存并回到第 1 页；缓存键包含专辑 ID、页码、排序。
- 主键使用 `trackId`，不要用标题或数组下标；`index` / `orderNo` 是展示顺序。
- `duration` 单位为秒，客户端自行格式化。
- 空目录、已删除作品、付费无权限、登录失效、网络失败应显示不同状态。

## 浏览和下载分层

展示作品详情不应先取得媒体 URL，也不应强制用户登录。用户能看到一部作品的详情，不代表其账号有权播放或下载。

建议边界：

1. **目录数据层**：搜索、作品详情、分集、主播等只读请求，匿名可用时不带 Cookie。
2. **账号与媒体层**：需要时单独获取授权信息或媒体地址，Cookie 只保留在可信本机/后端。
3. **客户端展示层**：消费统一字段，不依赖上游每个页面各自不同的对象命名。

如果客户端没有可修改的界面源码，补全服务端 API 文档本身不会自动新增作品页。应先确认界面扩展入口，再决定直接调用上游还是增加自己的目录适配路由；不要把本仓库的更新表述成客户端已经完成改版。

## 缓存与降级建议

- 优先由受控后端调用，避免假定所有接口都允许浏览器跨域；本次没有验证 CORS。
- 对公开元数据做短期缓存，目录翻页按需加载，不循环扫描全站。
- 有登录状态或权限字段的结果不要存入跨账号共享缓存。
- 推荐、评论等模块失败时单独隐藏或给出提示，不要让整部作品详情跟着报错。
- 若分类/榜单被限流或不可用，先保留搜索入口；不要用虚构榜单或过期样本冒充实时作品。
