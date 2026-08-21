# 34 — 桌宠「小墨」

**Type:** task

**Status:** resolved

**Source:** 用户需求：给学习工具加一只桌宠，核心是「记录的感觉」+ 简单互动，可爱、有设计感、有质感，不臃肿。

## 概念

一滴住在书桌上的活墨水。学习行为会「滴墨」喂养它：答题、对话、交卷、发布试卷、资料解析完成都产生墨水；它从蛋孵化，随累计墨水成长换形态。名片弹层展示连续学习天数、近 7 天足迹、今日记录和徽章——宠物即学习记录的化身。

设计取舍（防臃肿）：

- **全部墨水与统计从既有科目数据只读推导**，不新建事件管线、不在各服务里埋点。
- 宠物是**工作区级**（跨科目一只），持久化只存极少量自身状态。
- 台词用本地短语表，不调模型。
- 不做：喂食道具、离线挂机收益、每科目一只、宠物商店。

## 分工

- 后端（本票，implementer）：契约、持久化、推导服务、路由、测试。
- 前端（主会话负责，不在本票范围）：SVG 形象、动效、互动、名片弹层、app 接线。

## 后端设计规定

### 持久化

workspace 根级新增 `pet` 键（与 `models`、`subjects` 平级），经 `WorkspaceService.update_workspace` 读写：

```json
{
  "name": "小墨",
  "adopted_at": 1755700000000,
  "position_x": 78,
  "position_y": 100,
  "hidden": false,
  "pats_by_date": {"2026-08-21": 3}
}
```

- `position_x` / `position_y` 都是 0–100 的视口百分比（锚点是小墨脚底），可自由摆放；`position_y` 默认 100（贴底）。

- `normalize_workspace` 必须容忍缺失该键（旧数据文件打开时补默认值，`adopted_at` 为 null）。
- `adopted_at` 在第一次 `GET /api/pet` 时写入当前时间（领养 = 第一次见面）。
- `pats_by_date` 只保留最近 30 天，写入时清理。

### 契约（先改 `docs/api/schemas.yaml` / `openapi.yaml`，实现向契约收敛）

- `GET /api/pet`，operationId `getPet` → `Pet`
- `PATCH /api/pet`，operationId `updatePet`，body `{name?, position_x?, position_y?, hidden?}` → `Pet`
  - `name` trim 后 1–12 字符，超限 422；`position_x` / `position_y` 0–100 数值夹取；`hidden` 布尔。
- `POST /api/pet/pat`，operationId `patPet`，无 body → `Pet`
  - `pats_by_date[今日] += 1`；今日前 5 次每次 +1 墨水，之后只计数不给墨。

`Pet` 响应（键封闭）：

```json
{
  "name": "小墨",
  "adopted_at": 1755700000000,
  "position_x": 78,
  "position_y": 100,
  "hidden": false,
  "stage": 2,
  "ink_total": 128,
  "ink_today": 23,
  "ink_to_next": 272,
  "streak_days": 5,
  "pats_today": 3,
  "today": {"chat_messages": 6, "correct_answers": 4, "feedback_received": 5, "attempts_completed": 1, "exams_published": 0, "sources_ready": 0},
  "recent_days": [{"date": "2026-08-15", "ink": 12}, "…共 7 项，含今天，升序"],
  "badges": [{"id": "exam_1", "earned": true}, {"id": "attempt_1", "earned": true}, {"id": "streak_7", "earned": false}, {"id": "ink_100", "earned": true}]
}
```

### 墨水推导（新模块 `backend/app/pet.py`，纯读投影）

扫描全部科目的 `data`，按事件时间戳归日（服务器本地时区，`time.localtime`）。

**规则：一件学习的事 = 一滴墨，无权重、无日上限。** 计入的学习事件：

| 事件 | 取数 |
| --- | --- |
| 会话消息 | `sessions[].messages` 中 `role=="user"` 的 `created_at` |
| 收到反馈 | `attempts[].feedback[]` 每条（不分对错，答错也是学习） |
| 完成作答 | attempt 的完成时间戳（`completed_at`） |
| 发布试卷 | `exams[].created_at` |
| 资料就绪 | `source_versions[]` 中 `status=="ready"` 的时间戳（`processed_at` 回退 `created_at`） |

摸摸也给墨：+1/次，**日上限 5**（`pet.pats_by_date` 每日取 `min(count, 5)`，历史日期同规则）。这是唯一有日上限的来源。

- `ink_total` = 全部日期合计；`ink_today` = 今日合计；`recent_days` = 最近 7 天（含今天）每日合计。
- **阶段**：`ink_total == 0` → 0（蛋）；`>= 1` → 1；`>= 100` → 2；`>= 300` → 3。`ink_to_next` = 距下一阈值，满级为 null。
- **streak_days**：按「有任意墨水事件的日期」算连续天数——今日有事件则从今日往前连；今日没有则从昨日往前连；昨日也没有则 0。
- **badges**（纯推导，无存储）：`exam_1` 发布过 ≥1 份试卷；`attempt_1` 完成过 ≥1 次作答；`streak_7` **历史最长**连续天数 ≥7；`ink_100` 累计 ≥100。
- 性能：本地 JSON 全量扫描即可，不做缓存；前端调用频率低（启动 + 事件后 + 开名片）。

### 路由与组装

- 新路由文件或并入 `core_api.py`（选一处，与现有路由风格一致，带 `response_model` 与错误模型）。
- `main.py` 组装 `PetService(workspace_service, now=...)` 并注册路由。

### 测试要求（应用级 + 单元，风格随现有测试）

1. 空工作区首次 GET：stage 0、ink 0、adopted_at 被写入、name 默认「小墨」。
2. 造数据验证每类事件的权重、消息 20/日上限、摸摸 5/日墨水上限（第 6 次 pat 计数加但墨水不加）。
3. streak：连续三天有事件 → 3；今日无事件但昨日有 → 不断；隔一天 → 归零。
4. 阶段阈值边界（0/1/120/400）与 `ink_to_next`。
5. badges 四枚的正反例（streak_7 用历史最长而非当前）。
6. PATCH 校验：改名 trim 与长度 422、position 夹取、hidden；旧 workspace.json（无 pet 键）加载不报错。
7. 全量 pytest 通过，契约测试通过。

## 前端设计概要（主会话实现，本票不做）

蛋/墨滴/墨团/大墨团四形态 SVG，纸面主题墨色、黑板主题粉笔色（经 `--bubble-user` 自动）；摸摸 squish 反应与短语气泡；底边拖拽（PATCH position_x）；答对/交卷/发布的即时反应；4 分钟无操作打盹；名片弹层（改名、墨水进度、连续天数、7 天足迹点、今日记录、徽章、藏起来）。

## Comments

- 2026-08-21（二轮补充）：摸摸恢复给墨 +1/次、日上限 5（用户定夺），是唯一有上限的来源。
- 2026-08-21（二轮验收）：三处反馈全部落地并联调通过（全量 pytest 177）。冒烟断言：首次摸摸给墨并孵化、二维拖拽落库（x=50/y=29）、靠上时名片翻到脚下、藏起来吸附最近边框（左，x=0）、点小墨角恢复（x=7）。修复两个真实 bug：收纳角原先未绑点击事件（导致「藏起来回不来」）；is-low 名片向上生长盖住小墨。
- 2026-08-21（二轮，用户反馈）：墨水规则简化为「一件学习的事 = 一滴墨」，取消学习事件的权重与日上限，阈值改 1/100/300；新增 `position_y` 支持自由摆放；「藏起来」改为吸附到最近的不遮挡操作的边框（左/右/下），点边上的小墨角恢复。本文已按新规则改写。
- 2026-08-21：已实现并验收。后端（implementer）：`pet.py` / `pet_api.py`，完成时间戳用 `attempts[].completed_at`，资料就绪用 `processed_at` 回退 `created_at`；PATCH/pat 也会补写 `adopted_at` 以保证契约非空。前端（主会话）：`frontend/js/pet.js` + styles.css「桌宠」段 + app.js 五处事件钩子。默认位置定为 78%（居中会压双栏中缝）。全量 pytest 176 通过；真实服务冒烟：空工作区出蛋、首次摸摸孵化并正确说「你好呀，我是小墨」、名片与 API 计数一致。视觉记录见 `docs/design-language.md`「桌宠」一节。
