# -*- coding: utf-8 -*-
"""
jmcore.net —— HTTP 传输适配层（Android 版）

背景
----
上游 jmcomic 默认用 `curl_cffi` 发请求。curl_cffi 依赖 curl-impersonate 的
原生库，没有 Android 轮子，Chaquopy 也编不出来（`pip` 只接受预编译轮子）。
所以这里把「传输」这一层换掉，其它逻辑（加解密、拆图、并发、重试）全部沿用上游。

做法
----
commonx 的 Postman 是可注册的组件：

    ComponentRegistry.register_component(Postman, 'postman_key', [Clazz])

我们注册两个实现，直接占用 `curl_cffi` / `curl_cffi_session` 这两个 key，
于是 option.yml 里原有的 `type: curl_cffi` 无需修改，也能跑在 Android 上。

实际发包有两个后端：

1. `OkHttpBackend`（设备上默认）：通过 Chaquopy 调 Java 的
   `com.jmcomic.android.core.HttpBridge`，用 Android 自己的 TLS 栈
   （HttpURLConnection 内部就是 OkHttp 的 BoringSSL/Conscrypt），
   指纹比 CPython 的 ssl 更接近真实 App，能显著降低被 Cloudflare 拦的概率。
2. `RequestsBackend`（桌面调试 / 兜底）：用纯 Python 的 requests。

响应对象补齐了 jmcomic 用到的字段：status_code / content / text / url /
headers / redirect_count / json() / cookies。
"""
from __future__ import annotations

import base64
import json
import os
import threading
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import jmcore.paths as paths

DEFAULT_TIMEOUT = 30.0
MAX_REDIRECTS = 8


# --------------------------------------------------------------------------- #
# 响应对象
# --------------------------------------------------------------------------- #
class _RequestInfo:
    """请求侧信息。

    curl_cffi / requests 的 Response 都带 `.request`，上游会用它拿原始 URL
    （jm_client_impl.raise_if_resp_should_retry 里判断 /chapter_view_template）。
    我们这里补一个最小实现，避免 AttributeError。
    """

    def __init__(self, method, url, headers, body):
        self.method = (method or 'GET').upper()
        self.url = url or ''
        self.headers = headers or {}
        self.body = body

    def __repr__(self):
        return '<RequestInfo %s %s>' % (self.method, self.url)


class AndroidResponse:
    """尽量对齐 curl_cffi / requests 的 Response 接口。"""

    def __init__(self, status_code, url, headers, content, redirect_count=0):
        self.status_code = int(status_code or 0)
        self.url = url or ''
        self.headers = _HeaderMap(headers or {})
        self.content = content or b''
        self.redirect_count = int(redirect_count or 0)
        self._text = None
        self.cookies = {}

        # curl_cffi / requests 兼容字段
        self.request = None
        self.history = []
        self.elapsed = 0.0
        self.reason = ''
        self.encoding = None
        self.ok = 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.content.decode(self._encoding(), errors='replace')
        return self._text

    def _encoding(self) -> str:
        ctype = (self.headers.get('content-type') or '')
        for part in ctype.split(';'):
            part = part.strip()
            if part.lower().startswith('charset='):
                return part.split('=', 1)[1].strip().strip('"') or 'utf-8'
        return 'utf-8'

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise IOError('HTTP %s: %s' % (self.status_code, self.url))

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return '<AndroidResponse %s %s>' % (self.status_code, self.url)


class _HeaderMap(dict):
    """大小写不敏感的头字典（保留原始键，同时提供小写别名）。"""

    def __init__(self, raw: dict):
        super().__init__()
        self._lower = {}
        for key, value in raw.items():
            key = str(key)
            value = str(value)
            dict.__setitem__(self, key, value)
            self._lower[key.lower()] = value

    def get(self, key, default=None):
        if key in self:
            return dict.get(self, key)
        return self._lower.get(str(key).lower(), default)

    def __getitem__(self, key):
        if key in self:
            return dict.__getitem__(self, key)
        return self._lower[str(key).lower()]


# --------------------------------------------------------------------------- #
# 后端 1：Android 原生 HTTP（经 Chaquopy 调 Java）
# --------------------------------------------------------------------------- #
class OkHttpBackend:

    def __init__(self):
        self._bridge = None
        self._lock = threading.Lock()
        self._broken = False

    def available(self) -> bool:
        if self._broken:
            return False
        try:
            self._get_bridge()
            return True
        except Exception:
            return False

    def _get_bridge(self):
        if self._bridge is None:
            from java import jclass
            self._bridge = jclass('com.jmcomic.android.core.HttpBridge')
        return self._bridge

    def fetch(self, method, url, headers, body, body_type, timeout, allow_redirects,
              proxy=None):
        bridge = self._get_bridge()
        config = proxy or {}
        raw = bridge.fetch(
            method,
            url,
            json.dumps(headers or {}, ensure_ascii=False),
            base64.b64encode(body or b'').decode('ascii'),
            body_type or 'none',
            bool(allow_redirects),
            int(max(1.0, timeout or DEFAULT_TIMEOUT) * 1000),
            config.get('type') or 'http',
            config.get('host'),
            int(config.get('port') or 0),
            config.get('user'),
            config.get('password'),
        )
        data = json.loads(str(raw))
        if data.get('error'):
            raise IOError('HTTP 失败: %s' % data['error'])
        content = base64.b64decode(data.get('body') or '')
        return AndroidResponse(
            data.get('status'), data.get('url'), data.get('headers'),
            content, data.get('redirects', 0),
        )


# --------------------------------------------------------------------------- #
# 后端 2：纯 Python requests（桌面调试用）
# --------------------------------------------------------------------------- #
class RequestsBackend:

    def available(self) -> bool:
        try:
            import requests  # noqa: F401
            return True
        except Exception:
            return False

    def fetch(self, method, url, headers, body, body_type, timeout, allow_redirects,
              proxy=None):
        import requests

        kwargs = {
            'headers': headers or None,
            'timeout': timeout or DEFAULT_TIMEOUT,
            'allow_redirects': bool(allow_redirects),
        }
        if proxy:
            credential = ''
            if proxy.get('user'):
                credential = '%s:%s@' % (proxy['user'], proxy.get('password') or '')
            scheme = 'socks5' if proxy.get('type') == 'socks' else 'http'
            proxy_url = '%s://%s%s:%s' % (scheme, credential, proxy['host'], proxy['port'])
            kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}

        if body:
            if body_type == 'json':
                kwargs['data'] = body
                kwargs['headers'] = dict(headers or {}, **{'Content-Type': 'application/json'})
            elif body_type == 'form':
                kwargs['data'] = body
            else:
                kwargs['data'] = body

        resp = requests.request(method, url, **kwargs)
        return AndroidResponse(resp.status_code, resp.url, dict(resp.headers),
                               resp.content, len(resp.history))


_BACKENDS = [OkHttpBackend(), RequestsBackend()]


def _pick_backend():
    for backend in _BACKENDS:
        if backend.available():
            return backend
    raise RuntimeError('没有可用的 HTTP 后端（既没有 Android HttpBridge，也没有 requests）')


# --------------------------------------------------------------------------- #
# 组包
# --------------------------------------------------------------------------- #
def _merge_headers(base, extra):
    merged = {}
    for source in (base, extra):
        if not source:
            continue
        for key, value in dict(source).items():
            if value is None:
                continue
            # 头名大小写不敏感，先删掉同名旧项
            for existing in list(merged.keys()):
                if existing.lower() == str(key).lower():
                    del merged[existing]
            merged[str(key)] = str(value)
    return merged


def _cookies_to_header(cookies) -> str:
    if not cookies:
        return ''
    if isinstance(cookies, str):
        return cookies
    try:
        items = dict(cookies).items()
    except Exception:
        return ''
    return '; '.join('%s=%s' % (k, v) for k, v in items)


def _with_params(url: str, params) -> str:
    if not params:
        return url
    if isinstance(params, str):
        query = params
    else:
        query = urlencode(dict(params), doseq=True)
    parsed = urlparse(url)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    existing.extend(parse_qsl(query, keep_blank_values=True))
    return urlunparse(parsed._replace(query=urlencode(existing, doseq=True)))


def _encode_body(kwargs) -> tuple:
    """把 data / json 归一化成 (bytes, body_type)。"""
    if kwargs.get('json') is not None:
        raw = json.dumps(kwargs['json'], ensure_ascii=False).encode('utf-8')
        return raw, 'json'

    data = kwargs.get('data')
    if data is None:
        return b'', 'none'
    if isinstance(data, bytes):
        return data, 'raw'
    if isinstance(data, str):
        return data.encode('utf-8'), 'form'
    try:
        return urlencode(dict(data), doseq=True).encode('utf-8'), 'form'
    except Exception:
        return str(data).encode('utf-8'), 'form'


# --------------------------------------------------------------------------- #
# 请求入口
# --------------------------------------------------------------------------- #
def request(method: str, url: str, **kwargs) -> AndroidResponse:
    if kwargs.get('files'):
        raise NotImplementedError('Android 传输层暂不支持 multipart 上传')

    no_proxy = bool(kwargs.pop('_no_proxy', False))

    meta = kwargs.pop('_meta', None) or {}
    headers = _merge_headers(meta.get('headers'), kwargs.get('headers'))
    cookies = kwargs.get('cookies') or meta.get('cookies')
    cookie_header = _cookies_to_header(cookies)
    if cookie_header:
        headers = _merge_headers(headers, {'Cookie': cookie_header})

    if not any(k.lower() == 'user-agent' for k in headers):
        headers['User-Agent'] = ('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 '
                                 '(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36')

    url = _with_params(url, kwargs.get('params'))
    body, body_type = _encode_body(kwargs)

    timeout = kwargs.get('timeout') or meta.get('timeout') or DEFAULT_TIMEOUT
    if isinstance(timeout, (tuple, list)):
        timeout = timeout[0] if timeout else DEFAULT_TIMEOUT

    allow_redirects = kwargs.get('allow_redirects')
    if allow_redirects is None:
        allow_redirects = True

    backend = _pick_backend()
    proxy = None
    if not no_proxy:
        proxy = _proxy_for(url, force=bool(kwargs.pop('_force_proxy', False)))

    override_type = kwargs.pop('_proxy_type', None)
    if proxy is not None:
        ptype = override_type or proxy.get('type') or 'auto'
        proxy = dict(proxy, type=ptype)
        response = _fetch_with_proxy_type(backend, method, url, headers, body, body_type,
                                          timeout, allow_redirects, proxy)
    else:
        response = backend.fetch(method.upper(), url, headers, body, body_type,
                                 float(timeout), bool(allow_redirects), None)
    # 上游会读 resp.request.url，这里补上请求侧信息
    response.request = _RequestInfo(method, url, headers, body)
    # 上游的 ensure_have_cookies() 需要 resp.cookies（移动端接口强制带 cookie）
    response.cookies = _parse_set_cookie(response.headers)

    # 图片进度不在这里统计：上游把 is_image 当形参吃掉了，传输层拿不到这个标记。
    # 统一由 jmcore.progress.install() 挂在 JmImageResp.transfer_to 上计数。

    return response


def _fetch_with_proxy_type(backend, method, url, headers, body, body_type,
                           timeout, allow_redirects, proxy):
    """按代理协议发请求；auto 时先 HTTP，失败或 407 再换 SOCKS5。"""
    global _AUTO_TYPE

    if proxy.get('type') != 'auto':
        return backend.fetch(method.upper(), url, headers, body, body_type,
                             float(timeout), bool(allow_redirects), proxy)

    chosen = _AUTO_TYPE or 'http'
    primary = dict(proxy, type=chosen)
    try:
        response = backend.fetch(method.upper(), url, headers, body, body_type,
                                 float(timeout), bool(allow_redirects), primary)
    except Exception:
        if chosen == 'socks':
            raise
        response = backend.fetch(method.upper(), url, headers, body, body_type,
                                 float(timeout), bool(allow_redirects),
                                 dict(proxy, type='socks'))
        _AUTO_TYPE = 'socks'
        return response

    if response.status_code == 407 and chosen != 'socks':
        response = backend.fetch(method.upper(), url, headers, body, body_type,
                                 float(timeout), bool(allow_redirects),
                                 dict(proxy, type='socks'))
        _AUTO_TYPE = 'socks'
        return response

    _AUTO_TYPE = chosen
    return response


_AUTO_TYPE = None


def _proxy_config():
    """把设置里的代理字符串解析成 {host, port, user, password}。

    支持 `127.0.0.1:7890`、`http://host:port`、`user:pass@host:port`；
    单独填写的用户名/密码优先于 URL 里带的凭据。
    """
    raw = (paths.proxy() or '').strip()
    if not raw:
        return None

    text = raw
    if '://' in text:
        scheme, text = text.split('://', 1)
        if scheme.lower() not in ('http', 'https'):
            # 目前只支持 HTTP(S) 代理，SOCKS 需要额外实现
            return None
    text = text.rstrip('/')

    url_user = url_pass = None
    if '@' in text:
        credential, text = text.rsplit('@', 1)
        if ':' in credential:
            url_user, url_pass = credential.split(':', 1)
        else:
            url_user = credential

    if ':' not in text:
        return None
    host, port_text = text.rsplit(':', 1)
    try:
        port = int(port_text)
    except ValueError:
        return None
    if not host or not (0 < port < 65536):
        return None

    user, password = paths.proxy_credentials()
    return {
        'type': paths.proxy_type(),
        'host': host,
        'port': port,
        'user': user or url_user,
        'password': password or url_pass,
    }


def _proxy_for(url: str, force: bool = False):
    """按白名单决定这次请求是否走代理（对齐 ani-rss HttpReq 的 proxyList 思路）。

    * `proxy_only` 为空 → 所有请求都走代理；
    * 否则只有 host 等于白名单项、或以 `.<项>` 结尾才走代理；
    * `force=True`（测试代理）时忽略白名单。
    """
    config = _proxy_config()
    if config is None:
        return None
    if force:
        return config

    only = (paths.proxy_only() or '').strip()
    if not only:
        return config

    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        return None
    if not host:
        return None

    for line in only.splitlines():
        pattern = line.strip().lower()
        if not pattern:
            continue
        if pattern.startswith('*.'):
            pattern = pattern[2:]
        if host == pattern or host.endswith('.' + pattern):
            return config
    return None


def _parse_set_cookie(headers) -> dict:
    """把 Set-Cookie 头解析成字典。

    Java 侧对多值头用换行拼接，这里按行拆开；只取第一个分号前的 name=value。
    """
    raw = headers.get('set-cookie') if headers else None
    if not raw:
        return {}
    cookies = {}
    for line in str(raw).split('\n'):
        first = line.split(';', 1)[0].strip()
        if '=' in first:
            name, value = first.split('=', 1)
            name = name.strip()
            if name:
                cookies[name] = value.strip()
    return cookies


# --------------------------------------------------------------------------- #
# 注册进 commonx 的 Postman 组件表
# --------------------------------------------------------------------------- #
def install():
    from common import (AbstractPostman, AbstractSessionPostman,
                        ComponentRegistry, Postman)

    class _AndroidPostman(AbstractPostman):
        postman_key = 'android'

        def before_request(self, kwargs):
            merged = super().before_request(kwargs)
            merged.pop('impersonate', None)
            merged['_meta'] = self.meta_data
            return merged

        def __get__(self):
            return self._get

        def __post__(self):
            return self._post

        def _get(self, url, **kwargs):
            return request('GET', url, **kwargs)

        def _post(self, url, **kwargs):
            return request('POST', url, **kwargs)

    class _AndroidSession:
        """给 Postmans.new_session() 用的最小会话对象。"""

        def __init__(self, meta):
            self.meta_data = meta
            self.cookies = dict(meta.get('cookies') or {})
            self.headers = dict(meta.get('headers') or {})

        def _kwargs(self, kwargs):
            merged = dict(self.meta_data)
            merged.update(kwargs)
            if self.headers:
                merged['headers'] = _merge_headers(self.headers, kwargs.get('headers'))
            if self.cookies:
                merged.setdefault('cookies', self.cookies)
            merged.pop('impersonate', None)
            merged['_meta'] = self.meta_data
            return merged

        def get(self, url, **kwargs):
            return request('GET', url, **self._kwargs(kwargs))

        def post(self, url, **kwargs):
            return request('POST', url, **self._kwargs(kwargs))

    class _AndroidSessionPostman(AbstractSessionPostman):
        postman_key = 'android_session'

        def create_session(self, kwargs):
            return _AndroidSession(kwargs)

    # 用 Android 实现顶替 curl_cffi，这样 option.yml 不需要改
    class CurlCffiCompatPostman(_AndroidPostman):
        postman_key = 'curl_cffi'

    class CurlCffiSessionCompatPostman(_AndroidSessionPostman):
        postman_key = 'curl_cffi_session'

    classes = [
        _AndroidPostman, _AndroidSessionPostman,
        CurlCffiCompatPostman, CurlCffiSessionCompatPostman,
    ]
    ComponentRegistry.register_component(Postman, 'postman_key', classes)
    return [c.postman_key for c in classes]


def backend_name() -> str:
    try:
        return type(_pick_backend()).__name__
    except Exception as e:
        return 'unavailable: %s' % e
