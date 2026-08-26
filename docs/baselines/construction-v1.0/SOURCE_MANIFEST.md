# 来源清单与裁决顺序

> 目的：让 Mini 知道什么是产品事实、什么只能作为技术资产、发生冲突时听谁的。

## 1. 来源优先级

从高到低：

1. 产品 Owner 在 2026-08-23 至 2026-08-27 的明确裁决；
2. 探索营 V1.0 真实业务方案；
3. 《Muchen Quest｜沐晨新手村》V1.0 已验证闭环及任务卡库；
4. V0.7 中与 Owner 裁决一致的治理升级；
5. AI 学院主管执行计划 V0.2；
6. 本施工总包；
7. Mac mini `Muchen Journey2.0` 的技术运行资产；
8. 历史页面、候选原型、旧数据和未批准的产品设想。

低优先级来源不得覆盖高优先级规则。代码已经存在、机器测试已经通过、页面更漂亮，都不构成产品批准。

## 2. 主来源

| Source ID | 来源 | 用途 | 继承结论 |
| --- | --- | --- | --- |
| `SRC-OWNER-01` | 产品 Owner 九项产品裁决及后续历史数据/发布裁决 | 最高产品决策 | 全量继承 |
| `SRC-OWNER-02` | 产品 Owner 2026-08-27 `PRODUCTION_CANARY_UAT` 裁决 | UAT使用生产基础设施上的8人白名单Canary；候选Gate不降低 | 全量继承；Canary部署授权与Release GO严格分离 |
| `SRC-EXP-01` | 探索营 V1.0，飞书 `Wuz5dtk8GoXpdvxrH7BcQlaVnZe` | 四宝藏真实业务结构 | 全量继承；个人成长基线改为结果包 |
| `SRC-EXP-02` | 《MUCHEN 新人启航探索营 Day1 方案》 | Day0、三项实操、评分素材、AI助教边界 | 继承实操与运营骨架；原准入措辞受 Owner 裁决限制 |
| `SRC-NV-01` | 《Muchen Quest｜沐晨新手村》V1.0 | 已验证任务/NPC/运营/积分闭环 | 继承行为，不照搬旧表和高影响人才结论 |
| `SRC-NV-02` | 《新手村任务卡库表 & 积分兑换表内容 V1.0》 | 任务字段、首批任务与积分内容 | 作为内容候选，须由屠元琦绑定版本 |
| `SRC-GOV-01` | 《Muchen Journey 产品设计融合文档 V0.7》 | 证据、权限、AI、人审、申诉、审计、插件治理 | 只继承已批准治理；不继承五宝藏和与真实任务裁决冲突的限制 |
| `SRC-AIA-01` | Wiki `GzknwrxybiOAOGkRrKKcjZyqnPb` →《AI学院主管_2026下半年执行计划_V0.2》 | AI学院一级空间、学习/作业/资产闭环和运营节奏 | 继承；高潜识别只保留人工观察，不自动下结论 |
| `SRC-TECH-01` | Mac mini `/Users/liumowen/Documents/Muchen Journey2.0` | Web/API/Worker/PostgreSQL、身份、任务、审核、发布恢复 | 作为唯一技术运行基线；不作为产品 SSOT |
| `SRC-AUDIT-01` | `outputs/muchen-journey-baseline/*` | 产品继承审计、冲突裁决、代码映射、Build Contract | 作为本包的审计前置 |
| `SRC-WIKI-01` | `wiki/concepts/新人训练失败模式.md` | 训练必须贴近真实规则、统一门槛和评估口径 | 作为负向设计约束 |
| `SRC-WIKI-02` | `wiki/concepts/口径一致性验证.md` | 发布后验证理解一致而非只发布文字 | 作为内容变更/UAT约束 |
| `SRC-WIKI-03` | `wiki/concepts/沐晨-journey.md` | Journey 为跨学习、任务、认证和回流的成长主线 | 仅作背景；具体顺序以本包为准 |

## 3. 已裁决冲突

| 冲突 | 裁决 |
| --- | --- |
| 四宝藏 vs 五宝藏 | 采用 V1.0 四宝藏；个人成长基线是结果包 |
| 旧新手村表结构 vs Journey2.0 数据模型 | 继承任务闭环，不继承旧表；新表按共享领域模型重构 |
| V0.7 只允许模拟 vs Owner 允许真实任务 | 允许受控真实项目任务；Journey 不执行生产作业 |
| Day1 原准入分层 vs Owner 高影响边界 | 只决定下一训练阶段，不做录用、淘汰或项目准入终判 |
| 积分分流/高潜排序 vs Owner 裁决 | 积分只作激励和参考，不能单独产生人才结论 |
| 23 表完整历史迁移 Gate vs 9/1发布 | 旧数据仅参考；历史完整性不阻塞发布；正式迁移为 0 |
| 六模块首发 vs 9/1现实期限 | 9/1首发四模块；完整竞技场和 Career Map 延期 |
| staging UAT vs production UAT | 真人UAT改在生产基础设施上的8人白名单Canary执行；不改变候选、安全、恢复、真人或独立复核Gate |
| README 技术 Greenfield vs 产品继承 | 技术 Greenfield 可以保留；“产品从零设计”必须废止 |

## 4. 源文件定位

本地镜像主要位于：

- `tmp/llm-wiki-migration/Agentic COO/raw/sources/feishu/personal-docs/docx/Muchen Quest｜沐晨新手村-HzbUddQu0nQe/index.md`
- `tmp/llm-wiki-migration/Agentic COO/raw/sources/feishu/personal-docs/docx/MUCHEN 新人启航探索营 Day1 方案-Q399dK1SVnXd/index.md`
- `tmp/llm-wiki-migration/Agentic COO/raw/sources/feishu/personal-docs/docx/MUCHEN新人启航探索营优化建议-HVETdxcUBnog/index.md`
- `tmp/llm-wiki-migration/Agentic COO/raw/sources/feishu/personal-docs/docx/Muchen_Journey_产品设计融合文档_V0.7-U31fdQTNpn9d/index.md`
- `tmp/llm-wiki-migration/Agentic COO/raw/sources/feishu/personal-docs/docx/AI学院主管_2026下半年执行计划_V0.2-Yp7BdnjpAnHd/index.md`
- `outputs/muchen-journey-baseline/`

AI学院 Wiki 节点：`https://zx6w57w0j34.feishu.cn/wiki/GzknwrxybiOAOGkRrKKcjZyqnPb`。2026-08-26 只读核验显示该节点解析到《AI学院主管_2026下半年执行计划_V0.2》，与上述本地镜像为同名正式方案。

## 5. 不得伪造的空位

以下内容必须由对应 Owner 提供并形成版本/hash，Mini 不得自行补写：正式材料正文、真实项目任务授权、Rubric 具体阈值、执行 Reviewer 名单、替补 Reviewer、SLA 例外、UAT 真人记录、候选发布签署和任何高影响人才结论。
