# Learner 保存与提交限流技术验收

## 范围

仅草稿 PUT 与提交 POST；组织＋Learner 独立 scope。草稿 20/10 秒、90/分钟；提交 5/10 秒、20/分钟。固定数据库时钟窗口，不宣称滚动窗口上限。认证、角色、CSRF 通过后计数，重复幂等请求和业务失败均消耗额度。等待结束后原成功幂等结果仍可重放。

复用 auth_rate_limits；无迁移，无历史事实改写。原子 upsert，计数封顶 threshold+1，只清理当前主体新增 scope 中超过 10 分钟的桶。每个 API 进程增加最多 2 条专用计数连接，避免业务连接池二次借连接死锁。计数独立提交；存储故障 503 fail closed。429 包含 Retry-After 与 details.retry_after_seconds。

## 已执行证据（本地隔离 PostgreSQL，非真人 UAT）

- 定向 API/数据库测试：8 passed。50 次合法草稿请求在 10 秒内，20 成功、30 返回 429；一条草稿 revision=20，20 条草稿幂等结果、零 Submission。另测独立进程、20 线程并发、用户/组织隔离、跨任务连接、两窗口边界、正常 1.2 秒节奏、桶清理和封顶。
- 提交：成功和重复幂等重放均计数；第六次限流；恢复后同键返回同版本，异键旧 revision 被拒绝。草稿限制不占用提交额度。CSRF 失败不触发计数；计数故障返回可重试 503 且无草稿/提交写入。
- 本机 Chrome/Playwright 合成账号交互：草稿限流提示、按钮禁用、继续编辑、倒计时后保存最新文本；提交倒计时、确认内容与幂等键保留、不自动提交、手动重试仅一个版本、无 pageerror。
- Web：136 个源合同测试、lint、typecheck、生产 build 通过。运行时 OpenAPI 与导出合同相等。
- 完整本地 pytest 首轮：993 passed、17 failed、15 skipped。失败为缺 GNU grep/bash/git、外部 Legacy 归档（仓库 api-test 原本排除）和专用数据库命名约定；不能记为完整门禁通过。按门禁补装工具时 Alpine TLS 下载失败，完整门禁以 GitHub CI 后续实测为准。

## 重跑入口

- `pytest -q tests/test_learner_write_limits.py`，必须隔离 PostgreSQL＋seed＋fixture identity。其他业务流程测试用共享递增时钟模拟真人操作节奏；本文件 marker 保留专门的固定窗口与真实并发检验，生产无绕过开关。
- `node scripts/learner_write_limits_browser.cjs`：配置 PLAYWRIGHT_MODULE、PLAYWRIGHT_CHROMIUM_EXECUTABLE，可选 RATE_TEST_API/WEB 和 RATE_TEST_SCREENSHOTS。仅允许 127.0.0.1；目标必须为隔离 API/Web，禁止代理生产端口。脚本创建合成身份，不使用真实 Cookie。

## 发布边界

本记录不代表已经上线。须 PR/主线门禁通过、独立 Canary 兼容性包校验、prepare、用户协调暂停窗口后 switch，并核对真实运行版本与健康。高频脚本不得在刘纯洁账号或生产上执行。真人 UAT 与技术验收分别登记。
