# 搜索 API

[返回首页](README.md) · 最近核验：2026-10-27

## 结论

`GET https://www.ximalaya.com/revision/search` 仍可使用。已验证不带 Cookie 的专辑、声音、主播搜索，以及分页、相关度和时间排序。它不是官方承诺稳定的开放 API。

## 请求参数

| 参数 | 说明 |
| --- | --- |
| `core` | `album` 专辑、`track` 声音、`user` 主播，三种均已验证。 |
| `kw` | 搜索词；使用 URL 编码，不要直接拼接带 `&` 等符号的词。 |
| `page` | 从 `1` 开始的页码。 |
| `rows` | 每页数量；已验证 `3`、`5`。显式传入，不依赖默认值；最大值未核实。 |
| `condition` | 专辑搜索已验证 `relation`（相关度）、`time`（时间）。不保证对主播等其他类型同样有效。 |

历史文档中的 `spellchecker`、`device` 在旧示例里被接受，但本次未证实它们的实际作用，不是成功请求的必要条件。`fq` 的过滤语法和效果未核实，不再作为已支持能力介绍。

```bash
curl --get 'https://www.ximalaya.com/revision/search' \
  --data-urlencode 'core=album' \
  --data-urlencode 'kw=编程' \
  --data-urlencode 'page=1' \
  --data-urlencode 'rows=5' \
  --data-urlencode 'condition=relation' \
  -H 'Referer: https://www.ximalaya.com/' \
  -H 'User-Agent: Mozilla/5.0' \
  --connect-timeout 8 --max-time 25
```

使用验证工具：

```bash
python3 scripts/ximalaya.py search '编程' --rows 5
python3 scripts/ximalaya.py search '编程' --core track --rows 3
python3 scripts/ximalaya.py search '编程' --core user --rows 3
python3 scripts/ximalaya.py search '编程' --page 2 --rows 3
python3 scripts/ximalaya.py search '编程' --condition time --rows 3
```

## 响应结构

- Web 接口业务成功码为 `ret=200`，与移动接口的 `ret=0` 不同。
- 结果列表：`data.result.response.docs`。
- 分页字段位于 `data.result.response`，不在顶层。
- 即使响应头是 `text/plain`，响应体也可能是合法 JSON；不要只按 Content-Type 决定是否解析。

以下来自实际响应，删去了其他字段和条目；`pageSize` 表示服务端页大小，不是这个节选中 `docs` 的长度。搜索内容、顺序、数量随时间变化。

```json
{
  "ret": 200,
  "msg": "专辑检索结果",
  "data": {
    "result": {
      "response": {
        "docs": [
          {
            "id": 9803351,
            "title": "听学编程之Python",
            "uid": 3990327,
            "url": "/album/9803351",
            "is_paid": false,
            "tracks": 18
          }
        ],
        "numFound": 1248,
        "totalPage": 250,
        "start": 0,
        "pageSize": 5,
        "currentPage": 1
      }
    }
  }
}
```

### 分页字段

- `numFound` / `total`：服务端返回的匹配总数。
- `totalPage`：服务端总页数。
- `start`：本页起始偏移，本次 `page=2&rows=3` 返回 `start=3`。
- `pageSize`：实际每页数量。
- `currentPage`：实际当前页码。

翻页时保持 `kw`、`core`、`rows`、排序条件不变；不同时间的相关度结果可能变化，不要把搜索结果当成固定快照。

### 不同资源的字段

**专辑 `album`**：

- `id`：专辑 ID；`uid`：主播 ID。
- `title`、`intro`、`nickname`：标题、简介、主播名称。
- `url` / `anchorUrl`：网站相对路径。
- `cover_path`：封面，可能以 `//` 开头，网页外使用时补 `https:`。
- `tracks` / `play`：声音数量 / 播放次数。
- `is_paid`：付费属性，不代表当前账号是否已购买。
- `created_at` / `updated_at`：本次样本为毫秒级时间戳。

**声音 `track`**：

- `id`：声音 ID，不是专辑 ID；`album_id`：专辑 ID。
- `title`、`album_title`、`duration`（秒）、`count_play`。
- `trackUrl`、`albumUrl`、`userUrl`：对应页面路径。
- `play_path_32`、`play_path_64`、`play_path_aacv164`、`play_path_aacv224` 可能为空，不能承诺能从搜索结果直接下载。

**主播 `user`**：

- `id`、`nickname` 等字段以实际响应为准，字段集合不等同于专辑或声音。
- 主播搜索本次返回的后端排序为 `isVerified desc`，不能把专辑的 `condition` 语义直接套用。

### 不应猜测的字段

旧文档把 `is_finished` 固定解释为 `1=完结、0=未完结`，把 `last_uptrack_at_hour` 当标准时间戳，均不可靠。官网 Web 专辑 UI 和旧分类元数据支持 `1=连载`、`2=完本`，见[完结状态依据](Album_reviews_and_filters.md#5-旧分类元数据与完结状态)；搜索字段是另一个命名，接入时仍应确认枚举适用范围并保留未知值。`serialState`、`price_type_enum`、`vipType` 等内部枚举不要无依据转换。

`richTitle` 含高亮 HTML，不是纯文本；前端应提取文本或经过安全净化，不能直接把上游 HTML 插入页面。

`data.result.responseHeader.params` 是后端检索元信息，不代表其中每个参数都可作为公开请求参数传入；也可能包含用户或检索关联信息，不适合整段记录到日志。

## 常见问题

- HTTP 200 不等于业务成功，必须检查 `ret` 和响应结构。
- 返回 HTML、登录页或验证码时停止，不要无限重试或尝试绕过风控。
- 请求频率、地区和登录状态可能影响结果；工具每次只请求一页，不自动抓取全部搜索结果。
