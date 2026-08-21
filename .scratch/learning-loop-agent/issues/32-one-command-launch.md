# 32 — 一键启动

**Type:** task

**Status:** resolved

**Source:** 竞争力判断：本地优先工具的使用门槛在启动。现状 README 要求四条命令（venv、install、uvicorn、手动开浏览器），对非技术学习者不友好。

## 范围

做：单命令启动入口 + README 简化。
不做：安装器/打包成桌面应用（pyinstaller、electron 之类）、开机自启、多实例管理。

## 设计规定

- 新增 `backend/app/__main__.py`，使 `python3 -m backend.app` 完成：
  1. 检查依赖可导入，缺失时输出一句中文提示（提示先运行 `pip install -r requirements.txt`），不打印堆栈；
  2. 端口默认 4173，被占用时依次尝试 4174–4179 并在终端打印实际地址；
  3. 启动 uvicorn（非 reload），就绪后用 `webbrowser.open` 打开应用地址（提供 `--no-browser` 参数跳过）；
  4. 尊重现有 `LEARNING_LOOP_DATA_DIR` 环境变量。
- 根目录加 `run.sh`（两行：激活 venv 若存在 + `python3 -m backend.app`），Windows 不管。
- README「运行」小节改为首选 `python3 -m backend.app`（保留 uvicorn 命令作为开发方式）。
- 不改 FastAPI 应用本身；`__main__.py` 只做进程编排。

## 验收标准

1. 全新克隆 + 装依赖后，`python3 -m backend.app` 一条命令可用（终端显示地址，浏览器自动打开）。
2. 4173 被占用时自动换端口且终端明确提示。
3. `--no-browser` 生效；测试环境不弹浏览器（pytest 不受影响）。
4. 全量 pytest 通过。

## Comments

- 2026-08-20：按顺序开工。现有入口是 `uvicorn backend.app.main:app --reload --port 4173`。

## Answer

已落地。`python3 -m backend.app` 查依赖、4173–4179 选端口、非 reload 启动、就绪后开浏览器；`--no-browser` 可跳过。`run.sh` 激活 venv 后转调同一入口。README 运行小节已改。全量 pytest 154 passed。
