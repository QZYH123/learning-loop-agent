# 35 — Windows/macOS 桌面外壳

**Type:** task

**Status:** resolved

**Source:** 产品要给学习者双击打开，而不是先开终端再开浏览器。目标用户以 Windows 为主，其次 macOS；WSL 只作为开发环境。

## 范围

做：用系统 WebView 包住现有 FastAPI + 前端；打包成 Windows 可执行目录，并预留 macOS `.app`；源码运行仍可开浏览器。

不做：Electron/Tauri、账号云同步、开机自启、安装器签名、Linux 发布包、重写原生界面。

## 设计规定

- 桌面壳只做进程编排：本机起现有 HTTP 服务，窗口加载同一套前端。契约、领域和页面不因外壳分叉。
- 从源码运行默认仍开浏览器（方便 WSL）；`--desktop` 打开窗口；打包后的冻结进程默认开窗口，`--browser` 可退回浏览器。
- 打包后的数据目录用系统用户目录（Windows `%LOCALAPPDATA%\LearningLoop`，macOS `~/Library/Application Support/LearningLoop`）；源码运行继续默认仓库 `data/`。`LEARNING_LOOP_DATA_DIR` 始终可覆盖。
- 字体不再走 Google Fonts CDN，随前端一起分发。
- 打印不用 `window.open` 弹窗，改隐藏 iframe，避免 WebView 拦截。
- `pywebview` / `pyinstaller` 放在 `requirements-desktop.txt`，不塞进开发用的 `requirements.txt`。

## 验收标准

1. `python3 -m backend.app` 在 WSL/源码下行为与现在一致（开浏览器）。
2. `python3 -m backend.app --desktop` 在已装桌面依赖的 Windows/macOS 上打开原生窗口。
3. 打包后的 Windows 目录可双击 `LearningLoop.exe` 打开同一套界面；数据写到用户目录。
4. 离线时界面字体和 KaTeX 仍可用。
5. 全量 pytest 通过；未安装 pywebview 时测试仍可通过。

## Comments

- 2026-08-22：按 Windows 主、macOS 次、WSL 仅开发来落地。

## Answer

已落地。`python3 -m backend.app` 源码默认仍开浏览器；`--desktop` 用 pywebview 打开系统窗口；打包进程默认窗口。数据目录：源码 `data/`，Windows 打包 `%LOCALAPPDATA%\LearningLoop`，macOS 打包 `~/Library/Application Support/LearningLoop`。字体改为本地 OFL woff2。打印改为隐藏 iframe。Windows 用 `packaging/build.ps1` 打 `dist/LearningLoop/LearningLoop.exe`，macOS 用 `packaging/build-macos.sh`；GitHub Actions `desktop-build` 可出两边工件。桌面依赖在 `requirements-desktop.txt`，不进入开发 `requirements.txt`。
