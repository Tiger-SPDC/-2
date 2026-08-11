"""URL 规范化：用于去重指纹与内容指纹的稳定性。"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 跟踪类参数，规范化时移除（避免同内容因参数不同被判为不同 URL）
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "ref_src",
    "spm",
    "from",
}


def canonicalize_url(url: str) -> str:
    """规范化 URL：小写 host、去 www、去 fragment、去跟踪参数、排序 query、去尾斜杠。

    支持 http/https 及 file:// 等常见 scheme；无法解析时原样返回。
    """
    url = url.strip()
    if not url:
        return url

    parts = urlsplit(url)
    scheme = parts.scheme.lower()

    if parts.hostname:
        host = parts.hostname.lower()
        if host.startswith("www."):
            host = host[4:]
        try:
            if parts.port:
                host = f"{host}:{parts.port}"
        except ValueError:
            pass  # 非法端口，忽略端口
        netloc = host
    else:
        netloc = parts.netloc.lower()

    query = parts.query
    if query:
        params = sorted(
            (k, v)
            for k, v in parse_qsl(query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        )
        query = urlencode(params)
    else:
        query = ""

    path = parts.path
    if path and path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, ""))
