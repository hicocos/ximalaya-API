#!/usr/bin/env python3
"""喜马拉雅只读接口验证工具（仅使用 Python 标准库）。"""

import argparse
import json
import os
import sys
import time
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

WEB = "https://www.ximalaya.com"
MOBILE = "https://mobwsa.ximalaya.com"
MOBILE_API = "https://mobile.ximalaya.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MAX_JSON_BYTES = 4 * 1024 * 1024


class ApiError(Exception):
    """只包含可公开的错误，不保留请求头或完整响应。"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("必须是正整数") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def bounded_positive_int(value):
    parsed = positive_int(value)
    if parsed > 100:
        raise argparse.ArgumentTypeError("每页数量不能超过 100")
    return parsed


def positive_timeout(value):
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("超时必须在 0 到 120 秒之间") from None
    if not 0 < parsed <= 120:
        raise argparse.ArgumentTypeError("超时必须在 0 到 120 秒之间")
    return parsed


def read_cookie(path=None):
    """文件优先于环境变量；绝不在错误中回显内容。"""
    if path:
        try:
            cookie = Path(path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise ApiError("无法读取 Cookie 文件") from None
        if not cookie:
            raise ApiError("Cookie 文件为空")
    else:
        cookie = os.environ.get("XIMALAYA_COOKIE", "").strip()
    if any(ch in cookie for ch in ("\r", "\n", "\x00")):
        raise ApiError("Cookie 必须是单行原始值，不要包含 Cookie: 前缀")
    if cookie.lower().startswith("cookie:"):
        raise ApiError("请去掉 Cookie: 前缀")
    return cookie


class Client:
    def __init__(self, cookie="", timeout=20, opener=None):
        self.cookie = cookie
        self.timeout = timeout
        self.opener = opener or build_opener(NoRedirect())

    def get(self, base, path, params=None):
        if base not in (WEB, MOBILE, MOBILE_API) or not path.startswith("/"):
            raise ApiError("不允许的接口地址")
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": WEB + "/",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        url = base + path + ("?" + urlencode(params) if params else "")
        req = Request(url, headers=headers, method="GET")
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise ApiError(f"HTTP {code}；未跟随重定向，也不会转发 Cookie") from None
        except (URLError, OSError, ValueError, HTTPException):
            raise ApiError("网络、TLS、超时或请求头错误；请稍后手动重试") from None
        if len(raw) > MAX_JSON_BYTES:
            raise ApiError("响应过大，已停止读取")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ApiError("返回内容不是 JSON；可能是错误页或风控页") from None
        if not isinstance(body, dict) or type(body.get("ret")) is not int:
            raise ApiError("响应缺少整数业务码 ret")
        expected = 200 if base == WEB else 0
        if body["ret"] != expected:
            hints = {401: "需要登录或 Cookie 已失效", 407: "需要网站 webtk，Cookie 本身不足以满足要求", 404: "内容不存在或已删除", 76: "内容不存在"}
            raise ApiError(f"业务 ret={body['ret']}：{hints.get(body['ret'], '请求未成功；请在官网核对权限或风控状态')}")
        return body

    def search(self, keyword, core="album", page=1, rows=5, condition="relation"):
        return self.get(WEB, "/revision/search", {"core": core, "kw": keyword, "page": page, "rows": rows, "condition": condition})

    def album(self, album_id):
        return self.get(WEB, "/revision/album/v1/simple", {"albumId": album_id})

    def album_detail(self, album_id):
        return self.get(WEB, "/revision/album", {"albumId": album_id})

    def tracks(self, album_id, page=1, sort=0):
        return self.get(WEB, "/revision/album/getTracksList", {"albumId": album_id, "pageNum": page, "sort": sort})

    def mobile_tracks(self, album_id, page=1):
        return self.get(MOBILE, "/mobile/playlist/album/page", {"albumId": album_id, "pageId": page})

    def track(self, track_id):
        return self.get(WEB, "/revision/track/simple", {"trackId": track_id})

    def login_status(self):
        return self.get(WEB, "/revision/main/getCurrentUser")

    def categories(self):
        return self.get(WEB, "/revision/category/v2/allCategory")

    def category_albums(self, category_id, page=1, page_size=5, metadata_values="", sort=1):
        params = {"categoryId": category_id, "pageNum": page, "pageSize": page_size, "sort": sort}
        if metadata_values:
            params["metadataValues"] = metadata_values
        return self.get(WEB, "/revision/category/v2/albums", params)

    def category_metadata(self, category_id):
        return self.get(WEB, "/revision/category/v2/metadata/info", {"categoryId": category_id})

    def user(self, uid):
        return self.get(WEB, "/revision/user/basic", {"uid": uid})

    def user_home(self, uid):
        return self.get(WEB, "/revision/user", {"uid": uid})

    def user_albums(self, uid, page=1, page_size=5, keyword=""):
        return self.get(WEB, "/revision/user/pub", {"uid": uid, "page": page, "pageSize": page_size, "keyWord": keyword})

    def related_albums(self, album_id):
        return self.get(WEB, "/revision/seo/hotWordAlbums", {"id": album_id, "queryType": 1})

    def track_page(self, track_id):
        return self.get(WEB, "/revision/track/trackPageInfo", {"trackId": track_id})

    def comments(self, track_id, page=1, page_size=5):
        return self.get(WEB, "/revision/comment/queryComments", {"trackId": track_id, "page": page, "pageSize": page_size})

    def rank_tabs(self, scene_id=1):
        return self.get(WEB, "/revision/rank/v4/rankTabs", {"sceneId": scene_id})

    def album_rating(self, album_id):
        return self.get(WEB, f"/revision/comment/albumStatistics/{album_id}")

    def album_reviews(self, album_id, page=1, page_size=5, order="content-score-desc"):
        timestamp = int(time.time() * 1000)
        return self.get(MOBILE_API, f"/album-comment-mobile/web/album/comment/list/query/{timestamp}", {"albumId": album_id, "pageId": page, "pageSize": page_size, "order": order})

    def review_replies(self, album_id, comment_id, page=1, page_size=5):
        timestamp = int(time.time() * 1000)
        return self.get(MOBILE_API, f"/album-comment-mobile/ipad/album/comment/reply/list/query/{timestamp}", {"albumId": album_id, "commentId": comment_id, "pageId": page, "pageSize": page_size})


def object_at(body, *keys):
    current = body
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ApiError("响应结构与文档不符，缺少 " + ".".join(keys))
        current = current[key]
    if not isinstance(current, dict):
        raise ApiError("响应对象类型发生变化")
    return current


def list_at(body, *keys):
    current = body
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ApiError("响应结构与文档不符，缺少 " + ".".join(keys))
        current = current[key]
    if not isinstance(current, list) or not all(isinstance(item, dict) for item in current):
        raise ApiError("响应列表类型发生变化")
    return current


def pick(value, keys):
    return {key: value[key] for key in keys if key in value}


def metadata_nodes(nodes, depth=0):
    if depth > 20 or not isinstance(nodes, list) or not all(isinstance(x, dict) for x in nodes):
        raise ApiError("分类筛选树结构异常")
    result = []
    for node in nodes:
        item = pick(node, ["id", "displayName", "name"])
        if "metadataValues" in node:
            item["metadataValues"] = metadata_nodes(node["metadataValues"], depth + 1)
        result.append(item)
    return result


def summary(command, body):
    """白名单输出；不会输出登录账号资料、原始响应和媒体 URL。"""
    if command == "search":
        response = object_at(body, "data", "result", "response")
        return {**pick(response, ["numFound", "totalPage", "pageSize", "currentPage", "start"]), "items": [pick(x, ["id", "title", "nickname", "uid", "album_id", "album_title", "is_paid", "tracks", "cover_path", "album_cover_path", "intro", "play", "count_play", "duration", "url", "anchorUrl", "trackUrl", "albumUrl"]) for x in list_at(body, "data", "result", "response", "docs")]}
    if command == "album":
        data = object_at(body, "data")
        info = object_at(body, "data", "albumPageMainInfo")
        return {**pick(data, ["albumId"]), **pick(info, ["albumTitle", "cover", "anchorUid", "anchorName", "isPaid", "isFinished", "playCount", "updateDate", "createDate", "shortIntro", "detailRichIntro", "categoryId", "categoryTitle", "subscribeCount", "tags"])}
    if command == "album-detail":
        data = object_at(body, "data")
        return {
            **pick(data, ["albumId"]),
            "mainInfo": pick(object_at(body, "data", "mainInfo"), ["albumTitle", "cover", "crumbs", "isPaid", "isFinished", "playCount", "updateDate", "createDate", "shortIntro", "detailRichIntro", "subscribeCount", "sellingPoint", "customTitle", "tags", "metas"]),
            "anchorInfo": pick(object_at(body, "data", "anchorInfo"), ["anchorId", "anchorName", "anchorCover", "personalIntroduction", "anchorAlbumsCount", "anchorTracksCount", "anchorFansCount"]),
            "tracksInfo": {**pick(object_at(body, "data", "tracksInfo"), ["trackTotalCount", "pageNum", "pageSize", "sort"]), "tracks": [pick(x, ["trackId", "title", "duration", "isPaid", "index"]) for x in list_at(body, "data", "tracksInfo", "tracks")]},
        }
    if command == "tracks":
        data = object_at(body, "data")
        return {**pick(data, ["albumId", "pageNum", "pageSize", "trackTotalCount", "sort"]), "items": [pick(x, ["trackId", "title", "duration", "isPaid", "index"]) for x in list_at(body, "data", "tracks")]}
    if command == "mobile-tracks":
        tracks = list_at(body, "list")
        fields = ["playUrl64", "playUrl32", "playPathHq", "playPathAacv164", "playPathAacv224"]
        return {**pick(body, ["pageId", "pageSize", "maxPageId", "totalCount"]), "audio_url_counts": {key: sum(bool(x.get(key)) for x in tracks) for key in fields}, "items": [pick(x, ["trackId", "title", "duration", "isPaid", "isFree", "orderNo"]) for x in tracks]}
    if command == "track":
        return pick(object_at(body, "data", "trackInfo"), ["trackId", "title", "coverPath", "shortIntro", "richIntro", "duration", "isPaid", "playCount", "commentCount"])
    if command == "track-page":
        return {
            "trackInfo": pick(object_at(body, "data", "trackInfo"), ["trackId", "title", "coverPath", "shortIntro", "richIntro", "duration", "isPaid", "playCount", "commentCount"]),
            "albumInfo": pick(object_at(body, "data", "albumInfo"), ["albumId", "title", "coverPath", "trackCount", "description"]),
            "userInfo": pick(object_at(body, "data", "userInfo"), ["uid", "nickname", "coverPath", "intro", "albumCount", "trackCount", "fansCount"]),
            "moreTracks": [pick(x, ["trackId", "title", "coverPath", "duration"]) for x in list_at(body, "data", "moreTracks")],
        }
    if command == "categories":
        return {"items": [pick(x, ["id", "name", "title", "parentId", "categoryType", "orderNum", "isDisplay"]) for x in list_at(body, "data", "categories")]}
    if command == "category-albums":
        data = object_at(body, "data")
        return {**pick(data, ["total", "pageNum", "pageSize"]), "items": [pick(x, ["albumId", "albumTitle", "albumCoverPath", "albumUserNickName", "anchorId", "albumTrackCount", "albumPlayCount", "isPaid", "isFinished", "intro", "albumUrl"]) for x in list_at(body, "data", "albums")]}
    if command == "category-metadata":
        return {"items": metadata_nodes(list_at(body, "data", "metadata"))}
    if command == "user":
        return pick(object_at(body, "data"), ["uid", "nickName", "cover", "personalSignature", "fansCount", "followingCount", "tracksCount", "albumsCount", "anchorUrl"])
    if command == "user-home":
        return {
            "uid": object_at(body, "data").get("uid"),
            "albums": {**pick(object_at(body, "data", "pubPageInfo"), ["totalCount"]), "items": [pick(x, ["id", "title", "subTitle", "coverPath", "anchorNickName", "anchorUid", "playCount", "trackCount", "isPaid", "isFinished", "description", "albumUrl"]) for x in list_at(body, "data", "pubPageInfo", "pubInfoList")]},
            "tracks": {**pick(object_at(body, "data", "trackPageInfo"), ["totalCount"]), "items": [pick(x, ["trackId", "title", "coverPath", "albumId", "albumTitle", "length", "durationAsString", "isPaid", "playCount"]) for x in list_at(body, "data", "trackPageInfo", "trackInfoList")]},
        }
    if command == "comments":
        return {**pick(object_at(body, "data"), ["currentPage", "totalPage", "totalComment", "pageSize"]), "items": [pick(x, ["id", "content", "createAt", "commentTime", "uid", "nickname", "smallHeader", "likes", "replyCount"]) for x in list_at(body, "data", "comments")]}
    if command == "user-albums":
        return {**pick(object_at(body, "data"), ["totalCount", "filterTotalCount", "page", "pageSize", "keyWord", "maxCount"]), "items": [pick(x, ["id", "title", "coverPath", "anchorNickName", "anchorUid", "playCount", "trackCount", "isPaid", "isFinished", "description", "albumUrl"]) for x in list_at(body, "data", "albumList")]}
    if command == "related-albums":
        return {"items": [pick(x, ["id", "title", "intro", "nickname", "coverPath", "link", "playCount", "trackCount", "isPaid"]) for x in list_at(body, "data", "hotWordAlbums")]}
    if command == "rank-tabs":
        return {**pick(object_at(body, "data"), ["sceneId"]), "items": [pick(x, ["id", "name", "tabWraps"]) for x in list_at(body, "data", "tabLists")]}
    if command == "album-rating":
        return pick(object_at(body, "data"), ["isAlbumCommentShow", "albumScore", "totalCommentCount"])
    if command == "album-reviews":
        data = object_at(body, "data")
        fields = ["commentId", "content", "nickname", "smallHeader", "createdAt", "likes", "replyCount", "newAlbumScore"]
        return {**pick(data, ["albumScore", "albumValidScoreNum", "allCommentsCount", "isCommentsFolded"]), "scoreDiagram": pick(object_at(body, "data", "scoreDiagram"), ["fiveStar", "fourStar", "threeStar", "twoStar", "oneStar"]), "comments": {**pick(object_at(body, "data", "comments"), ["pageId", "pageSize", "maxPageId", "totalCount"]), "items": [pick(x, fields) for x in list_at(body, "data", "comments", "list")]}}
    if command == "review-replies":
        return {**pick(object_at(body, "data", "commentReplys"), ["pageId", "pageSize", "maxPageId", "totalCount"]), "items": [pick(x, ["replyId", "content", "nickname", "smallHeader", "createdAt", "parentReplyId", "parentReplyNickName"]) for x in list_at(body, "data", "commentReplys", "list")]}
    if command == "login-status":
        if not object_at(body, "data").get("uid"):
            raise ApiError("未确认有效登录用户")
        return {"authenticated": True}
    raise ApiError("未知命令")


def looks_like_mp3(sample):
    """检查 ID3v2 或 MPEG Layer III 头；不是完整解码验证。"""
    if sample.startswith(b"ID3"):
        return len(sample) >= 10 and sample[3] in (2, 3, 4) and sample[4] != 255 and all(x < 128 for x in sample[6:10])
    if len(sample) < 4:
        return False
    return (
        sample[0] == 255
        and sample[1] & 224 == 224
        and (sample[1] >> 3) & 3 != 1
        and (sample[1] >> 1) & 3 == 1
        and 1 <= sample[2] >> 4 <= 14
        and (sample[2] >> 2) & 3 != 3
    )


def probe_audio(tracks, timeout=20, opener=None):
    """仅检查明确非付费条目的首个 64 kbps 地址，最多读取 1024 字节。"""
    track = next((x for x in tracks if x.get("isPaid") is False and x.get("playUrl64")), None)
    if track is None:
        raise ApiError("没有可安全抽查的免费音频地址；不要尝试绕过权限")
    if not isinstance(track["playUrl64"], str):
        raise ApiError("媒体地址必须是非空字符串")
    try:
        parsed = urlsplit(track["playUrl64"])
    except (ValueError, TypeError):
        raise ApiError("媒体地址格式不合法") from None
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host.endswith(".xmcdn.com") or parsed.username or parsed.password:
        raise ApiError("媒体地址不在允许的喜马拉雅 CDN 范围内")
    try:
        port = parsed.port
    except ValueError:
        raise ApiError("媒体地址端口不合法") from None
    if port not in (None, 80, 443):
        raise ApiError("媒体地址端口不合法")
    url = urlunsplit(("https", host, parsed.path, parsed.query, ""))
    # 独立 opener，没有 Cookie 头、CookieJar 或 API Client。
    req = Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023", "Referer": WEB + "/"}, method="GET")
    try:
        with (opener or build_opener(NoRedirect())).open(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            status = response.status
            content_range = response.headers.get("Content-Range", "")
            sample = response.read(1024)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise ApiError(f"音频 HTTP {code}；未跟随跳转") from None
    except (URLError, OSError, ValueError, HTTPException):
        raise ApiError("音频网络、TLS 或超时错误") from None
    if status not in (200, 206) or content_type not in ("audio/mpeg", "audio/mp3") or not looks_like_mp3(sample):
        raise ApiError("返回内容未通过音频类型与 MP3 文件头检查")
    return {"trackId": track.get("trackId"), "http_status": status, "content_type": content_type, "content_range": content_range, "bytes_read": len(sample), "cookie_sent": False}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--cookie-file", help="本机单行 Cookie 文件；不要放在仓库中")
    result.add_argument("--timeout", type=positive_timeout, default=20)
    commands = result.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="搜索专辑、声音或主播")
    search.add_argument("keyword")
    search.add_argument("--core", choices=["album", "track", "user"], default="album")
    search.add_argument("--page", type=positive_int, default=1)
    search.add_argument("--rows", type=bounded_positive_int, default=5)
    search.add_argument("--condition", choices=["relation", "time"], default="relation")
    album = commands.add_parser("album", help="专辑简介")
    album.add_argument("album_id", type=positive_int)
    album_detail = commands.add_parser("album-detail", help="完整作品详情：封面、介绍、主播和首批分集")
    album_detail.add_argument("album_id", type=positive_int)
    tracks = commands.add_parser("tracks", help="Web 声音列表；服务端每页 30 条")
    tracks.add_argument("album_id", type=positive_int)
    tracks.add_argument("--page", type=positive_int, default=1)
    tracks.add_argument("--sort", type=int, choices=[0, 1], default=0)
    mobile = commands.add_parser("mobile-tracks", help="旧移动声音列表和地址可用数量")
    mobile.add_argument("album_id", type=positive_int)
    mobile.add_argument("--page", type=positive_int, default=1)
    mobile.add_argument("--check-audio", action="store_true", help="抽查一个非付费 MP3 的前 1024 字节，不保存文件")
    track = commands.add_parser("track", help="声音简介")
    track.add_argument("track_id", type=positive_int)
    track_page = commands.add_parser("track-page", help="单集详情、所属作品和主播")
    track_page.add_argument("track_id", type=positive_int)
    commands.add_parser("categories", help="作品分类目录")
    category_albums = commands.add_parser("category-albums", help="分类下的作品卡片")
    category_albums.add_argument("category_id", type=positive_int)
    category_albums.add_argument("--page", type=positive_int, default=1)
    category_albums.add_argument("--rows", type=bounded_positive_int, default=5)
    category_albums.add_argument("--metadata-values", default="", help="筛选节点名称，逗号分隔；不是 ID")
    category_albums.add_argument("--sort", type=int, choices=[1, 2, 3], default=1, help="1 综合 / 2 最近更新 / 3 最多播放")
    category_metadata = commands.add_parser("category-metadata", help="分类筛选元数据树")
    category_metadata.add_argument("category_id", type=positive_int)
    user = commands.add_parser("user", help="主播公开基本资料")
    user.add_argument("uid", type=positive_int)
    user_home = commands.add_parser("user-home", help="主播主页首批作品和声音，不保证完整分页")
    user_home.add_argument("uid", type=positive_int)
    user_albums = commands.add_parser("user-albums", help="主播公开作品分页")
    user_albums.add_argument("uid", type=positive_int)
    user_albums.add_argument("--page", type=positive_int, default=1)
    user_albums.add_argument("--rows", type=bounded_positive_int, default=5)
    user_albums.add_argument("--keyword", default="", help="官网参数 keyWord；非空过滤效果未验证")
    related_albums = commands.add_parser("related-albums", help="作品页 SEO 相关推荐（非个性化）")
    related_albums.add_argument("album_id", type=positive_int)
    comments = commands.add_parser("comments", help="单集公开评论")
    comments.add_argument("track_id", type=positive_int)
    comments.add_argument("--page", type=positive_int, default=1)
    comments.add_argument("--rows", type=bounded_positive_int, default=5)
    rank_tabs = commands.add_parser("rank-tabs", help="榜单目录（不代表已取得榜单作品）")
    rank_tabs.add_argument("--scene", type=positive_int, default=1)
    album_rating = commands.add_parser("album-rating", help="作品评分和评价显示开关")
    album_rating.add_argument("album_id", type=positive_int)
    album_reviews = commands.add_parser("album-reviews", help="作品最热或最新评价")
    album_reviews.add_argument("album_id", type=positive_int)
    album_reviews.add_argument("--page", type=positive_int, default=1)
    album_reviews.add_argument("--rows", type=bounded_positive_int, default=5)
    album_reviews.add_argument("--order", choices=["content-score-desc", "time-desc"], default="content-score-desc")
    review_replies = commands.add_parser("review-replies", help="作品评价回复")
    review_replies.add_argument("album_id", type=positive_int)
    review_replies.add_argument("comment_id", type=positive_int)
    review_replies.add_argument("--page", type=positive_int, default=1)
    review_replies.add_argument("--rows", type=bounded_positive_int, default=5)
    commands.add_parser("login-status", help="只输出登录是否有效，不输出账户资料")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        cookie = read_cookie(args.cookie_file)
        if args.command == "login-status" and not cookie:
            raise ApiError("请先通过环境变量或文件提供 Cookie")
        client = Client(cookie, args.timeout)
        if args.command == "search":
            body = client.search(args.keyword, args.core, args.page, args.rows, args.condition)
        elif args.command == "album":
            body = client.album(args.album_id)
        elif args.command == "album-detail":
            body = client.album_detail(args.album_id)
        elif args.command == "tracks":
            body = client.tracks(args.album_id, args.page, args.sort)
        elif args.command == "mobile-tracks":
            body = client.mobile_tracks(args.album_id, args.page)
        elif args.command == "track":
            body = client.track(args.track_id)
        elif args.command == "track-page":
            body = client.track_page(args.track_id)
        elif args.command == "categories":
            body = client.categories()
        elif args.command == "category-albums":
            body = client.category_albums(args.category_id, args.page, args.rows, args.metadata_values, args.sort)
        elif args.command == "category-metadata":
            body = client.category_metadata(args.category_id)
        elif args.command == "user":
            body = client.user(args.uid)
        elif args.command == "user-home":
            body = client.user_home(args.uid)
        elif args.command == "user-albums":
            body = client.user_albums(args.uid, args.page, args.rows, args.keyword)
        elif args.command == "related-albums":
            body = client.related_albums(args.album_id)
        elif args.command == "comments":
            body = client.comments(args.track_id, args.page, args.rows)
        elif args.command == "rank-tabs":
            body = client.rank_tabs(args.scene)
        elif args.command == "album-rating":
            body = client.album_rating(args.album_id)
        elif args.command == "album-reviews":
            body = client.album_reviews(args.album_id, args.page, args.rows, args.order)
        elif args.command == "review-replies":
            body = client.review_replies(args.album_id, args.comment_id, args.page, args.rows)
        else:
            body = client.login_status()
        output = {"ok": True, "command": args.command, "result": summary(args.command, body)}
        if args.command == "related-albums":
            output["result"]["items"] = [x for x in output["result"]["items"] if str(x.get("id")) != str(args.album_id)]
        if args.command == "mobile-tracks" and args.check_audio:
            output["audio_check"] = probe_audio(list_at(body, "list"), args.timeout)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except ApiError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('{"ok":false,"error":"已取消"}', file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
