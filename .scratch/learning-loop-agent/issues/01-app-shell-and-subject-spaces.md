# 01 — 应用壳和科目空间

**What to build:** 提供可在浏览器使用的本地应用壳。用户可以创建、重命名、切换和删除科目空间，并在重新打开应用后继续使用之前的科目。第一版只需要建立后续问答、资料库和试卷都能复用的最小工作区。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [x] 用户可以创建、重命名、切换和删除科目空间
- [x] 当前科目和科目列表在重新打开应用后仍然存在
- [x] 不同科目的本地状态相互隔离
- [x] 桌面浏览器中能看到左侧学习操作区和右侧内容区的稳定布局
- [x] 自动化测试覆盖科目生命周期和本地恢复行为

## Comments

- 实现（技术栈已调整为 FastAPI 后端 + 浏览器前端）：`backend/app/domain.py` 提供科目空间纯领域规则，`backend/app/main.py` 提供 API，`frontend/` 渲染桌面双栏应用壳。
- 运行：`uvicorn backend.app.main:app --port 4173` 后打开 http://127.0.0.1:4173；测试：`pytest -q`。
