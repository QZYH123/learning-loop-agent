# 31 — 聊天流式输出（第一阶段：轮询增量）

**Type:** task

**Status:** resolved

**Source:** 竞争力判断：感知质量差距最大的一处——所有同类产品聊天都是流式，本产品 `stream: False` + 轮询终态。spec 原则「页面必须及时显示本地状态和模型任务状态」，且不设模型耗时 SLA，流式正是把等待变成可见进展。

## 范围

做：三适配器流式解析 + 会话消息内容随生成增量落库 + 前端轮询节奏适配。
不做（明确 Out of Scope，防臃肿）：SSE/WebSocket 新传输通道、逐 token 打字机动画、组卷/批改等非会话路径的流式、`validate` 流式。第二阶段是否上 SSE，等本票落地后按体感再议。

## 设计规定

### 模型客户端（`backend/app/model_client.py`）

- `ModelApiClient.chat` 增加可选参数 `on_delta: Callable[[str], None] | None`。提供时用流式请求，每收到一段文本增量就回调；返回值结构不变（完整 text + tool_calls + 元数据），调用方无感切换。
- 三格式流式解析：
  - `openai-chat-completions`：`stream: true`，逐行解析 SSE `data:`，文本取 `choices[0].delta.content`；`delta.tool_calls` 分片**缓冲拼装不外发**，流结束后并入归一化 `tool_calls`。
  - `openai-responses`：`stream: true`，SSE 事件流，文本取 `response.output_text.delta` 事件；`function_call` 相关事件缓冲拼装。
  - `ollama`：`stream: true`，逐行 JSON，文本取 `message.content` 分片；`message.tool_calls` 出现时缓冲。
- 用 `httpx.AsyncClient.stream(...)` 实现；取消（CancelledError）时关闭响应流即可，错误语义与现有 `ModelClientError` 一致。带 tools 的请求同样可流（文本推增量、工具调用缓冲），`tools_unsupported` 4xx 降级重试逻辑不变。
- 假模型：脚本支持 `deltas: [...]` 分片输出，供行为测试。`ObservedModelClient` 透传 `on_delta`，stage 仍在调用结束记一次，不逐 delta 记。

### 会话生成（`backend/app/learning.py`）

- `_generate_session_assistant` 里给最终答案轮传入 `on_delta`：累计文本，**距上次落库 ≥300ms 才**调 `_update_session_message` 写入 content（status 保持 `generating`），避免每 token 一次磁盘写。工具调用轮的中间文本不落库。
- 完成后的终态写入路径与现状完全一致（complete + citations + tool_events）。停止生成路径不变，已收到的部分内容保留在 stopped 消息里。

### 前端

- `pollSessionMessageOperation` / 生成中的会话刷新节奏收紧到 500ms（仅当有进行中的 chat-generation operation 时；空闲不轮询）。
- 渲染不改结构：generating 状态的消息已渲染 content，增量落库后自然逐段出现；保留现有「生成中」spinner 直到首段文本到达。sticky-bottom 跟随逻辑复用（`chatStick`）。

## 验收标准

1. 假模型分片脚本下，行为测试断言：消息在 complete 之前至少出现过一次非空且严格递增的 content（轮询中间态可见）。
2. 三适配器流式解析各有单测（httpx MockTransport 流式响应）：纯文本流、文本+工具调用混合流、流中断错误。
3. 停止生成后消息保留已生成片段，状态 stopped，重试可用。
4. 非流调用方（组卷、批改、验证、蓝图解析）行为与性能不变；全量 pytest 通过。

## Comments

- 2026-08-20：按顺序开工。`ModelApiClient.chat` 现全部 `stream: False`。会话循环在 `_run_session_assistant_loop`。假模型需能接受 `on_delta`。

## Answer

已落地。`ModelApiClient.chat(on_delta=)` 三格式流式解析；会话最终轮 ≥300ms 节流落库；工具轮增量会撤回。假模型支持 `deltas`。前端 chat 轮询与 generating 刷新 500ms。行为测试断言 complete 前 content 严格递增；停止保留片段。全量 pytest 144 passed。
