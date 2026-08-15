# HTTP API 契约

本项目采用契约先行。Ticket 01–15 的后端开发输入是：

- [`api/openapi.yaml`](api/openapi.yaml)：路径、方法、状态码、请求和响应。
- [`api/schemas.yaml`](api/schemas.yaml)：资源结构、枚举、状态机和错误码。

两者共同构成 OpenAPI 3.1 主契约。FastAPI 自动生成的 `/openapi.json` 是实现产物，后续必须通过一致性测试证明它符合主契约，不能替代主契约。

## 当前状态

契约版本为 `0.1.0`，状态为 `target`。Ticket 03 的后端路径、operationId、成功状态码和响应模型已与目标契约对齐，覆盖 Markdown/TXT 资料上传、异步解析、内容缓存、版本和删除；资料库前端尚未实现。Ticket 01 和 02 的现有接口在响应结构、状态码、异步任务和敏感字段方面仍未完全符合目标契约。

主要迁移差异：

- 成功响应直接返回资源，不再把完整工作区塞进每个修改响应。
- 所有失败统一返回 `ErrorResponse`，不再混用 FastAPI 的 `detail` 和领域错误信封。
- 模型验证、资料解析、AI 生成、批改、修改、导出和评估统一返回 `202 OperationAccepted`。
- `api_key` 只写；读取模型服务只返回 `has_api_key`。
- `GET /api/workspace` 只返回导航摘要，不内嵌不断增长的业务数据。
- 兼容停止接口 `/api/generations/{generation_id}/stop` 标记为 deprecated，新实现以 `/api/operations/{operation_id}/cancel` 为准。

## 通用规则

- 服务是单用户、本地优先应用，当前无认证；OpenAPI 根级 `security` 为空。
- 除上传和下载外均使用 `application/json`。
- 字段使用 `snake_case`，枚举值使用小写 kebab-case。
- ID 是不透明字符串；客户端不得解析或自行构造。
- 时间字段是 Unix 毫秒时间戳。
- 创建资源使用 `201`，异步任务使用 `202`，成功删除使用 `204`。
- 字段校验失败使用 `422`，资源不存在使用 `404`，状态或版本冲突使用 `409`。
- 错误码是 `schemas.yaml` 中 `ErrorCode` 的封闭枚举；新增错误码必须先改契约。

错误响应固定为：

```json
{
  "ok": false,
  "error": {
    "code": "EXAM_VERSION_CONFLICT",
    "message": "试卷已被更新，请基于最新版本重试",
    "retryable": true,
    "details": {
      "current_version_id": "version-id"
    }
  }
}
```

`details` 只能包含安全的结构化诊断信息，禁止放入 API Key、完整用户资料、完整提示词或无关敏感内容。

## 异步任务

以下工作不得伪装成同步成功：模型验证、资料解析、问答生成、章节速成、蓝图解析、增量组卷、单题重试、主观题反馈、统一批改、AI 修改、导出和固定评估。

创建任务后返回 `OperationAccepted`。客户端通过 `GET /api/operations/{operation_id}` 轮询：

```text
queued -> running -> succeeded
                  -> failed
       -> canceling -> canceled
```

只有 `cancelable: true` 的非终态任务可以取消。终态任务保留 `result` 或 `error`，不能依赖临时内存 ID 才能读取结果。

## 关键边界

### 资料与引用

上传相同内容可以复用解析缓存，但内容变化必须创建新资料版本。来源引用固定到 `source_version_id + anchor_id`；资料从资料库删除或变为不可用后，历史来源引用仍保留身份和位置，不会悄悄指向新版本。

资料严格模式未命中时，AI 消息使用 `grounding_result: not-covered`，不得隐式补充模型知识。图片输入必须检查所选模型的 `capabilities.vision`，不支持时返回 `IMAGE_INPUT_UNSUPPORTED`。

### 学习会话

每个科目空间当前有一个学习会话资源，HTTP 路径继续使用 `/chat` 兼容现有前端。`learning_mode` 为 `chat`、`socratic` 或 `crash-course`；切换学习方式、资料范围和依据模式不会删除会话记录，也不会隐式切换模型。

苏格拉底式学习通过消息 `intent` 推进：配置目标后以 `start` 开始，再使用尝试、请求提示、直接解释、复述和自测等动作。`SocraticState` 明确当前阶段、提示层级和答案是否已展示，客户端不得仅凭文案猜测流程状态。

选区问答使用 `SelectionContext` 固定到文档版本、题目和内容块。创建消息只更新会话和异步任务，不具备修改试卷的副作用。

### 试卷

组卷蓝图必须经过 `draft -> confirmed` 后才能生成试卷草稿。增量组卷先创建 `DraftQuestion` 槽位，再让各题独立进入 `queued`、`generating`、`complete`、`failed` 或 `needs-review`。

题目使用带判别字段的固定结构，覆盖选择、填空、判断、简答、辨析和大题。每道题都必须包含答案、解析、考点和题目依据；依据或结构不完整时只能标记为 `needs-review`。

人工修改和 AI 修改都会创建试卷版本。AI 先产生试卷修改提案，只有明确调用 `apply` 才能修改试卷；应用时必须校验 `base_version_id`，防止覆盖更新。

### 作答与答案可见性

`Attempt.paper` 是答题页面唯一允许使用的题目视图，不包含答案、解析或隐藏的题目依据。考试模式提交前 `Attempt.feedback` 必须为空，`GET /attempts/{id}/review` 必须返回 `409 ANSWER_NOT_AVAILABLE`。

练习模式只返回用户已请求或已产生的单题反馈。主观题反馈记录用户答案快照、得分点、遗漏点、推理问题、改进建议、题目依据和实际模型；关闭建议分数时 `suggested_score` 为 `null`。

### 渲染与导出

网页、打印和 PDF 使用同一个 `ExamRenderDocument`。题目版的 `RenderQuestion.solution` 必须为 `null`；答案版必须由 `edition=solutions` 显式请求。导出是固定试卷版本的副本，不与应用内试卷双向同步。

### 观测与评估

编排运行分别记录 `outer_elapsed_ms` 和 `model_wait_ms`，并只保存脱敏阶段事件。固定评估结果把 `orchestration_metrics` 与 `model_observations` 分成两个对象，禁止把答案正确率或引用准确率当成编排层性能指标。

## Ticket 追踪

每个 OpenAPI operation 都带 `x-tickets`。契约测试要求 01–15 全部被覆盖。

| Ticket | 主契约区域 |
| --- | --- |
| 01 | 工作区、科目空间 |
| 02 | 模型服务、基础会话、异步任务 |
| 03 | 用户资料、资料版本、解析缓存 |
| 04 | 资料范围、依据模式、来源引用 |
| 05 | 富文档、图片资源、模型视觉能力 |
| 06 | 苏格拉底式状态与消息 intent |
| 07 | 章节速成和学习产物 |
| 08 | 组卷蓝图解析、编辑和确认 |
| 09 | 增量组卷、固定题型、单题重试和发布 |
| 10 | 试卷作答、模式、暂停恢复和客观题反馈 |
| 11 | 主观题反馈和可选建议分数 |
| 12 | 固定文档版本的文字/图片选区问答 |
| 13 | 修改提案、差异预览、版本、撤销和恢复 |
| 14 | 统一渲染文档和导出副本 |
| 15 | 编排运行和固定评估 |

## 实现顺序

后端按 Ticket 依赖顺序实现。每完成一个 Ticket：

1. 为对应 operation 建立 FastAPI 请求/响应模型，禁止直接返回未声明的字典。
2. 增加契约示例和领域行为测试。
3. 比较 FastAPI `/openapi.json` 与静态主契约中该 Ticket 的路径、状态码和 Schema。
4. 只有一致性测试通过后才勾选 Ticket 验收项。
