"""离线回归：所有响应和凭据均为测试合成值，不访问喜马拉雅。"""

import argparse
import contextlib
from email.message import Message
import importlib.util
import io
import json
import os
import re
import shlex
from http.client import IncompleteRead
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SPEC = importlib.util.spec_from_file_location("ximalaya", Path(__file__).resolve().parents[1] / "scripts" / "ximalaya.py")
assert SPEC is not None and SPEC.loader is not None
xm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xm)


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


class ApiTests(unittest.TestCase):
    def test_web_success(self):
        opener = Opener(Response({"ret": 200, "data": {}}))
        self.assertEqual(xm.Client(opener=opener).album(1)["ret"], 200)
        self.assertEqual(opener.requests[0][0].get_method(), "GET")
        self.assertNotIn("Cookie", dict(opener.requests[0][0].header_items()))

    def test_mobile_has_different_success_code(self):
        opener = Opener(Response({"ret": 0, "list": []}))
        self.assertEqual(xm.Client(opener=opener).mobile_tracks(1)["ret"], 0)
        with self.assertRaises(xm.ApiError):
            xm.Client(opener=opener).album(1)

    def test_business_error_not_http_success(self):
        opener = Opener(Response({"ret": 407, "msg": "synthetic secret"}))
        with self.assertRaisesRegex(xm.ApiError, "webtk") as err:
            xm.Client(opener=opener).tracks(1)
        self.assertNotIn("synthetic secret", str(err.exception))

    def test_missing_or_invalid_ret(self):
        for body in ({}, [], {"ret": True}, {"ret": "200"}):
            with self.subTest(body=body), self.assertRaises(xm.ApiError):
                xm.Client(opener=Opener(Response(body))).album(1)

    def test_non_json(self):
        with self.assertRaisesRegex(xm.ApiError, "不是 JSON"):
            xm.Client(opener=Opener(Response(b"<html>synthetic captcha</html>"))).album(1)

    def test_numeric_time_is_not_normal_api_body(self):
        with self.assertRaises(xm.ApiError):
            xm.Client(opener=Opener(Response(b"1700000000000"))).album(1)

    def test_oversized_response(self):
        with self.assertRaisesRegex(xm.ApiError, "过大"):
            xm.Client(opener=Opener(Response(b"x" * (xm.MAX_JSON_BYTES + 1)))).album(1)

    def test_http_error_has_no_raw_body_or_url(self):
        error = HTTPError("https://example.invalid/synthetic-secret", 403, "secret", Message(), io.BytesIO(b"secret"))
        with self.assertRaisesRegex(xm.ApiError, "HTTP 403") as err:
            xm.Client(opener=Opener(error=error)).album(1)
        self.assertNotIn("secret", str(err.exception))

    def test_network_error_is_redacted(self):
        with self.assertRaises(xm.ApiError) as err:
            xm.Client(opener=Opener(error=URLError("synthetic-secret"))).album(1)
        self.assertNotIn("synthetic-secret", str(err.exception))

    def test_incomplete_http_response(self):
        with self.assertRaises(xm.ApiError) as err:
            xm.Client(opener=Opener(error=IncompleteRead(b"synthetic-private", 100))).album(1)
        self.assertNotIn("synthetic-private", str(err.exception))

    def test_cookie_header_only_to_allowed_api(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(cookie="synthetic=credential", opener=opener).album(1)
        self.assertEqual(opener.requests[0][0].get_header("Cookie"), "synthetic=credential")
        with self.assertRaises(xm.ApiError):
            xm.Client(cookie="synthetic=credential", opener=opener).get("https://example.invalid", "/")
        self.assertEqual(len(opener.requests), 1)

    def test_redirects_disabled(self):
        handler = xm.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_unicode_keyword_url_encoded(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener).search("编程 & Python")
        url = opener.requests[0][0].full_url
        self.assertIn("%E7%BC%96", url)
        self.assertIn("%26", url)
        self.assertIn("rows=5", url)

    def test_tracks_parameter_names(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener).tracks(123, 2, 1)
        self.assertTrue(opener.requests[0][0].full_url.endswith("albumId=123&pageNum=2&sort=1"))
        self.assertNotIn("pageSize", opener.requests[0][0].full_url)

    def test_album_detail_endpoint(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener).album_detail(123)
        self.assertTrue(opener.requests[0][0].full_url.endswith("/revision/album?albumId=123"))

    def test_mobile_parameter_names(self):
        opener = Opener(Response({"ret": 0}))
        xm.Client(opener=opener).mobile_tracks(123, 2)
        self.assertTrue(opener.requests[0][0].full_url.endswith("albumId=123&pageId=2"))

    def test_track_parameter_name(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener).track(123)
        self.assertTrue(opener.requests[0][0].full_url.endswith("/revision/track/simple?trackId=123"))

    def test_catalog_endpoint_parameters(self):
        cases = [
            ("categories", (), "/revision/category/v2/allCategory"),
            ("category_albums", (3, 2, 5), "/revision/category/v2/albums?categoryId=3&pageNum=2&pageSize=5&sort=1"),
            ("user", (123,), "/revision/user/basic?uid=123"),
            ("user_home", (123,), "/revision/user?uid=123"),
            ("user_albums", (123, 2, 3, ""), "/revision/user/pub?uid=123&page=2&pageSize=3&keyWord="),
            ("related_albums", (123,), "/revision/seo/hotWordAlbums?id=123&queryType=1"),
            ("category_metadata", (3,), "/revision/category/v2/metadata/info?categoryId=3"),
            ("album_rating", (123,), "/revision/comment/albumStatistics/123"),
            ("track_page", (456,), "/revision/track/trackPageInfo?trackId=456"),
            ("comments", (456, 2, 5), "/revision/comment/queryComments?trackId=456&page=2&pageSize=5"),
            ("rank_tabs", (1,), "/revision/rank/v4/rankTabs?sceneId=1"),
        ]
        for method, args, suffix in cases:
            with self.subTest(method=method):
                opener = Opener(Response({"ret": 200}))
                getattr(xm.Client(opener=opener), method)(*args)
                self.assertEqual(opener.requests[0][0].full_url, xm.WEB + suffix)

    def test_review_endpoints_use_mobile_success_and_timestamp(self):
        for method, args, expected in [
            ("album_reviews", (123, 2, 3, "time-desc"), "/album-comment-mobile/web/album/comment/list/query/1700000000000?albumId=123&pageId=2&pageSize=3&order=time-desc"),
            ("review_replies", (123, 456, 2, 3), "/album-comment-mobile/ipad/album/comment/reply/list/query/1700000000000?albumId=123&commentId=456&pageId=2&pageSize=3"),
        ]:
            with self.subTest(method=method), patch.object(xm.time, "time", return_value=1700000000):
                opener = Opener(Response({"ret": 0}))
                getattr(xm.Client(opener=opener), method)(*args)
                self.assertEqual(opener.requests[0][0].full_url, xm.MOBILE_API + expected)

    def test_category_metadata_uses_name_not_id(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener).category_albums(3, 1, 3, "女频", 2)
        url = opener.requests[0][0].full_url
        self.assertIn("metadataValues=%E5%A5%B3%E9%A2%91", url)
        self.assertIn("sort=2", url)


class CookieTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_absent_cookie(self):
        self.assertEqual(xm.read_cookie(), "")

    @patch.dict(os.environ, {"XIMALAYA_COOKIE": " synthetic=value "})
    def test_environment(self):
        self.assertEqual(xm.read_cookie(), "synthetic=value")

    @patch.dict(os.environ, {"XIMALAYA_COOKIE": "synthetic=environment"})
    def test_file_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.txt"
            path.write_text("synthetic=file\n", encoding="utf-8")
            self.assertEqual(xm.read_cookie(path), "synthetic=file")

    def test_missing_file(self):
        with self.assertRaisesRegex(xm.ApiError, "无法读取"):
            xm.read_cookie("/nonexistent/synthetic-cookie.txt")

    def test_empty_file_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.txt"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(xm.ApiError, "为空"):
                xm.read_cookie(path)

    def test_invalid_cookie_is_not_echoed(self):
        for cookie in ("synthetic=x\nsecret", "synthetic=x\rsecret", "Cookie: synthetic=secret"):
            with self.subTest(cookie=repr(cookie)), patch.dict(os.environ, {"XIMALAYA_COOKIE": cookie}), self.assertRaises(xm.ApiError) as err:
                xm.read_cookie()
            self.assertNotIn("secret", str(err.exception))

    def test_nul_in_cookie_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.txt"
            path.write_text("synthetic=x\x00secret", encoding="utf-8")
            with self.assertRaises(xm.ApiError) as err:
                xm.read_cookie(path)
            self.assertNotIn("secret", str(err.exception))


class SummaryTests(unittest.TestCase):
    def test_login_privacy(self):
        result = xm.summary("login-status", {"data": {"uid": 123, "mobile": "synthetic-private", "nickname": "private"}})
        self.assertEqual(result, {"authenticated": True})

    def test_login_without_uid_not_verified(self):
        with self.assertRaises(xm.ApiError):
            xm.summary("login-status", {"data": {}})

    def test_mobile_omits_urls(self):
        body = {"pageId": 1, "pageSize": 20, "list": [{"trackId": 1, "isPaid": False, "playUrl64": "https://synthetic-private"}, {"trackId": 2, "playUrl64": ""}]}
        result = xm.summary("mobile-tracks", body)
        self.assertEqual(result["audio_url_counts"]["playUrl64"], 1)
        self.assertNotIn("synthetic-private", json.dumps(result))

    def test_search_whitelist(self):
        result = xm.summary("search", {"data": {"result": {"response": {"currentPage": 1, "docs": [{"id": 1, "title": "合成标题", "play_path_64": "synthetic-private"}]}}}})
        self.assertEqual(result["items"], [{"id": 1, "title": "合成标题"}])

    def test_album_shape(self):
        result = xm.summary("album", {"data": {"albumId": 1, "currentUid": 99, "albumPageMainInfo": {"albumTitle": "合成专辑", "isPaid": False}}})
        self.assertEqual(result, {"albumId": 1, "albumTitle": "合成专辑", "isPaid": False})

    def test_tracks_empty_page(self):
        result = xm.summary("tracks", {"data": {"pageNum": 2, "tracks": []}})
        self.assertEqual(result["items"], [])

    def test_album_detail_contains_display_fields_not_account_data(self):
        body = {"data": {"albumId": 1, "currentUid": 999, "mainInfo": {"albumTitle": "合成作品", "cover": "//example.invalid/test.jpg", "detailRichIntro": "<p>简介</p>", "hasBuy": False}, "anchorInfo": {"anchorId": 2, "anchorName": "合成主播"}, "tracksInfo": {"trackTotalCount": 1, "tracks": [{"trackId": 3, "title": "合成分集"}]}}}
        result = xm.summary("album-detail", body)
        self.assertEqual(result["mainInfo"]["albumTitle"], "合成作品")
        self.assertEqual(result["anchorInfo"]["anchorId"], 2)
        self.assertEqual(result["tracksInfo"]["tracks"][0]["trackId"], 3)
        self.assertNotIn("currentUid", json.dumps(result))
        self.assertNotIn("hasBuy", json.dumps(result))

    def test_track_shape(self):
        self.assertEqual(xm.summary("track", {"data": {"trackInfo": {"trackId": 1, "title": "合成", "secret": 1}}}), {"trackId": 1, "title": "合成"})

    def test_schema_drift_not_silently_empty(self):
        for body in ({"data": {}}, {"data": {"tracks": "not-a-list"}}, {"data": {"tracks": [123]}}):
            with self.subTest(body=body), self.assertRaises(xm.ApiError):
                xm.summary("tracks", body)

    def test_catalog_summary_shapes(self):
        cases = [
            ("categories", {"data": {"categories": [{"id": 3, "title": "合成分类"}]}}),
            ("category-albums", {"data": {"total": 1, "pageNum": 1, "pageSize": 3, "currentUid": 999, "albums": [{"albumId": 1, "albumTitle": "合成作品"}]}}),
            ("user", {"data": {"uid": 1, "nickName": "合成主播", "mobile": "synthetic-private"}}),
            ("user-home", {"data": {"uid": 1, "pubPageInfo": {"totalCount": 1, "pubInfoList": [{"id": 2, "title": "合成作品"}]}, "trackPageInfo": {"totalCount": 0, "trackInfoList": []}, "fansPageInfo": {"private": "synthetic-private"}}}),
            ("user-albums", {"data": {"page": 2, "pageSize": 2, "totalCount": 5, "albumList": [{"id": 1, "title": "合成作品"}]}}),
            ("related-albums", {"data": {"hotWordAlbums": [{"id": 1, "title": "合成推荐"}]}}),
            ("album-rating", {"data": {"isAlbumCommentShow": True, "albumScore": 9.0, "totalCommentCount": 1}}),
            ("album-reviews", {"data": {"albumScore": 9.0, "scoreDiagram": {"fiveStar": 80}, "comments": {"list": [{"commentId": 1, "content": "合成评价", "clientInfo": "synthetic-private"}]}}}),
            ("review-replies", {"data": {"commentReplys": {"list": [{"replyId": 1, "content": "合成回复", "clientInfo": "synthetic-private"}]}}}),
            ("category-metadata", {"data": {"metadata": [{"id": 1, "name": "合成分类", "metadataValues": [{"id": 2, "name": "合成筛选"}]}]}}),
            ("comments", {"data": {"currentPage": 1, "totalPage": 2, "totalComment": 2, "pageSize": 1, "comments": [{"id": 1, "content": "合成评论", "replyCount": 0}]}}),
            ("rank-tabs", {"data": {"sceneId": 1, "tabLists": [{"id": 1, "name": "合成榜单", "tabWraps": []}]}}),
            ("track-page", {"data": {"trackInfo": {"trackId": 1, "title": "合成声音"}, "albumInfo": {"albumId": 2}, "userInfo": {"uid": 3}, "moreTracks": []}}),
        ]
        for command, body in cases:
            with self.subTest(command=command):
                result = xm.summary(command, body)
                self.assertTrue(result)
                self.assertNotIn("synthetic-private", json.dumps(result))
                self.assertNotIn("currentUid", json.dumps(result))

    def test_metadata_tree_rejects_invalid_nodes_and_excessive_depth(self):
        for nodes in (None, [123], "bad"):
            with self.subTest(nodes=nodes), self.assertRaises(xm.ApiError):
                xm.metadata_nodes(nodes)
        with self.assertRaises(xm.ApiError):
            xm.metadata_nodes([], depth=21)


class AudioTests(unittest.TestCase):
    def track(self, url: object = "http://aod.cos.tx.xmcdn.com/test.mp3?synthetic=value"):
        return {"trackId": 1, "isPaid": False, "playUrl64": url}

    def test_audio_range_no_cookie_and_https(self):
        response = Response(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"x" * 2000, 206, {"Content-Type": "audio/mpeg", "Content-Range": "bytes 0-1023/2010"})
        opener = Opener(response)
        result = xm.probe_audio([self.track()], opener=opener)
        request = opener.requests[0][0]
        self.assertEqual(request.get_header("Range"), "bytes=0-1023")
        self.assertIsNone(request.get_header("Cookie"))
        self.assertTrue(request.full_url.startswith("https://"))
        self.assertEqual(result["bytes_read"], 1024)
        self.assertEqual(response.read_sizes, [1024])
        self.assertNotIn("synthetic=value", json.dumps(result))

    def test_paid_or_unknown_permission_not_checked(self):
        for paid in (True, None, 0):
            track = self.track()
            track["isPaid"] = paid
            opener = Opener()
            with self.subTest(paid=paid), self.assertRaises(xm.ApiError):
                xm.probe_audio([track], opener=opener)
            self.assertEqual(opener.requests, [])

    def test_empty_address(self):
        with self.assertRaises(xm.ApiError):
            xm.probe_audio([self.track("")])

    def test_non_string_address(self):
        for value in (123, ["synthetic"], {"url": "synthetic"}):
            with self.subTest(value=value), self.assertRaises(xm.ApiError):
                xm.probe_audio([self.track(value)], opener=Opener())

    def test_untrusted_urls(self):
        for url in ("https://xmcdn.com.evil.invalid/a.mp3", "file:///etc/passwd", "https://user:password@a.xmcdn.com/a.mp3", "https://127.0.0.1/a.mp3", "https://a.xmcdn.com:8080/a.mp3", "https://a.xmcdn.com:bad/a.mp3", "https://[invalid/a.mp3"):
            opener = Opener()
            with self.subTest(url=url), self.assertRaises(xm.ApiError):
                xm.probe_audio([self.track(url)], opener=opener)
            self.assertEqual(opener.requests, [])

    def test_html_instead_of_audio(self):
        opener = Opener(Response(b"<html>synthetic</html>", 200, {"Content-Type": "text/html"}))
        with self.assertRaises(xm.ApiError):
            xm.probe_audio([self.track()], opener=opener)

    def test_audio_type_alone_is_not_enough(self):
        opener = Opener(Response(b"not-an-mp3", 200, {"Content-Type": "audio/mpeg"}))
        with self.assertRaises(xm.ApiError):
            xm.probe_audio([self.track()], opener=opener)

    def test_mp3_frame_header(self):
        opener = Opener(Response(b"\xff\xfb\x90\x00" + b"x" * 1020, 206, {"Content-Type": "audio/mpeg"}))
        self.assertEqual(xm.probe_audio([self.track()], opener=opener)["http_status"], 206)

    def test_aac_adts_not_mp3(self):
        for content_type in ("audio/aac", "audio/mpeg"):
            opener = Opener(Response(bytes.fromhex("fff15080001ffc"), 206, {"Content-Type": content_type}))
            with self.subTest(content_type=content_type), self.assertRaises(xm.ApiError):
                xm.probe_audio([self.track()], opener=opener)

    def test_truncated_and_invalid_mp3_headers(self):
        for sample in (b"ID3", b"ID3\x01\x00\x00\x00\x00\x00\x00", b"\xff\xfb", b"\xff\xfb\xf0\x00", b"\xff\xfb\x9c\x00"):
            with self.subTest(sample=sample):
                self.assertFalse(xm.looks_like_mp3(sample))

    def test_audio_redirect_not_followed(self):
        opener = Opener(error=HTTPError("https://a.xmcdn.com/test", 302, "redirect", Message(), io.BytesIO()))
        with self.assertRaisesRegex(xm.ApiError, "HTTP 302"):
            xm.probe_audio([self.track()], opener=opener)


class CliTests(unittest.TestCase):
    def test_new_command_parsing(self):
        for argv in (["album-detail", "1"], ["categories"], ["category-albums", "3", "--rows", "2"], ["user", "1"], ["user-home", "1"], ["user-albums", "1", "--rows", "3"], ["related-albums", "1"], ["track-page", "1"], ["comments", "1", "--page", "2"], ["rank-tabs", "--scene", "1"]):
            with self.subTest(argv=argv):
                self.assertEqual(xm.parser().parse_args(argv).command, argv[0])

    def test_validation(self):
        for value in ("0", "-1", "1.2", "abc"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                xm.positive_int(value)
        self.assertEqual(xm.positive_int("42"), 42)
        with self.assertRaises(argparse.ArgumentTypeError):
            xm.bounded_positive_int("101")
        for value in ("nan", "inf", "0", "-1", "121"):
            with self.subTest(timeout=value), self.assertRaises(argparse.ArgumentTypeError):
                xm.positive_timeout(value)

    @patch.dict(os.environ, {}, clear=True)
    def test_login_no_cookie_no_request(self):
        with patch.object(xm.Client, "login_status") as mocked, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(xm.main(["login-status"]), 1)
        mocked.assert_not_called()
        self.assertFalse(json.loads(err.getvalue())["ok"])

    @patch.dict(os.environ, {}, clear=True)
    def test_main_success(self):
        body = {"ret": 200, "data": {"trackInfo": {"trackId": 1, "title": "合成"}}}
        with patch.object(xm.Client, "track", return_value=body), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(xm.main(["track", "1"]), 0)
        self.assertEqual(json.loads(out.getvalue())["result"]["trackId"], 1)

    @patch.dict(os.environ, {}, clear=True)
    def test_main_business_failure(self):
        with patch.object(xm.Client, "album", side_effect=xm.ApiError("合成错误")), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(xm.main(["album", "1"]), 1)
        self.assertEqual(json.loads(err.getvalue()), {"ok": False, "error": "合成错误"})

    @patch.dict(os.environ, {}, clear=True)
    def test_recommendation_excludes_current_album(self):
        body = {"ret": 200, "data": {"hotWordAlbums": [{"id": 1, "title": "自己"}, {"id": 2, "title": "其他"}]}}
        with patch.object(xm.Client, "related_albums", return_value=body), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(xm.main(["related-albums", "1"]), 0)
        self.assertEqual([x["id"] for x in json.loads(out.getvalue())["result"]["items"]], [2])


class RankTests(unittest.TestCase):
    def test_ranking_id_format_preserved(self):
        self.assertEqual(xm.ranking_ids("100006,100149"), "100006,100149")
        for value in ("0", "-1", "01", "100006, 100149", "100006,", "100006&x=y", "abc"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                xm.ranking_ids(value)

    @patch.dict(os.environ, {"XIMALAYA_XM_SIGN": "synthetic-browser&&synthetic-session"})
    def test_sign_read_unchanged(self):
        self.assertEqual(xm.read_xm_sign(), "synthetic-browser&&synthetic-session")

    def test_sign_control_characters_redacted(self):
        for value in ("synthetic-secret\nvalue", " synthetic-secret", "xm-sign:synthetic-secret", "合成非ASCII", "s" * 16385):
            with self.subTest(value=value[:20]), patch.dict(os.environ, {"XIMALAYA_XM_SIGN": value}), self.assertRaises(xm.ApiError) as err:
                xm.read_xm_sign()
            self.assertNotIn("synthetic-secret", str(err.exception))

    def test_rank_no_sign_no_request(self):
        opener = Opener()
        with self.assertRaisesRegex(xm.ApiError, "XIMALAYA_XM_SIGN"):
            xm.Client(opener=opener).rank("100006")
        self.assertEqual(opener.requests, [])

    def test_direct_invalid_sign_no_request(self):
        for value in (123, "synthetic\r\ninjected", " synthetic"):
            opener = Opener()
            with self.subTest(value=value), self.assertRaises(xm.ApiError):
                xm.Client(opener=opener, xm_sign=value).rank("100006")
            self.assertEqual(opener.requests, [])

    def test_rank_default_omits_misleading_page_num(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener, xm_sign="synthetic-sign").rank("100006")
        request = opener.requests[0][0]
        self.assertEqual(request.full_url, xm.WEB + "/revision/rank/v4/element?rankingId=100006")
        self.assertEqual(request.get_header("Xm-sign"), "synthetic-sign")
        self.assertIsNone(request.get_header("Cookie"))

    def test_limit_encodes_top_n_not_page(self):
        opener = Opener(Response({"ret": 200}))
        xm.Client(opener=opener, xm_sign="synthetic-sign").rank("100006,100149", 3)
        self.assertTrue(opener.requests[0][0].full_url.endswith("rankingId=100006%2C100149&pageNum=3"))

    def test_invalid_direct_limit(self):
        for limit in (0, -1, 101, True, "3"):
            opener = Opener()
            with self.subTest(limit=limit), self.assertRaises(xm.ApiError):
                xm.Client(opener=opener, xm_sign="synthetic").rank("100006", limit)
            self.assertEqual(opener.requests, [])

    def test_sign_not_forwarded_to_other_api(self):
        opener = Opener(Response({"ret": 200}))
        client = xm.Client(opener=opener, xm_sign="synthetic")
        client.album(1)
        self.assertIsNone(opener.requests[0][0].get_header("Xm-sign"))
        with self.assertRaises(xm.ApiError):
            client.get(xm.MOBILE, "/test", xm_sign="synthetic")

    def test_rank_error_is_not_empty_success(self):
        opener = Opener(Response({"ret": 400, "msg": "synthetic-sign"}))
        with self.assertRaises(xm.ApiError) as err:
            xm.Client(opener=opener, xm_sign="synthetic-sign").rank("100006")
        self.assertNotIn("synthetic-sign", str(err.exception))

    def test_album_and_anchor_ranks_whitelist(self):
        body = {"data": {"currentUid": 123, "rankList": [
            {"rankId": 1, "contentType": 2, "count": 1, "albums": [{"id": 11, "albumTitle": "合成作品", "isSubscribe": True}], "anchors": []},
            {"rankId": 2, "contentType": 3, "count": 1, "albums": [], "anchors": [{"id": 22, "anchorName": "合成主播", "isFollow": True}]},
        ]}}
        result = xm.summary("rank", body)
        self.assertEqual(result["items"][0]["albums"][0]["id"], 11)
        self.assertEqual(result["items"][1]["anchors"][0]["id"], 22)
        for name in ("currentUid", "isSubscribe", "isFollow"):
            self.assertNotIn(name, json.dumps(result))

    def test_rank_parser(self):
        args = xm.parser().parse_args(["rank", "100006,100149", "--limit", "3"])
        self.assertEqual(args.ranking_ids, "100006,100149")
        self.assertEqual(args.limit, 3)
        self.assertIsNone(xm.parser().parse_args(["rank", "100006"]).limit)

    @patch.dict(os.environ, {"XIMALAYA_XM_SIGN": "synthetic-sign"})
    def test_main_rank(self):
        body = {"ret": 200, "data": {"rankList": [{"rankId": 1, "albums": [], "anchors": []}]}}
        with patch.object(xm.Client, "rank", return_value=body) as mocked, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(xm.main(["rank", "100006", "--limit", "3"]), 0)
        mocked.assert_called_once_with("100006", 3)
        self.assertNotIn("synthetic-sign", out.getvalue())


class DocumentationTests(unittest.TestCase):
    def test_json_examples_are_valid(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob("*.md"):
            for block in re.findall(r"```json\s*\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
                with self.subTest(document=path.name):
                    json.loads(block)

    def test_relative_links_exist(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if not target.startswith(("http:", "https:", "#", "mailto:")):
                    with self.subTest(document=path.name, target=target):
                        self.assertTrue((path.parent / target.split("#", 1)[0]).exists())

    def test_cli_examples_parse(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("python3 scripts/ximalaya.py "):
                    with self.subTest(document=path.name, command=line):
                        xm.parser().parse_args(shlex.split(line)[2:])


if __name__ == "__main__":
    unittest.main()
