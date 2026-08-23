# boss-dungeon 浏览器证据

精选证据来自同一只读 Playwright Chromium 会话。测试目标为当前 worktree 内的静态隔离原型；没有安装浏览器、调用 API 或执行生产变更。

| 视口 | 起点 | 终点 |
| --- | --- | --- |
| 390 × 844 | `390-entry.png` | `390-receipt.png` |
| 768 × 900 | `768-entry.png` | `768-receipt.png` |
| 1280 × 900 | `1280-entry.png` | `1280-receipt.png` |

语义快照分别保留 390 宽度下的安全边界校验错误、团队状态重进和决策回执。完整机器结果见上级目录的 `builder-machine-evidence.json`。

这些文件只证明机器可复现行为，不能代替真人验收。
