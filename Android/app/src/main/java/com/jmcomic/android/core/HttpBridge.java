package com.jmcomic.android.core;

import android.util.Base64;

import org.json.JSONObject;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.Credentials;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * Python 侧 HTTP 传输的落地实现（由 jmcore/net.py 调用）。
 *
 * 为什么不用 Python 自己发请求：
 *  - CPython 的 ssl 指纹很容易被 Cloudflare 识别；
 *  - OkHttp 走 Android 的原生 TLS（Conscrypt/BoringSSL），更像真实 App。
 *
 * 为什么从 HttpURLConnection 换成 OkHttp：
 *  Android 的 HttpURLConnection 对「HTTPS 代理 + 407 认证」支持不可靠
 *  （CONNECT 隧道阶段的凭据常常没被带上），表现为“代理填了也没用”。
 *  OkHttp 的 proxyAuthenticator 对普通请求和 CONNECT 隧道都能正确重试。
 *
 * 约定：把 Python 传来的参数变成一次 HTTP 请求，返回 JSON：
 *   {status, url, headers, body(base64), redirects} 或 {error}
 * 重定向手动跟随，好让 Python 拿到 redirect_count。
 */
public final class HttpBridge {

    private static final int MAX_REDIRECTS = 8;

    private static volatile OkHttpClient cachedClient;
    private static volatile String cachedKey;

    private HttpBridge() {
    }

    public static String fetch(String method,
                               String url,
                               String headersJson,
                               String bodyBase64,
                               String bodyType,
                               boolean allowRedirects,
                               int timeoutMs) {
        return fetch(method, url, headersJson, bodyBase64, bodyType,
                allowRedirects, timeoutMs, "http", null, 0, null, null);
    }

    /**
     * @param proxyType http / socks（OpenClash 的 mixed 端口两种都支持）
     * @param proxyHost 代理主机；为空表示直连
     * @param proxyPort 代理端口
     * @param proxyUser 代理认证用户名（可空）
     * @param proxyPass 代理认证密码（可空）
     */
    public static String fetch(String method,
                               String url,
                               String headersJson,
                               String bodyBase64,
                               String bodyType,
                               boolean allowRedirects,
                               int timeoutMs,
                               String proxyType,
                               String proxyHost,
                               int proxyPort,
                               String proxyUser,
                               String proxyPass) {
        JSONObject out = new JSONObject();
        try {
            JSONObject headers = new JSONObject(
                    headersJson == null || headersJson.isEmpty() ? "{}" : headersJson);
            byte[] body = (bodyBase64 == null || bodyBase64.isEmpty())
                    ? new byte[0]
                    : Base64.decode(bodyBase64, Base64.DEFAULT);

            OkHttpClient client = clientFor(proxyType, proxyHost, proxyPort,
                    proxyUser, proxyPass, timeoutMs);

            String currentUrl = url;
            String currentMethod = method == null ? "GET" : method.toUpperCase();
            byte[] currentBody = body;
            int redirects = 0;

            while (true) {
                Request request = buildRequest(currentMethod, currentUrl,
                        headers, currentBody, bodyType);
                Response response = client.newCall(request).execute();
                try {
                    int code = response.code();

                    if (isRedirect(code) && allowRedirects && redirects < MAX_REDIRECTS) {
                        String location = response.header("Location");
                        if (location == null || location.isEmpty()) {
                            return finish(out, response, currentUrl, redirects);
                        }
                        currentUrl = resolve(currentUrl, location);
                        redirects++;
                        if (code == 303
                                || ((code == 301 || code == 302) && "POST".equals(currentMethod))) {
                            currentMethod = "GET";
                            currentBody = new byte[0];
                        }
                        continue;
                    }

                    return finish(out, response, currentUrl, redirects);
                } finally {
                    response.close();
                }
            }
        } catch (Throwable t) {
            try {
                out.put("error", t.getClass().getSimpleName() + ": " + t.getMessage());
            } catch (Exception ignored) {
            }
            return out.toString();
        }
    }

    private static String finish(JSONObject out, Response response,
                                 String fallbackUrl, int redirects) throws Exception {
        byte[] payload = response.body() == null ? new byte[0] : response.body().bytes();
        String finalUrl = response.request().url().toString();
        if (finalUrl == null || finalUrl.isEmpty()) {
            finalUrl = fallbackUrl;
        }

        out.put("status", response.code());
        out.put("url", finalUrl);
        out.put("headers", headersToJson(response));
        out.put("body", Base64.encodeToString(payload, Base64.NO_WRAP));
        out.put("redirects", redirects);
        return out.toString();
    }

    private static Request buildRequest(String method, String url, JSONObject headers,
                                        byte[] body, String bodyType) throws Exception {
        Request.Builder builder = new Request.Builder().url(url);

        Iterator<String> keys = headers.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            String value = headers.optString(key, null);
            if (value == null) {
                continue;
            }
            String lower = key.toLowerCase();
            // 这些头由 OkHttp 自己管理，手动设置会冲突
            if (lower.equals("host") || lower.equals("content-length")
                    || lower.equals("connection") || lower.equals("accept-encoding")
                    || lower.equals("transfer-encoding")
                    || lower.equals("proxy-authorization")) {
                continue;
            }
            builder.header(key, value);
        }

        RequestBody requestBody = null;
        if (body != null && body.length > 0
                && !"GET".equals(method) && !"HEAD".equals(method)) {
            MediaType type = MediaType.parse(contentType(bodyType));
            requestBody = RequestBody.create(type, body);
        } else if ("POST".equals(method) || "PUT".equals(method) || "PATCH".equals(method)) {
            // OkHttp 要求这几个方法必须有 body
            requestBody = RequestBody.create(null, new byte[0]);
        }

        builder.method(method, requestBody);
        return builder.build();
    }

    private static String contentType(String bodyType) {
        if ("json".equals(bodyType)) {
            return "application/json; charset=utf-8";
        }
        if ("form".equals(bodyType)) {
            return "application/x-www-form-urlencoded; charset=utf-8";
        }
        return "application/octet-stream";
    }

    private static synchronized OkHttpClient clientFor(String proxyType, String proxyHost,
                                                       int proxyPort, String proxyUser,
                                                       String proxyPass, int timeoutMs) {
        String key = nullToEmpty(proxyType) + '|' + nullToEmpty(proxyHost) + ':' + proxyPort + '|'
                + nullToEmpty(proxyUser) + '|' + nullToEmpty(proxyPass) + '|' + timeoutMs;
        if (cachedClient != null && key.equals(cachedKey)) {
            return cachedClient;
        }

        OkHttpClient.Builder builder = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(Math.max(15000, timeoutMs), TimeUnit.MILLISECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .followRedirects(false)
                .followSslRedirects(false)
                .retryOnConnectionFailure(true);

        if (proxyHost != null && !proxyHost.trim().isEmpty() && proxyPort > 0) {
            boolean socks = "socks".equalsIgnoreCase(proxyType);
            builder.proxy(new Proxy(socks ? Proxy.Type.SOCKS : Proxy.Type.HTTP,
                    new InetSocketAddress(proxyHost.trim(), proxyPort)));

            if (proxyUser != null && !proxyUser.isEmpty()) {
                final String user = proxyUser;
                final String pass = proxyPass == null ? "" : proxyPass;

                if (socks) {
                    // SOCKS5 的用户名/密码由 JDK 在握手阶段通过全局 Authenticator 回调
                    installSocksAuthenticator(user, pass);
                } else {
                    // 普通请求的 407 与 HTTPS CONNECT 的 407 都会走到这里
                    builder.proxyAuthenticator((route, response) -> {
                        if (response.request().header("Proxy-Authorization") != null) {
                            return null;         // 已经试过了，别死循环
                        }
                        return response.request().newBuilder()
                                .header("Proxy-Authorization", Credentials.basic(user, pass))
                                .build();
                    });
                }
            }
        }

        OkHttpClient built = builder.build();
        cachedClient = built;
        cachedKey = key;
        return built;
    }

    private static void installSocksAuthenticator(final String user, final String pass) {
        java.net.Authenticator.setDefault(new java.net.Authenticator() {
            @Override
            protected java.net.PasswordAuthentication getPasswordAuthentication() {
                if (getRequestorType() != RequestorType.PROXY) {
                    return null;
                }
                return new java.net.PasswordAuthentication(user,
                        pass == null ? new char[0] : pass.toCharArray());
            }
        });
    }

    private static boolean isRedirect(int code) {
        return code == 301 || code == 302 || code == 303 || code == 307 || code == 308;
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static String resolve(String base, String location) {
        try {
            return new java.net.URL(new java.net.URL(base), location).toString();
        } catch (Exception e) {
            return location;
        }
    }

    private static JSONObject headersToJson(Response response) {
        JSONObject json = new JSONObject();
        for (Map.Entry<String, List<String>> entry : response.headers().toMultimap().entrySet()) {
            String key = entry.getKey();
            if (key == null || entry.getValue() == null || entry.getValue().isEmpty()) {
                continue;
            }
            try {
                List<String> values = entry.getValue();
                // 同一个头出现多次（典型是 Set-Cookie）用换行拼起来，Python 侧按行拆
                json.put(key, values.size() == 1 ? values.get(0) : String.join("\n", values));
            } catch (Exception ignored) {
            }
        }
        return json;
    }
}
