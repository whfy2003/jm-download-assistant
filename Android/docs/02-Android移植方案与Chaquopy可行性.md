# Android 移植方案与 Chaquopy 可行性分析

> 结论先行：**可以，但不是「原样塞进 APK」**。
> Chaquopy 能跑 `jmcomic` 的绝大部分逻辑，唯一硬阻塞是 `curl_cffi`（TLS 指纹库）没有
> Android 轮子。把这个「传输层」换掉之后，Python 核心可以完整跑在 Android 进程内，
> 界面用原生 Java 重写。本项目即按此实现。

---

## 一、结论与边界

| 问题 | 回答 |
| --- | --- |
| 能不能用 Chaquopy 跑这个项目的核心？ | 能。Python 3.13 + 已 vendor 的 `jmcomic` / `commonx` 源码；原生扩展只要 `pycryptodome`、`Pillow`，Chaquopy 都有 Android 轮子 |
| 有没有硬阻塞？ | 有一个：`curl_cffi`（依赖 libcurl-impersonate）没有 Android 轮子，Chaquopy 17 起只接受预编译轮子，**无法编译安装** |
| 阻塞怎么绕？ | 不绕过它，而是**替换它**：`commonx` 的 Postman 是可注册组件，注册一个 Android 实现顶替 `curl_cffi` 这个 key 即可，上游业务代码一行不用改 |
| Flask 还要不要？ | 不要。Flask 在手机上多一层端口、回环、浏览器，收益为零 |
| 界面怎么做？ | 原生 Java（AppCompat + Material 3 + RecyclerView），三视图对应原网页三页 |
| 有什么代价？ | ① 首次启动要解压 Python 运行时（几秒）；② APK 体积 +20~40 MB；③ 所有网络都过 Python，调试不如纯 Java 直观 |

---

## 二、Chaquopy 事实核查（截至本次调研）

| 项 | 结论 | 来源 |
| --- | --- | --- |
| 最新版本 | **17.1.0**（2026-10-12） | [版本对照表](https://chaquo.com/chaquopy/doc/current/versions.html) |
| 插件坐标 | `id("com.chaquo.python") version "17.1.0"` → `com.chaquo.python:gradle:17.1.0` | [Gradle 插件文档](https://chaquo.com/chaquopy/doc/current/android.html) |
| 仓库 | **Maven Central**（不在 chaquo.com/maven，那里只有 pip 轮子） | 同上 |
| 支持的 AGP | 7.3 ~ **9.4** | 版本对照表 |
| 支持的 Python | 3.10 ~ 3.15（默认 3.10；3.8/3.9 已在 17.0 移除） | 版本对照表 |
| minSdk | ≥ 24 | Gradle 插件文档 |
| ABI | `arm64-v8a`、`x86_64`（Python 3.12+ 仅 64 位） | Gradle 插件文档 |
| 构建机 Python | 必须与 app 的 Python 大版本一致；Windows 上自动尝试 `py -3.13` → `py -3` → `python` | Gradle 插件文档 |
| pip 策略 | 17.0 起 `--only-binary`：**只能装轮子，不会现场编译** | 同上 |
| 轮子仓库 | `https://chaquo.com/pypi-13.1/`（所有版本共用），文件名带 `android_24_arm64_v8a` 之类的 ABI 标签 | 同上 |
| 双向调用 | Java→Python：`Python.getInstance().getModule(...).callAttr(...)`；Python→Java：`import java` / `jclass` | [Java API](https://chaquo.com/chaquopy/doc/current/java.html) |
| 存储 | `os.environ["HOME"]` 是应用私有目录；绝对不要用相对路径写文件 | Gradle 插件文档 |
| SSL | 用的是随包 certifi CA，不是系统 CA | 同上 |
| stdlib 限制 | 不支持 `crypt/grp/nis/spwd/curses/readline/tkinter`、`multiprocessing` 的 IPC 部分 | 同上 |

> 这就是为什么这个项目要 **Python 3.13**：17.1 的 Android 轮子目前覆盖到 cp313 最完整，
> 3.14/3.15 的轮子还很少。

---

## 三、依赖逐一判定

| 依赖 | 用途 | Android 可用性 | 处理 |
| --- | --- | --- | --- |
| `jmcomic` | 下载核心 | 纯 Python（源码 vendor） | ✅ 原样使用 + 2 处 Android 补丁 |
| `commonx`（import 名 `common`） | 工具库 + Postman 抽象 | 纯 Python，且**没有声明任何依赖** | ✅ 源码 vendor |
| `curl_cffi` | HTTPS + TLS 指纹 | ❌ 无 Android 轮子，PyPI 只有 mac/linux/win | **用 `jmcore/net.py` 顶替** |
| `pycryptodome` | 接口 AES 解密 | ✅ `chaquo.com/pypi-13.1/pycryptodome`（3.21.0，cp39–cp313） | `pip { install("pycryptodome") }` |
| `Pillow` | 图片解码 + 拆图还原 | ✅ `pillow`（11.0.0，cp313 有 android_24 轮子） | 同上 |
| `PyYAML` | option 解析 | ✅ `PyYAML`（6.0.3） | 同上 |
| `img2pdf` | 整本合并 PDF | ⚠️ 只有 **0.3.1** 可用：0.4+ 强制依赖 `pikepdf`（无 Android 轮子），pip 会自动回退 | 显式 `install("img2pdf==0.3.1")` |
| `pikepdf` | **仅** PDF 加密时用 | ❌ 依赖 qpdf C++，无 Android 轮子 | 不装；只做「合并」不做「加密」 |
| `psutil` / `rich` / `py7zr` / `pyzipper` / `browser_cookie3` | 上游可选插件 | ❌/未验证 | 不装；把 `plugins.dependencies_strategy` 设为 `ignore-only-log` |
| `requests` | 桌面端传输后端 | ✅ 纯 Python | 作为 Android 失败时的兜底 |

**关键结论**：阻塞点只有「网络传输」和「PDF 加密」两项；
前者已用可插拔 Postman 换掉，后者本来就没用到（`option.yml` 里没有 `encrypt`）。

---

## 四、方案对比与选型

| 方案 | 做法 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- |
| **A. Flask + WebView** | Python 起 Flask 监听 127.0.0.1，WebView 加载 | 前端零改动，最快出原型 | 多一层回环服务；后台/锁屏易被杀；`os.startfile` 等仍需替换；界面手感是网页 | 备选 |
| **B. Chaquopy + 原生 UI**（本项目） | Python 只做业务，Java 做界面 | 体验最好；无端口；可用前台服务、FileProvider、MediaStore；调试点清晰 | Java 侧要重写三页；跨语言调试稍麻烦 | ✅ **采用** |
| **C. 纯 Kotlin/Java 重写** | 不用 Python，直接实现 JM 协议 | APK 最小、最快 | 要把 AES/拆图/域名/重试全部重写并长期跟进上游；工作量与维护成本最高 | 不推荐（除非彻底脱离上游） |
| **D. 电脑跑服务 + 手机当客户端** | PC 上仍跑 Flask，手机 App 只连它 | 手机端最轻 | 必须开电脑；内网穿透/鉴权；离线不可用 | 不适合「单机 App」诉求 |
| **E. Termux / python-for-android** | 完整 CPython | 兼容性最好 | Termux 出不了 Gradle 工程；p4a 需要给每个 C 扩展写 recipe | 不适合 Android Studio 交付 |

选 B 的核心理由：这个项目的价值在**流程编排 + 记录账本**，不在网络层；
把这部分留在 Python，界面交给原生，是改动量、稳定性、体验三者最平衡的点。

---

## 五、本项目的落地结构

```
app/src/main/
├── java/com/jmcomic/android/
│   ├── JmApp.java                 Application（PyApplication 子类，启动 Python）
│   ├── core/
│   │   ├── Py.java                Java → Python 唯一入口（线程池 + JSON 约定）
│   │   ├── HttpBridge.java        Python → Java 的 HTTP 落地（HttpURLConnection/OkHttp TLS）
│   │   ├── Models.java            JSON → 强类型
│   │   ├── FileOps.java           FileProvider 打开 / 导出到系统下载 / 目录统计
│   │   └── ...
│   ├── ui/                        MainActivity + 三个 Fragment + RecyclerView + 自定义占用条
│   └── service/DownloadService.java  前台服务（通知栏进度）
└── python/
    ├── jmcore/                    ← 从 app.py 拆出来的四层（无 Flask）
    │   ├── api.py                 暴露给 Java 的 JSON 接口
    │   ├── paths.py               目录 / settings.json / 迁移 / 磁盘
    │   ├── store.py               记录账本
    │   ├── task.py                单任务状态机 + 下载编排 + 日志
    │   ├── net.py                 Postman 适配层（顶替 curl_cffi）
    │   └── logbus.py              日志环形缓冲
    ├── jmcomic/                   上游源码（vendor）
    └── common/                    commonx 0.6.40（vendor）
```

### 5.1 跨语言约定：只传 JSON 字符串

```java
// Java
Py.call("records", json -> adapter.submit(Models.Record.list(json)), "all", "350234");
```

```python
# Python
@_safe
def records(scope='all', q=''):
    items = store.download_records(scope, q)
    return {'ok': True, 'records': items, ...}
```

好处：跨语言只有 `String` 一种类型，异常也在 Python 侧统一转成 `{"ok":false,"error":...}`，
不会出现「Chaquopy 把 Java 异常包装成 PyObject」那种难查的问题。

### 5.2 传输层：用注册表把 `curl_cffi` 换掉

`commonx` 的 Postman 是注册式组件：

```python
# common/postman/__init__.py
ComponentRegistry.register_component(Postman, 'postman_key', globals().values(), False)
```

于是只要在初始化时再注册一次同 key 的实现，就能整体替换：

```python
class CurlCffiCompatPostman(_AndroidPostman):
    postman_key = 'curl_cffi'          # ← 直接占用上游的 key

class CurlCffiSessionCompatPostman(_AndroidSessionPostman):
    postman_key = 'curl_cffi_session'
```

`option.yml` 里原本的 `client.postman.type: curl_cffi` **不用改**，
`JmModuleConfig.new_postman()` 里的 `Postmans.new_session()` 也一并被接管。

响应对象补齐了上游用到的字段：
`status_code / content / text / url / headers / redirect_count / json() / cookies`。

### 5.3 为什么还要走 Java 发请求

两层后端，自动选择：

1. **OkHttpBackend**（设备上）：`jclass("...HttpBridge").fetch(...)`，
   同步 `HttpURLConnection`（Android 内部就是 OkHttp + Conscrypt/BoringSSL）。
   好处：TLS 指纹接近真实 App，Cloudflare 拦截概率显著低于 CPython 的 `ssl`。
2. **RequestsBackend**（桌面 / 兜底）：`requests`。

重定向在 Java 侧手动跟随，好让 Python 拿到 `redirect_count`（上游 html 端会读它）。

### 5.4 线程与生命周期

* 所有 Python 调用走 `Py` 的固定线程池（4 线程），**绝不占主线程**；
* 下载本体由 Python 线程执行（上游内部还有图片/章节并发池）；
* 前台服务每秒轮询 `state()` 刷通知，下载结束自动 `stopSelf()`；
* 界面用 `state().logs` 的**条数变化**判断是否需要刷新日志，避免每 1.5 s 重绘文本。

### 5.5 存储策略

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 成品 PDF | `getExternalFilesDir()/JM/漫画` | 应用私有外部目录，免权限，卸载即清 |
| 收藏 PDF | `getExternalFilesDir()/JM/收藏` | 同上 |
| 图片工作区 | `getExternalFilesDir()/JM/work` | 合并 PDF 后自动清空 |
| 设置 / 日志 | 同上（`settings.json`、`jm_log.txt`） | 与原项目格式一致 |
| 想让自己在文件管理器里看到 | 记录菜单「导出到“下载”」 | MediaStore 写入 `Download/JM`，Android 10+ |

> 原项目「设置里随便填绝对路径」在 Android 上不成立（分区存储）。
> 因此改为固定沙箱目录 + 导出，`paths.set_dirs()` 的迁移能力保留在 Python 侧供扩展使用。

---

## 六、构建与运行

### 6.1 环境

* Android Studio 2026.2.1（自带 AGP 9.4.1、SDK 37、build-tools 36）
* JDK 17+（Studio 自带 JBR 25 即可）
* 本机 Python **3.13**（Chaquopy 用它做字节码预编译；版本必须与 app 一致）

### 6.2 步骤

```powershell
# 1) 用 Studio 打开 JmComicAndroid 目录（不要 Import 整个 WorkA）
# 2) 确认 local.properties 里的 sdk.dir 指向你的 SDK
# 3) 首次同步会下载：Chaquopy 插件、Python 运行时、Android 轮子（约 100 MB）
# 4) 运行
.\gradlew.bat :app:assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

### 6.3 常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `No matching distributions available for pycryptodome` | 网络到 `chaquo.com` 不通 | 挂代理，或先手动下载轮子用 `install("xxx.whl")` 指本地文件 |
| `Python version 3.13 not found` | 构建机没有 3.13 | 装 3.13，或在 `chaquopy {}` 里写死 `buildPython("...")` |
| `Failed to resolve: com.chaquo.python` | 仓库配置缺 `mavenCentral()` | 检查根 `settings.gradle.kts` |
| 构建时 pip 反复回溯 `img2pdf` 版本 | 0.4+ 要 `pikepdf`，装不上 | 已钉 `img2pdf==0.3.1`（只依赖 Pillow，合并功能足够） |
| 首次启动卡白屏 3~5 s | 解压 Python 运行时 | 正常现象；`python.stdout` 可在 logcat 里看到进度 |
| 下载 403 | 网络/域名/风控 | 换网络、设置页填代理或 AVOID cookie；见 `diagnose()` |

---

## 七、风险与未覆盖项（务必知晓）

1. **TLS 指纹不是 100% 等价**：OkHttp 的指纹比 curl_cffi 的 chrome 指纹弱，
   极端情况下仍可能被 Cloudflare 拦。缓解：`HttpBridge` 与 `net.py` 都是可替换的，
   后续可换 Conscrypt 自定义配置，或加 cookie/代理。
2. **下载不可中断**：上游没有 cancel 语义，本项目与网页版一致——只能等它跑完。
3. **没有自定义目录（SAF）**：要在任意目录读写需要 `ACTION_OPEN_DOCUMENT_TREE` +
   `DocumentFile`，PDF 由 Python 直接写盘，这一步需要额外一层桥接，属于下一步。
4. **收藏页只纳管顶层 PDF**：与原项目一致（子目录不纳管）。
5. **未做 iOS**：Chaquopy 只服务 Android。
6. **合规**：上游与本项目均为 MIT；内容来自第三方站点，本项目不存储、不传播。
   代码里没有硬编码任何域名/密钥，域名与接口逻辑都在 vendored 的上游源码里。

---

## 八、后续可做（按性价比排序）

1. **下载队列**：现在是单任务串行，可加一个持久化队列（Room 或 JSON）；
2. **SAF 自定义目录**：让用户选 SD 卡/下载目录；
3. **封面预览**：`jmcomic` 能拿封面 URL，列表里加缩略图；
4. **批量编号**：`download_batch` 上游已支持，界面加「多行编号」入口；
5. **失败重试按钮**：状态卡上加「重试上次编号」；
6. **记录导入导出**：把 `jm_log.txt` 迁到新手机。
