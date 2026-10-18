# JM 下载助手 · Android 版

把 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)（Python API for JMComic）
搬到 Android 上：**Python 核心（Chaquopy）+ 原生 Java 界面**，不跑 Flask、不起本地端口。

原项目 `jm-download-assistant`（Flask + 网页 UI，MIT）的逻辑被拆成四层 Python 模块，
界面按同一套交互与设计令牌重写。

---

## 一、这个工程是什么

| 层 | 实现 | 说明 |
| --- | --- | --- |
| 界面 | **Java**（AppCompat + Material 3 + RecyclerView） | 底部四个页签：**下载 / 本机 / 收藏 / 设置** |
| 业务 | Python `jmcore`（vendor 在本工程内） | 目录、记录账本、任务编排、日志 |
| 下载能力 | 上游 `jmcomic`（vendor，源码） | 域名、接口加解密、拆图、并发、合并 PDF |
| 运行时 | Chaquopy 17.1 / Python 3.13 | 进程内运行，无外部依赖 |

```
app/src/main/python/
├── jmcore/        ← 本项目写的业务代码（从 Flask 版 app.py 拆出来）
├── jmcomic/       ← 上游源码（只有 1 处 Android 补丁：异步客户端可选导入 curl_cffi）
└── common/        ← commonx 0.6.40（纯 Python，原样）
```

**当前状态**：`assembleDebug` / `assembleRelease` 均已跑通，release 包约 45.8 MB
（arm64-v8a + x86_64），版本 1.02。Python 侧业务逻辑自测见 `tools/python_smoke_test.py`。
详见 [`docs/03-构建与验证记录.md`](docs/03-构建与验证记录.md)。

---

## 二、功能对照

| 原网页版 | Android 版 | 状态 |
| --- | --- | --- |
| 输入编号 → 下载 → 自动合并 PDF | 同（前台服务 + 通知栏进度） | ✅ |
| **下载页只留输入框 / 两个按钮 / 进度 / 日志** | 同（整屏垂直居中，日志为底部浮层） | ✅ |
| 下载记录（两行合并、按文件名去重） | 同，独立放在 **「本机」页** | ✅ |
| **记录列表预览缩略图** | PDF 首屏本地渲染（`PdfRenderer`），带磁盘/内存缓存 | ✅ |
| 点击记录用默认程序打开 | FileProvider + `ACTION_VIEW` | ✅ |
| 长按记录 | 打开 / 导出到“下载” / 删除 | ✅ |
| ★ 收藏 / 取消收藏 / 🗑 删除 | 对话框二次确认后执行 | ✅ |
| 收藏夹自动纳管已有文件（编号 `-`） | 同 | ✅ |
| 设置页：目录、迁移、磁盘三段条 | 目录只读（分区存储）+ 磁盘三段条 + 并发/Cookie/代理 + 导出 | ✅（迁移能力留在 Python，界面未开放） |
| 深色模式 | 同（记住选择，无白屏闪烁，日志区同步变暗） | ✅ |
| **下载进度 / 网速** | 状态栏与通知栏显示页数、速度、百分比，进度条为确定进度 | ✅ |
| **代理** | HTTP / SOCKS5，支持用户名密码、域名白名单；测试含 TCP 连通性 + 4 项协议检查 | ✅ |
| 运行日志 | 同（最近 60 行 + 通知栏摘要） | ✅ |
| 打开文件夹 | 改为「导出到系统下载目录」（MediaStore，Android 10+） | ✅ |

---

## 三、怎么跑起来

### 3.1 前置

* Android Studio（本工程按 AGP **9.4.1** / compileSdk **37** 配置）
* JDK 17 及以上（Studio 自带 JBR 即可）
* 本机 Python **3.13**（Chaquopy 用它预编译字节码；大版本必须一致）

> 如果你的 Studio 是 AGP 8.x，把根 `build.gradle.kts` 的 AGP 改成你的版本、
> `app/build.gradle.kts` 的 `compileSdk` 改成旧写法（`compileSdk = 35`），
> 并把 Chaquopy 降到 16.1（16.1 支持 AGP 7.0~8.13）。

### 3.2 构建

```powershell
# 首次：复制配置模板并填写 SDK 路径（签名见第 3.3 节）
copy local.properties.example local.properties

# 调试包
.\gradlew.bat :app:assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk

# 正式包（release，需配置签名）
.\gradlew.bat :app:assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

* 首次构建约 **10~15 分钟**：Chaquopy 要从 `chaquo.com` 下 Python 运行时与 Android 轮子
  （国内网络较慢，换网络或挂代理会快很多）。
* `local.properties` 里的 `sdk.dir` 要指向你自己的 SDK。
* 仓库**不包含**构建产物（`build/`、`dist/`）与签名文件（`keystore/`、`*.jks`）。

### 3.3 release 签名

`app/build.gradle.kts` 从 `local.properties` 读取以下四项，密码不写进仓库：

```properties
jm.storeFile=keystore/jm-release.jks
jm.storePassword=
jm.keyAlias=jm
jm.keyPassword=
```

把维护者提供的 `jm-release.jks` 放到 `keystore/`，填好密码后执行
`.\gradlew.bat :app:assembleRelease`；也可以用 Android Studio 的
**Build → Generate Signed App Bundle / APK → APK** 向导。

> ⚠️ 这个 keystore 决定以后能否给已安装用户发升级包，请妥善备份，且不要提交到仓库。
> 没有签名文件时，`assembleDebug` 仍可正常构建。

### 3.3 首次启动

1. 允许通知（前台服务的进度要显示）；
2. 进入「设置 → 运行环境自检」，确认：
   * `modules.jmcomic` / `common` / `Crypto` / `PIL` / `yaml` / `img2pdf` 全为 `ok`；
   * `transport` 显示 `OkHttpBackend`；
3. 回「下载」页输入纯数字编号 → 开始下载；通知栏与页面都会滚动日志。

---

## 四、代码地图

| 文件 | 作用 |
| --- | --- |
| `core/Py.java` | Java→Python 唯一入口；线程池 + JSON 约定 + 初始化 |
| `core/HttpBridge.java` | Python→Java 的 HTTP 落地（替代 `curl_cffi` 的关键） |
| `python/jmcore/net.py` | 用注册表把 `curl_cffi` 这两个 key 换成 Android 实现 |
| `python/jmcore/task.py` | 单任务状态机、option 组装、下载编排、日志 |
| `python/jmcore/store.py` | 记录账本（解析/合并/写入/抹除/纳管） |
| `python/jmcore/paths.py` | 目录、settings.json、迁移、磁盘统计 |
| `python/jmcore/api.py` | 对外 JSON 接口（`init/state/records/favorites/...`） |
| `service/DownloadService.java` | 前台服务 + 通知栏进度 |
| `core/PdfThumbnails.java` | PDF 首屏缩略图（PdfRenderer + 磁盘/内存两级缓存） |
| `ui/DownloadFragment.java` | 下载页：输入 + 预览 + 下载 + 进度 + 可展开的日志浮层 |
| `ui/LocalFragment.java` | 本机页：下载记录列表（搜索 / 刷新 / 收藏 / 删除） |
| `ui/FavoritesFragment.java` | 收藏页：同构，数据来自收藏目录 |
| `ui/SettingsFragment.java` | 设置页：目录、磁盘三段条、并发 / Cookie / 代理、关于 |
| `tools/python_smoke_test.py` | 桌面端业务逻辑自测（28 项） |

设计说明：

* [`docs/01-项目逻辑结构分析.md`](docs/01-项目逻辑结构分析.md) —— 原项目分层、记录格式、状态机、接口清单
* [`docs/02-Android移植方案与Chaquopy可行性.md`](docs/02-Android移植方案与Chaquopy可行性.md) —— Chaquopy 事实核查、依赖矩阵、方案对比
* [`docs/03-构建与验证记录.md`](docs/03-构建与验证记录.md) —— 真实构建输出、APK 核对、测试结果、未验证项

---

## 五、更新记录

### v1.0.1（当前）

**一键清除数据 + 拖动自动滚动 + release 签名**

| 类型 | 内容 |
| --- | --- |
| 新增 | 设置 → 工具 →「**清除所有下载数据**」：删除下载目录与收藏目录下的全部 PDF 与日志、清空图片工作区。**两次确认**：第一次说明不可恢复，第二次再问「确定删除」，按钮样式与工具卡片里其它按钮一致 |
| 新增 | 拖动设置卡片时，**靠近屏幕上/下边缘会自动缓慢滚动页面**（越靠边越快，16ms 一帧），可以把卡片拖到当前屏幕之外的位置 |
| 工程 | **release keystore**：`keystore/jm-release.jks`，密码存于 `local.properties`（均不进仓库，keystore 需向维护者获取）。`assembleRelease` 出可直接分发的正式签名包 |

### v1.9（历史）

| 类型 | 内容 |
| --- | --- |
| 调整 | 下载页主内容从屏幕约 1/3 处开始排布，不再垂直居中；底部运行日志条位置不变 |
| 调整 | **运行日志只保留本次启动的内容**：`jmcore.api.init()` 里清空日志总线；下载记录与收藏记录长期保留 |
| 改进 | 拖动设置卡片时，被拖卡片 `translationZ` 抬高到最上层 |
| 改进 | 拖到其它卡片之间的空位时，其它卡片自动让位，可预览松手后的布局 |

### v1.8

**下载页品牌化 + 已下载识别 + 设置页细节**

| 类型 | 内容 |
| --- | --- |
| 新增 | **已下载识别**：输入编号后自动比对 `jm_log.txt`，命中则状态显示「已下载」，并在进度条下方展示该漫画的信息卡（缩略图 / 编号 / 标题 / 时间，与本机页同款），**不会拉起下载**；点「开始下载」会二次确认「已下载过，是否重新下载」 |
| 新增 | 下载页品牌区：紫色圆角方块 `JM` + 「JM 下载助手」+「移动端」，替换原来的左上角文字与英文版本号 |
| 调整 | 设置页所有卡片统一 **12dp** 上下间距（此前只有「存储位置」有间距，其余贴在一起） |
| 调整 | 磁盘环形图：中心只显示「下载目录 + 收藏目录」占本机存储的百分比；「已用 / 共」移到左侧图例下方；图例补上「收藏目录」独立色块 |
| 调整 | 项目主页卡片文案改为「单击此卡片前往项目主页查看更新」 |
| 修复 | 暗黑模式下编号输入框看不到边框：描边改用 ColorStateList（平时 `border_strong`、聚焦品牌色），线宽 1.5dp |

### v1.7

**界面继续打磨：品牌区、圆角系统、环形图、卡片排序**

| 类型 | 内容 |
| --- | --- |
| 新增 | 下载页左上角大号「JM 下载助手」，页面中间显示 `JM Download Assistant` + 下标版本角标；去掉顶部工具栏，避免标题重复 |
| 调整 | 「预览封面 / 开始下载」与编号输入框**同高**（56dp）；进度条改为常驻（空闲是灰色轨道，下载时填充品牌色） |
| 新增 | **全局圆角**：设置页 5 档滑杆（方框 / 小 / 中 / 大 / 胶囊），改完弹「需要重启」提示；`Ui.apply()` 递归套用到卡片、按钮、输入框、进度条、对话框 |
| 新增 | **磁盘占用环形图**：左侧三色图例，右侧环形饼图 |
| 新增 | **设置卡片可拖动排序**：长按卡片标题上下拖动，顺序存 SharedPreferences |
| 新增 | 卡片底色：页面浅灰 + 卡片白，层次与 PC WebUI 一致 |
| **改动** | **收藏不再复制 PDF**：点星标只在收藏目录的 `jm_fav_log.txt` 里记一行文件名，收藏页读日志再回下载目录取文件 |
| 修复 | 状态永远显示「已完成」；界面出现「null」字样 |

### v1.6

| 类型 | 内容 |
| --- | --- |
| 新增 | **「本机」页**：下载完成后的记录都在这里（搜索、刷新、缩略图、长按菜单、收藏/删除全部照旧） |
| 重做 | **下载页**：主内容（编号输入 / 预览封面 / 开始下载 / 状态 / 进度条）整屏垂直居中；底部是 56dp 的「运行日志」条，点开从底部升起覆盖下半屏 |
| 设计 | 日志面板是**独立浮层**，不参与主内容布局 —— 折叠、展开、日志滚动时输入框和按钮位置完全不动；展开高度取 45%，正好不遮挡输入框与按钮 |
| 修复 | **状态永远显示「已完成」**：`jmcore.api.state()` 把接口成功标志写进了 `payload['ok']`，覆盖了任务结果；改为 `api_ok` |
| 修复 | **界面出现「null」字样**（收藏页警告条、设置页代理框）：Android 的 `org.json` 对 JSON `null` 会返回字符串 `"null"`，统一在 `Models.str()` 里折成空串 |
| 修复 | 目录路径显示被截成「…omic.android/files/JM/漫画」，改为保留 `files/` 之后的部分（`…/JM/漫画`） |
| 调整 | 下载中**不再自动展开日志**，底部日志条已显示最后一行；下载结束若面板开着会自动收起，让「已完成 / 标题」露出来 |

### v1.5

| 类型 | 内容 |
| --- | --- |
| 修复 | **进度条不动**：`request_with_retry()` 把 `is_image` 当成形参吃掉了，传输层永远看不到这个标记 → 改为挂在 `JmImageResp.transfer_to()` 上计数（每张图保存时 +1） |
| 修复 | **代理密码保存后无法再修改**：保存成功后会 `load()` 清空密码/Cookie 输入框。现在保存后保留输入；只有首次进入页面才清空；提示语改为「留空＝保持不变，输入新密码可修改」 |
| 改进 | 环境自检里新增 `progress.hooked`，可以直接确认进度计数器是否挂上 |

### v1.4

| 类型 | 内容 |
| --- | --- |
| 修复 | **代理认证不生效**：Android 的 `HttpURLConnection` 对 HTTPS CONNECT 的 407 认证不可靠 → 传输层改用 **OkHttp**，`proxyAuthenticator` 对普通请求与 CONNECT 隧道都能正确重试 |
| 修复 | 代理测试目标从 `google` 换成 `baidu/generate_204`（只验证代理链路，不依赖能否翻墙），失败时自动做一次**直连对照**并弹窗给出完整错误与排查建议 |
| 修复 | **下载结束后进度条一直转**：结束时隐藏页面进度条；通知栏最终状态不再挂一个不确定进度 |

### v1.3

| 类型 | 内容 |
| --- | --- |
| 新增 | **下载进度 + 网速**：传输层按图片累计字节数，状态栏/通知栏显示「45/120 页 · 3.2 MB/s · 37%」，进度条改成确定进度 |
| 新增 | **代理认证**：代理地址支持 `host:port` / `http://user:pass@host:port`，并新增独立的用户名、密码输入框；设置页可一键测试代理连通性 |
| 修复 | 代理之前根本没生效（只写给了 requests 后端，实际走的是 OkHttp/HttpURLConnection）——现在真正使用代理 |
| 修复 | **下载页记录列表几乎滑不动**：顶部固定内容挤占了 `weight=1` 的列表空间。现在进度/日志默认折叠，下载时自动展开 |

### v1.2

| 类型 | 内容 |
| --- | --- |
| 新增 | **下载前预览**：输入编号点「预览封面」，先看到封面 / 标题 / 作者 / 页数 / 章节 / 标签，再决定是否下载 |
| 新增 | **导出运行日志**：状态卡右上角一键导出到系统 `下载/JM/jm-log-时间.txt`（Android 10+；更低版本写到应用外部目录并提示路径） |
| 修复 | **深色模式切换后页面叠加、再次切换卡死**：Activity recreate 后按 tag 恢复 Fragment 引用（之前会重复 add）、保存当前 Tab、切换加 800ms 防抖并跳过「已是目标模式」的重复 recreate |
| 修复 | **WebP 图片下载失败**（`cannot identify image file`）：Chaquopy 的 Pillow 缺 `_webp.so` → 运行时用 Android `BitmapFactory` 解码成 PNG 再交给 Pillow，保存时 `.webp` 改存 `.jpg` |
| 修复 | 环境自检里增加 Pillow WebP 支持状态与 imagefix 补丁状态，便于排查 |

### v1.1

| 类型 | 内容 |
| --- | --- |
| 修复 | `AttributeError: 'AndroidResponse' object has no attribute 'request'` —— 上游 `raise_if_resp_should_retry()` 会读 `resp.request.url`，已在传输层补齐 `request / ok / history / elapsed / encoding` 等 curl_cffi 兼容字段 |
| 修复 | `Set-Cookie` 未解析导致 `resp.cookies` 为空（移动端接口要求带 cookie）—— Java 侧保留多值头，Python 侧解析成字典 |
| 新增 | 记录列表显示 **PDF 首屏缩略图**（本地 `PdfRenderer` 渲染，历史记录与收藏同样生效；磁盘 + 内存两级缓存） |
| 新增 | 长按记录弹出「打开 / 导出到“下载” / 删除」 |
| 修复 | 切深色模式白屏闪烁：窗口背景跟随主题、切换前先刷窗口底色、去掉窗口重建动画 |
| 修复 | 深色模式下运行日志 / 状态徽标仍是白底：补齐 `values-night` 配色与状态栏图标颜色 |

### v1.0

首个可构建版本（下载 / 记录 / 收藏 / 设置 / 前台服务）。

---

## 六、已知限制

1. `curl_cffi` 用不了（没有 Android 轮子），改为 Android 原生 TLS；
   指纹不等价，极端网络环境下仍可能被拦。
2. `img2pdf` 只能用 0.3.1（0.4+ 强制依赖 `pikepdf`，后者没有 Android 轮子）；
   合并 PDF 的功能不受影响。
3. 下载任务不可中断（上游没有 cancel 语义）。
4. 目录固定在应用私有外部存储，暂未接 SAF；可用「导出到下载」把 PDF 放到公共目录。
5. 首次启动需要几秒解压 Python 运行时，属正常现象。
6. 代理支持 **HTTP(S) / SOCKS5**（含账号密码与域名白名单）；SOCKS4 未支持。
7. 网速是「累计字节 / 已用时间」的平均值，不是瞬时速度。

---

## 七、许可与声明

* 本项目：MIT。
* 上游 `JMComic-Crawler-Python`：MIT，版权归 hect0x7；`commonx`：MIT，版权归 hect0x7。
  二者以源码形式随包分发，未改变其授权条件。
* 本项目不含任何内容数据，所有内容均来自第三方站点；仅供个人学习与技术研究，
  请遵守所在国家/地区的法律法规，未满 18 岁请勿使用。
