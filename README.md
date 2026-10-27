# 喜马拉雅 API 参考

整理喜马拉雅主站与历史移动端的只读接口，帮助客户端接入**作品浏览、作品详情、分集目录、分类发现、主播作品与评论**，并保留搜索和免费音频地址验证说明。**这不是官方 SDK，也不保证接口长期稳定。**官方开放平台不在本项目范围内。

## 从这里开始

- [作品浏览与详情接入](Catalog_integration.md)：页面对应接口、卡片与详情字段映射、分页和浏览/下载分层。
- [搜索 API](Search_API.md)：专辑、声音、主播搜索，参数、分页与返回字段。
- [专辑、声音与音频地址](Album_information_and_audio_download_address.md)：专辑简介、声音列表、单条声音，以及旧移动接口的登录要求。
- [其他只读接口](Read_only_API.md)：分类、榜单、主播与评论等补充接口及限制。
- [作品评分、评价与分类筛选](Album_reviews_and_filters.md)：评分、最热/最新评价、回复及分类元数据。
- [请求与登录说明](Authentication.md)：Cookie 安全、业务状态码、常见失败和验证边界。

### 当前可用性

最近核验：**2026-10-27**。不同地区、账号、内容和时间的结果可能不同。

- **可匿名使用**：专辑 / 声音 / 主播搜索、作品详情、分集目录、分类及分类作品、主播主页、单集详情与评论。
- **主播作品和相关推荐**：已验证主播公开作品分页、作品页非个性化相关推荐；主页首批内容与独立分页接口不能混用。
- **需要分别判断**：榜单目录已可读，但不能据此保证榜单内容接口成功。
- **旧移动列表仍可使用**：返回声音列表，但不能保证匿名返回播放地址；免费样本在有效登录后返回了媒体地址。
- **不能混用新版路径**：`/revision/album/v1/getTracksList` 本次提示缺少 `webtk`；不带 `/v1/` 的旧 Web 列表路径仍可用。
- **不要继续照搬旧播放接口**：本次 `/revision/play/v1/audio` 返回 HTTP 404。

音频 URL 非空不等于一定能完整播放；列表、权限、媒体访问需要分别判断。不提供付费解密、DRM 绕过、验证码绕过或权限伪造。

## 本机验证工具

需要 **Python 3.10 或更新版本**，仅使用标准库，无需 `pip install`。

```bash
python3 scripts/ximalaya.py search '编程' --rows 5
python3 scripts/ximalaya.py search '编程' --core track --rows 3
python3 scripts/ximalaya.py search '编程' --core user --rows 3
python3 scripts/ximalaya.py album 9803351
python3 scripts/ximalaya.py album-detail 9803351
python3 scripts/ximalaya.py tracks 9803351 --page 1 --sort 0
python3 scripts/ximalaya.py track 47218632
python3 scripts/ximalaya.py categories
python3 scripts/ximalaya.py category-albums 3 --rows 3
python3 scripts/ximalaya.py user 3990327
python3 scripts/ximalaya.py user-home 3990327
python3 scripts/ximalaya.py user-albums 3990327 --rows 3
python3 scripts/ximalaya.py related-albums 9803351
python3 scripts/ximalaya.py comments 47218632 --rows 2
python3 scripts/ximalaya.py album-rating 24448864
python3 scripts/ximalaya.py album-reviews 24448864 --rows 3
python3 scripts/ximalaya.py mobile-tracks 9803351
```

工具输出 JSON 摘要。`mobile-tracks` 只显示各音质字段的非空地址数量，不会输出媒体 URL。成功退出码为 `0`，请求/业务/结构错误为 `1`，命令参数错误为 `2`；错误信息输出到 stderr。

### 使用自己的登录态

Cookie 相当于登录凭据。只在本机使用，不要发到 issue、提交进 Git、放在截图或公开日志里。建议通过隐藏输入提供，避免把 Cookie 原文写进 shell 历史：

```bash
# Bash：输入不会显示在屏幕上
read -r -s -p 'Cookie: ' XIMALAYA_COOKIE; printf '\n'
export XIMALAYA_COOKIE
python3 scripts/ximalaya.py login-status
python3 scripts/ximalaya.py mobile-tracks 9803351 --check-audio
unset XIMALAYA_COOKIE
```

也支持 `python3 scripts/ximalaya.py --cookie-file /你的私有目录/cookie.txt login-status`：文件只包含一行 Cookie 原始值，不带 `Cookie:` 前缀，权限建议设为 `600`；不要放在项目目录。指定文件时优先于环境变量，读取失败不会回退使用另一份凭据。

- `login-status` 只显示是否成功确认登录，不输出账号 ID、昵称、手机号或会员资料。
- `--check-audio` 只对返回 `isPaid=false` 且有地址的首个 MP3 读取最多 **1024 字节**，检查 HTTP、音频类型和文件头，不保存音频。
- API 请求只使用固定的 HTTPS 域名，不跟随重定向；媒体抽查使用独立请求，**不携带 Cookie**，只接受 `*.xmcdn.com` 并优先 HTTPS。
- 每次只读一个页面，不批量下载、不自动重试、不进行关注、订阅、发帖、购买等操作。
- 遇到 `webtk`、风控或验证码要求时停止，不尝试绕过。工具不是浏览器，不能保证复用 Cookie 后所有网站接口都可用。

## 开发与贡献

```bash
python3 -m unittest discover -s tests -v
```

离线测试只使用合成响应，不需要 Cookie，也不调用外部服务。CI 同样不注入个人账号凭据。

欢迎补充有依据的参数、字段和接口变化。请区分真实请求结果、源码中观察到的路径以及尚未验证的推测；分享内容前删除 Cookie、账号资料、临时媒体 URL 和风控令牌。

## 使用声明与许可

- 遵守平台规则与适用法律，控制请求频率，不影响服务正常使用。
- 仅处理自己有权访问和使用的内容；能读取接口不代表拥有复制、传播或商业使用授权。
- 保留原项目的 [CC BY-NC 4.0 许可](LICENSE)，转载请署名，禁止商业使用。接口返回的内容、音频和图片不因本项目许可而获得授权。

## 鸣谢

- 原项目：[qilishidai/ximalaya-API](https://github.com/qilishidai/ximalaya-API)
- API 参考：[hkslover/ximalaya](https://github.com/hkslover/ximalaya)
