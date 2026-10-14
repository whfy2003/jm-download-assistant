#注意，本项目绝大部分代码组件来自AI生成，兼容性不可预见，恶性bug未知，请不要小头控制大头，谨慎部署

# JM 下载助手（本地网页版）

把 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 包装成「双击即用」的本地下载工具：
**图形化安装向导 ＋ 网页操作界面 ＋ 自动合并 PDF ＋ 下载记录与收藏管理**。

---

## ⚠️ 重要声明（请先读这一段）

**本项目的全部下载能力，均来自开源项目 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)（作者：hect0x7）。**

- 本项目**不是** JMComic-Crawler-Python 的官方项目，**与上游官方仓库、原作者没有任何隶属关系**
- 本项目所做的工作仅仅是：
  1. **简化安装方式** —— 打包成 exe，自带 Python 运行环境，双击即可安装运行
  2. **提供 WebUI** —— 把命令行操作变成网页点点点，方便不熟悉命令行的用户
  3. **补充周边功能** —— 自动合并 PDF、下载记录、收藏夹、目录迁移、磁盘占用显示
- 涉及**核心下载能力**的问题（下载失败、域名失效、接口变更、403、需要登录 cookie 等），
  请优先查阅[上游项目文档](https://jmcomic.readthedocs.io/zh-cn/latest/)与 [issues](https://github.com/hect0x7/JMComic-Crawler-Python/issues)，
  这些逻辑由上游实现，本项目没有重复实现
- **本项目的 bug（网页界面、安装程序、打包相关问题）请提到本仓库，不要提到上游项目**，谢谢配合
- 如果你只需要核心功能，强烈建议直接使用上游项目：`pip install jmcomic -U`

> 上游项目地址：https://github.com/hect0x7/JMComic-Crawler-Python

---

## 下载

**不想折腾环境？直接去 [Releases](https://github.com/whfy2003/jm-download-assistant/releases/latest) 下载现成的：**

| 下载哪个 | 大小 | 适合谁 |
| --- | --- | --- |
| **JM下载助手-安装程序.exe** | 约 86 MB | 大多数人。双击安装，可自选安装位置与下载 / 收藏目录；自带运行环境，**无需安装 Python**；支持从系统「应用」里卸载 |
| **JM下载助手-绿色版.zip** | 约 61 MB | 免安装。解压后双击里面的 `JM下载助手.exe` 即可用，整个文件夹可拷到 U 盘带走 |

> 下载页：**https://github.com/whfy2003/jm-download-assistant/releases/latest**

---

## 功能一览

**下载页**
- 输入本子编号 → 后台下载 → 自动合并为一个 PDF 存入本地目录
- 下载记录读取同目录日志，同一个本子只显示一条（标题行与文件名行自动合并）
- 单击记录用系统默认程序打开 PDF
- 每条记录：★ 收藏（复制一份到收藏夹）/ 🗑 删除文件并从日志抹去记录
- 按编号搜索（最近 500 条 / 全部）、刷新数据、实时状态与运行日志

**收藏页**
- 收藏夹独立目录与独立日志，支持查看、搜索、打开、取消收藏、删除
- 收藏夹里原本已有的漫画会自动登记进日志（编号显示为 `-`），无需手工整理

**设置页**
- 修改下载目录 / 收藏目录，保存时**自动把原目录内容整体迁移**到新位置
- 迁移规则：只搬变化的项、同名不覆盖、旧目录空后自动删除、拒绝非法路径
- 显示两个目录的占用与所在磁盘的总容量 / 已用 / 可用

**界面**
- 与官方 `jm-view-server` 同一套设计令牌（品牌色 `#5b5bd6`、圆角卡片、侧栏 + 顶栏）
- 浅色 / 深色主题一键切换并记住
- 侧栏磁盘占用条：**橙色＝该目录占用 · 紫色＝同盘其它占用 · 灰色＝可用**，鼠标悬停展开显示具体数字

---

## 快速开始

### 方式一：安装包（推荐，无需 Python 环境）

1. 下载 `JM下载助手-安装程序.exe`（约 86 MB）
2. 双击运行，在向导里选择三个位置：
   - **安装位置**：程序装到哪里（默认 `D:\JM下载助手`）
   - **下载目录**：漫画 PDF 与记录日志存哪里
   - **收藏夹目录**：收藏副本存哪里
3. 点「开始安装」，几秒完成。之后双击桌面快捷方式即可使用

> 目标电脑**不需要安装 Python**，也不需要联网安装依赖。
> 程序完全本机运行，只监听 `127.0.0.1`，不对外开放任何服务。

**卸载**：Windows「设置 → 应用」里找到「JM 下载助手」卸载，或双击安装目录里的 `卸载.cmd`。
卸载时会询问是否一并删除下载目录与收藏夹的内容（默认不删）。

### 方式二：源码版

```bash
git clone https://github.com/whfy2003/jm-download-assistant.git
cd jm-download-assistant

# 建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ".\JMComic-Crawler-Python[plugins]"
.venv\Scripts\python.exe -m pip install flask

# 启动
start-jm-web.cmd
```

浏览器访问 http://127.0.0.1:8080

---

## 目录结构

```
├── README.md                  本文件
├── 开发文档.md                 架构、部署、打包与接口说明
├── 使用说明书.txt              给最终用户的文字说明书
├── 使用说明书-长图.png          给最终用户的图文说明书
├── LICENSE
├── .gitignore
│
├── webui/                     网页端（本项目的核心代码）
│   ├── app.py                 后端：Flask 路由、记录解析、目录迁移、磁盘占用
│   ├── launcher.py            启动器：首次运行向导、启动服务、卸载程序
│   ├── installer.py           安装程序：安装向导、写配置、注册卸载信息
│   ├── templates/index.html   页面结构
│   └── static/                样式与前端逻辑
│
├── JMComic-Crawler-Python/    上游项目源码（git submodule 或直接放入）
├── option.yml                 jmcomic 下载配置（域名、PDF 输出、cookies）
├── start-jm-web.cmd           启动脚本
└── stop-jm-web.cmd            停止脚本
```

> 打包好的 exe 不放在仓库里，统一在 [Releases](https://github.com/whfy2003/jm-download-assistant/releases) 页面发布。

> **注意**：`.venv/`、`_build/`、`_dist/`、`__pycache__/` 都不应提交，见 `.gitignore`。

---

## 已知问题

### 1. 安装程序创建的桌面快捷方式，路径可能指向错误

**现象**：安装完成后，桌面上的「JM 下载助手」快捷方式双击打不开，或提示找不到文件。

**原因**：安装程序在创建快捷方式时，个别情况下记录的目标路径不正确
（例如安装目录被移动过、或同一台电脑上装过多次到不同位置）。

**解决办法**（任选其一）：

1. **直接去安装目录里启动**：打开你安装时选择的目录（例如 `D:\JM下载助手`），
   双击里面的 `JM下载助手.exe`
2. **手动重建快捷方式**：在安装目录里右键 `JM下载助手.exe`
   → 发送到 → 桌面快捷方式
3. **删掉旧的错误快捷方式**，再用上面的方法建一个新的

> 如果你改变了安装目录的位置，旧快捷方式一定会失效，请按第 2 条重建。

### 2. 上游核心功能的已知限制

以下问题属于上游项目范畴，请查阅[上游文档](https://jmcomic.readthedocs.io/zh-cn/latest/)：

- 网页端接口（`impl: html`）在部分网络环境返回 403（本项目已默认改用移动端 `impl: api`）
- 少数本子提示「只对登录用户可见」，需要在 `option.yml` 里填 AVS cookie
- 域名失效需要等待上游更新

---

## 免责声明

1. 本项目**仅供个人学习与技术研究使用**，请勿用于任何商业用途
2. 本项目不含任何内容数据，所有内容均来自第三方网站，本项目不存储、不传播任何内容
3. 使用者应自行遵守所在国家/地区的法律法规。因使用本项目产生的一切后果由使用者自行承担
4. 本项目按「现状」提供，不提供任何形式的担保
5. 本项目涉及的内容可能包含成人向素材，**未满 18 岁请勿使用**
6. 请合理使用，不要一次性批量抓取过多，以免给对方服务器造成压力

---

## 致谢

- **[JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)** —— 本项目的全部下载能力来自该项目，感谢作者 hect0x7
- [jm-view-server](https://github.com/hect0x7/jm-view-server) —— 界面设计参考了它的设计令牌
- [curl-cffi](https://github.com/lexiforest/curl_cffi) / [Flask](https://flask.palletsprojects.com/) / [img2pdf](https://github.com/josch/img2pdf) / [PyInstaller](https://pyinstaller.org/)

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。

上游项目 JMComic-Crawler-Python 同样采用 MIT 许可证，其版权归原作者所有。
