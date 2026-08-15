# AI 学习工具

单用户、本地优先的浏览器学习工具。当前实现覆盖：

- `01-app-shell-and-subject-spaces.md`：应用壳、科目空间和本地恢复
- `02-basic-chat-and-model-switching.md`：基础问答、模型服务配置/验证、停止生成和模型切换

## 技术栈

- 后端：FastAPI + uvicorn；模型调用使用 httpx
- 前端：当前选择原生 ES modules + HTML + CSS，由 FastAPI 静态托管（前端框架和构建方式不设限制）
- 持久化：本地 JSON 文件（默认 `data/workspace.json`），不依赖浏览器 localStorage
- 模型协议：OpenAI-compatible `/chat/completions` 文本接口
- 测试：pytest + FastAPI TestClient + 可控假模型，不依赖真实网络

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 4173
```

浏览器打开 <http://127.0.0.1:4173>。先创建科目空间，再添加
OpenAI-compatible 模型服务（服务商、模型、Base URL、可选 API Key），验证后即可
发送问题。应用状态和完整会话记录保存在服务端本地数据文件中，重启后自动恢复。

可通过环境变量 `LEARNING_LOOP_DATA_DIR` 修改数据目录。

## 测试

```bash
pytest -q
```

## 结构

```
backend/app/main.py          FastAPI 路由、应用壳和 API 响应
backend/app/domain.py        纯领域规则：科目、模型服务、会话状态
backend/app/store.py          工作区文件持久化
backend/app/model_client.py   OpenAI-compatible 模型客户端
backend/app/generation.py     异步生成任务和停止编排
backend/tests/                pytest 领域、API、模型客户端测试
frontend/                     浏览器前端（静态托管）
```

领域入口是 `apply_action(workspace, action)`：

```
用户操作 + 当前科目空间状态 -> 下一步状态 + 用户可见结果 + 待执行请求
```

- 模型服务是工作区级配置，可被多个科目复用。
- 每个科目的 `data.chat` 独立保存完整消息；AI 消息保存发送时的服务商/模型快照，
  之后修改或删除模型配置不会改写历史消息。
- 当前没有用户资料，所有回答都标注为通用知识模式。
