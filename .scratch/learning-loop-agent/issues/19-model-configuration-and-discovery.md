# 19 — 模型配置、API 格式和手动发现

**What to build:** 提供一个模型配置面板，支持添加、编辑、选择、手动测试和模型发现。服务商名称只用于识别配置，调用协议由用户明确选择的 API 格式决定。

**Blocked by:** 16 — API 契约和工作流状态基线；02 — 基础问答和模型切换

**Status:** ready-for-agent

## Contract

- [ ] 模型配置增加必填 `api_format`：`openai-chat-completions | openai-responses | ollama`
- [ ] `ModelService`、输入、更新和每条结果的 `ModelSnapshot` 都保存 `api_format`
- [ ] 临时模型发现请求使用 `api_format`，不再用 `provider` 猜请求路径
- [ ] 既有配置迁移时默认 `openai-chat-completions`，不得因名称包含 OpenAI 或 Ollama 自动改写
- [ ] OpenAI 两种格式通过 `/models` 发现模型；Ollama 通过 `/api/tags`
- [ ] 明确不同格式的规范化结果和错误码

## Backend

- [ ] `openai-chat-completions` 调用 `/chat/completions`，发送 `messages`，从 `choices[0].message.content` 读取文本
- [ ] `openai-responses` 调用 `/responses`，发送 `instructions` 和 `input`，从类型化 `output` 中的 `output_text` 内容读取文本
- [ ] Responses 默认使用 `store: false`，由本地会话记录重放上下文，不依赖远端保存状态
- [ ] Responses 多模态内容映射为对应 input items；结构化输出使用 `text.format`，不能复用 Chat Completions 的 `response_format`
- [ ] 如果后续启用流式输出，Responses 按 `response.output_text.delta`、`response.completed` 和 `error` 等类型化事件处理，不能复用 chunk delta 解析器
- [ ] `ollama` 原生格式使用 `/api/chat` 生成、`/api/tags` 发现；OpenAI 兼容模式应选择对应 OpenAI API 格式
- [ ] 填写必填字段后允许保存，不强制先测试；只有用户主动测试或发现时发起网络请求
- [ ] 发现失败时允许手动输入模型名，临时凭据不持久化、不进入日志
- [ ] 不实现后台轮询、实时健康监测或基于模型名猜 Vision 能力

## Frontend

- [ ] 顶部只保留一个“模型配置”入口
- [ ] 配置表单把“名称”和“API 格式”分开；API 格式使用单选或下拉，不使用自由文本
- [ ] 选项文案为 `Chat Completions`、`Responses`、`Ollama`，旁边提供简短 tooltip
- [ ] 切换 API 格式时给出对应 Base URL 示例，但不静默覆盖用户已输入地址
- [ ] 提供“测试连接”和“获取模型”两个明确动作；发现失败后保留手动模型输入
- [ ] 当前模型切换只影响后续 AI 操作，每条结果显示实际模型和 API 格式
- [ ] 未实现适配器的格式不得显示为可保存选项

## Verification

- [ ] 测试三种 API 格式的保存、编辑、读取、模型快照和既有数据迁移
- [ ] 使用假 HTTP transport 分别验证三个端点、请求体和响应解析
- [ ] 测试 Responses 输出包含 reasoning 等非 message item 时仍能提取最终文本
- [ ] 测试手动验证、模型发现、手动兜底、错误反馈和凭据脱敏
- [ ] 测试不同 API 格式不会因为 provider、model 或 Base URL 文本被自动切换

## Comments

- 当前后端生成客户端只实现 OpenAI-compatible Chat Completions；仅增加前端下拉选项不算完成。
- Responses 协议依据 OpenAI 官方迁移文档：<https://developers.openai.com/api/docs/guides/migrate-to-responses>。
