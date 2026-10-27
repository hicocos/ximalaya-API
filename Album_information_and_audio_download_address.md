# 专辑信息、声音列表及音频地址

[返回首页](README.md) · 最近核验：2026-10-27

## 先区分三件事

1. **专辑与声音元数据**：标题、ID、时长、分页等，当前可匿名读取。
2. **服务端是否返回音频 URL**：受登录状态和内容权限影响。成功返回列表不代表存在下载地址。
3. **音频 URL 本身是否可访问**：还需检查 CDN 状态、类型和文件头，不能只看 URL 非空。

本次免费样本专辑 `9803351`：匿名时 18 条声音的媒体地址均为空；有效登录后 18 条返回 MP3 / AAC 地址。仅对其中一个免费 MP3 做了 1024 字节的 Range 抽查，返回 `206 audio/mpeg` 且通过 MP3 文件头检查；没有批量下载。

## 1. 旧移动接口：仍可使用，但有登录与权限条件

```text
GET https://mobwsa.ximalaya.com/mobile/playlist/album/page
```

- `albumId`：专辑 ID。
- `pageId`：从 `1` 开始的页码。
- 本次服务端固定 `pageSize=20`；不要假定可用额外参数修改。
- 业务成功码为 **`ret=0`**。
- 旧的 HTTP 地址目前也能返回数据，但请使用 HTTPS，尤其不能在明文 HTTP 上传送 Cookie。

```bash
curl --get 'https://mobwsa.ximalaya.com/mobile/playlist/album/page' --data-urlencode 'albumId=9803351' --data-urlencode 'pageId=1' -H 'User-Agent: Mozilla/5.0' --connect-timeout 8 --max-time 25
```

匿名请求适合验证目录，不保证返回媒体地址。带 Cookie 的操作建议使用[本机验证工具](README.md#本机验证工具)，不要把凭据直接写入 shell 命令。

### 分页与返回字段

- `list`：本页声音。
- `pageId` / `pageSize`：实际页码 / 页大小。
- `totalCount` / `maxPageId`：总声音数 / 最大页码。
- 已验证 `74215376` 第 1、2 页各 20 条；`9803351` 只有 18 条，第 2 页返回空列表。
- 翻页应依据实际分页字段并在空列表时结束，避免无限请求。

以下为免费样本的真实字段节选；删除了媒体 URL 和其余条目，而非完整响应：

```json
{
  "msg": "0",
  "ret": 0,
  "maxPageId": 1,
  "pageSize": 20,
  "pageId": 1,
  "totalCount": 18,
  "list": [
    {
      "trackId": 47218632,
      "title": "一、（小白系列）Python版本和安装",
      "duration": 873,
      "albumId": 9803351,
      "albumTitle": "听学编程之Python",
      "isPaid": false,
      "isFree": false,
      "isAuthorized": false,
      "orderNo": 1
    }
  ]
}
```

### 媒体字段

| 字段 | 正确理解 |
| --- | --- |
| `playUrl64` | 传统字段名中的 `64` 指约 64 kbps 码率档位，不是“64 位音频”。本次样本为 MP3。 |
| `playUrl32` | 传统约 32 kbps 码率档位，不是“32 位”。本次样本为 MP3。 |
| `playPathHq` | 高品质地址槽位，本次免费样本为空，不保证可用。 |
| `playPathAacv164` | AAC 字段名，通常理解为 AAC v1 / 64 档位，不能只凭名称断定编码、实际码率或质量。 |
| `playPathAacv224` | AAC 字段名，通常理解为 AAC v2 / 24 档位；不是“比上一个更高音质”的可靠标记。 |

需要准确编码或码率时，应对自己有权使用的实际媒体做探测，不能以字段名代替媒体分析。本次没有完成所有格式的编码和完整播放检查。

### 权限字段不是下载许可

- `isPaid`：内容的付费属性。
- `isFree`：接口内部的免费/试听属性，不能独立作为下载判断；免费样本中出现 `isPaid=false`、`isFree=false`，且仍正常返回可播放地址。
- `isAuthorized`：保留原值，不能单独判断账号拥有内容。
- `isPaid=true`、`isFree=true` 也可能只是付费专辑中的试听条目，不表示整张专辑免费。
- `isRichAudio` 不应直接解释为“是否有声书”；价格、VIP、权限来源等内部枚举不在没有依据时硬编码含义。

若付费或受限内容没有返回地址，应在官方客户端确认订购和授权。本项目不提供付费解密、DRM 绕过、令牌伪造或验证码绕过。

## 2. Web 专辑简介

```text
GET https://www.ximalaya.com/revision/album/v1/simple?albumId=9803351
```

- 匿名可用，业务成功为 `ret=200`。
- 主要信息：`data.albumPageMainInfo`。
- 常见字段：`albumTitle`、`anchorUid`、`anchorName`、`isPaid`、`isFinished`、`playCount`、`updateDate`、`shortIntro`、`richIntro`、`categoryId`。
- `data.albumId` 是专辑 ID；`currentUid` 与登录有关，不应记录到公开日志。
- `isFinished` 是整数枚举，不能按布尔值处理。本次 Web 专辑的 `1=连载`、`2=完本` 有官网 UI 与分类元数据依据，详见[完结状态](Album_reviews_and_filters.md#5-旧分类元数据与完结状态)，未知值保留降级。
- 专辑 `1` 本次返回 HTTP 200 但业务 `ret=404`，表示内容被删除。

完整专辑页面数据也可从下列接口获取：

```text
GET https://www.ximalaya.com/revision/album?albumId=9803351
```

本次返回 `data.mainInfo`、`data.anchorInfo`、`data.tracksInfo`；它与 `v1/simple` 的字段层级不同，不能混用。页面里的首批声音不代表完整专辑。

## 3. Web 专辑声音列表（不含媒体直链）

```text
GET https://www.ximalaya.com/revision/album/getTracksList?albumId=74215376&pageNum=1&sort=0
```

- `albumId`：专辑 ID。
- `pageNum`：页码，从 1 开始，注意不是移动接口的 `pageId`。
- `sort=0`：正序；`sort=1`：倒序。本次免费样本首尾声音顺序已实际对比。
- 返回 `data.tracks`、`data.trackTotalCount`、`data.pageNum`、`data.pageSize`、`data.sort`。
- 本次服务端每页 **30** 条；传 `pageSize=3` 或 `5` 仍返回 `pageSize=30`，因此不把它当成有效可调参数。
- 已验证大专辑第 1、2 页返回各 30 条且 ID 不同；不足一页的免费专辑第 2 页为空。
- `data.tracks[].trackId` 是声音 ID；`title` 是标题；`duration` 是秒数。

不要把它和下面这个不同接口混为一谈：

```text
GET /revision/album/v1/getTracksList
```

带 `/v1/` 的版本本次匿名和仅带有效登录 Cookie 时均返回 **`ret=407`、`webtk缺失`**。这不是 HTTP 网络失败，也不是重新传同一个 Cookie 就能解决。不在本项目中伪造 `webtk` 或承诺兼容该版本。

## 4. 单条声音信息

```text
GET https://www.ximalaya.com/revision/track/simple?trackId=47218632
```

- 匿名可用，业务成功为 `ret=200`。
- `data.trackInfo`：`trackId`、`title`、`duration`、`playCount`、`isPaid`、`commentCount` 等。
- `data.albumInfo`：所属专辑。
- `hasBuy`、`vipPermission` 等依赖登录和内容权限，不能作为通用授权结论。
- 本接口提供元数据，不是通用音频下载接口。

旧资料常见的 `/revision/play/v1/audio?id=47218632&ptype=1` 本次返回 HTTP 404，不能推荐为当前可用替代。`/revision/sound?trackId=47218632` 也返回 HTTP 404。以上是本次请求结果，不表示所有网络和客户端永久相同。

## 安全使用媒体 URL

- 优先使用 HTTPS。旧接口可能返回 `http://...xmcdn.com/...`；本次同一免费 MP3 的 HTTPS 版本已实际验证可用，但不保证所有历史地址均支持。
- 下载 CDN 资源时不要携带账号 Cookie，更不要把 Cookie 发送给未知域名。
- 媒体 URL 可能失效或带短期参数，不适合作为永久地址存储或公开。
- Range 抽查只证明开头一小段可访问，不代表完整下载、全长播放或所有音质均验证。
- 不建议把 `curl -I` 的 HEAD 结果当成实际 GET 一定成功；CDN 对 HEAD、GET、Range 的行为可能不同。

## 5. 其他免费公开内容入口

以下是独立于旧播放列表的正常只读路径，已用一个明确非付费样本匿名验证；不保证适用于所有作品或账号。

```text
GET https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=299146&pageSize=1&pageId=1
```

- 业务成功 `ret=0`；分页在 **`data`** 下：`data.list`、`pageId`、`pageSize`、`maxPageId`、`totalCount`。
- 与旧 `mobwsa` 接口顶层 `list` 的结构不同。
- 本次 `pageSize=1` 实际生效，两个相邻页返回不同声音 ID；列表本身没有媒体 URL。
- 不同目录入口可能出现不一致，例如一些历史专辑在此入口返回 `ret=924`、内容下架，不能将这一结果推广到其他接口。

单条历史 JSON：

```text
GET https://m.ximalaya.com/tracks/1027731027.json
```

- 本次 HTTP 200，**没有 `ret` 字段**，不要套用 `ret=0/200` 的校验方式。
- `id`、`album_id`、`title`、`duration`、`is_paid`、`is_free` 为顶层字段。
- 免费样本 `is_paid=false`，`play_path`、`play_path_64`、`play_path_32` 非空。
- 本次 `play_path_64` 对应的 CDN 资源抽查返回 `206 audio/mp4`，前 1024 字节存在 MP4 文件类型标记；未携带 Cookie，也未完整下载。
- **字段名不保证编码**：`play_path_64` 并不保证一定是 64 kbps MP3，也可能是 AAC/M4A。不能把旧移动接口 `playUrl64` 的传统含义强加给这个接口。
- 付费、下架、缺失或未知权限内容不在该免费样本结论内；不要尝试解密受限字段或寻找权限绕过。

路径也可在 [RSSHub 喜马拉雅路由](https://github.com/DIYgod/RSSHub/blob/master/lib/routes/ximalaya/album.ts) 与 [yt-dlp 提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/ximalaya.py) 观察到，但第三方代码存在不能代替真实验证。本仓库 CLI 暂不封装此历史 JSON 入口，避免与具有业务码的接口混用。
