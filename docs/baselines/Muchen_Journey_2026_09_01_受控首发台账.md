# Muchen Journey｜2026-09-01 受控首发唯一台账

> 首次记录：2026-08-26
> 每日更新时间：22:00 Asia/Shanghai；只更新本文件
> 发布范围：探索营、新手村、AI学院、交付线公会；最多 25 人

## STATUS

`CONTROLLED_RELEASE_SCOPE_FROZEN / ISOLATED_SOURCE_MACHINE_PASS / CANDIDATE_COMMIT_NOT_CREATED / NO_RELEASE`

## CURRENT_CANDIDATE_SHA

- 当前开发 HEAD：`b7597edfdf7d5bd2fdbda99cd1141590ab3d5859`
- Release Candidate：`NOT_CREATED`
- 工作树：`DIRTY / ATTRIBUTION_V0.11_COMPLETE / UNKNOWN_ZERO / PHYSICAL_SOURCE_ISOLATION_COMPLETE`
- 当前 HEAD 不是候选 SHA，不能绑定 UAT 或独立签署。
- 最新不可覆盖归因快照：`worktree-attribution-20260826-v0.11.json`，400 个状态条目＝130 `RELEASE_REQUIRED` / 270 `POST_RELEASE_DEFERRED` / 0 `UNKNOWN`；SHA-256 `4dbb12d710a1967916e4c92356f5557fa4b20709277f738012c4743dcc330051`。生成后新增证据不回写旧快照。
- 已在仓库外生成并二次校验只读隔离源码树 `/Users/liumowen/.codex/candidates/muchen-journey/2026-09-01-controlled-release-source-v0.4`：569 个文件、71 个 dirty overlay、329 个排除状态条目，源码树 SHA-256 `e22efb6570f081146cdfd808431ef8f1d863da75202ff896cb3de83df69ca92a`。该树不是 commit，`release_authorized=false`。
- 8 月 8 日正式内容工作簿经只读检查，15 项批准数为 0，任务题面、Rubric、Reviewer、批准人均未完成，并含已被后续裁决禁止的 `ADMIT/NOT_ADMIT` 语义；其目录整体归入 `POST_RELEASE_DEFERRED / FROZEN_REFERENCE`，未据此生成新内容。

## FOUR_MODULE_VERTICAL_SLICE_STATUS

| 模块 | 当前状态 | actual 证据 |
|---|---|---|
| 探索营 | `ENTRY_AND_SHARED_ENGINE_MACHINE_PASS / OWNER_CONTENT_PENDING / HUMAN_NOT_RUN` | 入口、Enrollment 作用域与既有任务闭环机器通过；本首发真实内容纵切未证明 |
| 新手村 | `ENTRY_AND_SHARED_ENGINE_MACHINE_PASS / OWNER_CONTENT_PENDING / HUMAN_NOT_RUN` | 入口复用 Enrollment/Assignment/Result；真实首发任务未冻结 |
| AI学院 | `ENTRY_AND_SHARED_ENGINE_MACHINE_PASS / OWNER_CONTENT_PENDING / HUMAN_NOT_RUN` | 入口复用 Enrollment/Assignment/Result；真实学习单元/任务/Reviewer 未冻结 |
| 交付线公会 | `ENTRY_AND_SHARED_ENGINE_MACHINE_PASS / OWNER_CONTENT_PENDING / HUMAN_NOT_RUN` | 入口复用 Enrollment/Assignment/Result；真实公会规则/演练/Reviewer 未冻结 |

既有 map workstream 已逐项复核：探索营合同为 `RUNTIME_NOT_IMPLEMENTED`；新手村、AI学院、交付线公会均为冻结的 `ISOLATED_DRAFT_BUILD / READY_FOR_HUMAN`，真人 Gate `NOT_RUN`、集成/发布未授权。其中 AI 学院明确使用 `READ_ONLY_SYNTHETIC_FIXTURE / NO_SHARED_WRITE / NO_IDENTITY_OR_SESSION`。四份合同 SHA-256 分别为 `8552a57f…e69cd5`、`d02ed885…eb5d18`、`11a59b5f…943c95`、`807ba48f…44d6e`；只能作为体验参考，不能作为正式内容包或 runtime 通过。

## MACHINE_TEST_STATUS

受控首发当前机器结果：

- 仓库外隔离树 Web：合同测试 43/43、TypeScript、ESLint、Production Build：`PASS`；生产依赖与全依赖 `npm audit --audit-level=high` 均为 0 vulnerabilities；本地镜像 digest `sha256:42ccd13ae31cd576d1e866a48479c018e768ed4ffc0ebd4b03575a3ed73a8dd1`，未推送；
- 仓库外隔离树 API/合同套件：在新建具名合成库 `journey_controlled_stage_v06` 完成 `base → 0019` 与 seed，414 passed、5 skipped；本地镜像 digest `sha256:a4a561aea893023f732fe65825cdc576a1e11d5737e8d3212e34f1c1ac1a4537`，未推送；
- 隔离/归因宿主自测：8/8 `PASS`；Legacy 历史只读测试在只读挂载既有证据后：19 passed、12 subtests passed；
- 新增 Enrollment 选择、Result/Timeline 同作用域定向测试：17/17 `PASS`；
- 隔离镜像运行时 OpenAPI 与静态合同：66 条路径等值 `PASS`；migration head 为 `0019_wp30_invitation_control`，未创建新 migration；
- 当前分支迁移链在全新合成临时库完成 `base → 0019 → 0009 → 0019`，业务指纹一致，报告 SHA-256 `d86a1c9b0e002c479c6bbfc3551091d29cf2db2bcca94ea281b2452b458f2034`；
- 首日监控告警决策合成演练：`PASS`，覆盖 worker stale、outbox backlog、dead notification、API/Worker release 漂移和 migration 漂移；报告 SHA-256 `ad22734751dc270e756c975a3283dd0ae110c95802d3f4e6a01b8c81480b23fe`。真实外部告警投递仍为 `NOT_RUN`；
- 内置浏览器确认公开首页/私邀页仅显示四模块，console error/warn 0；无 Session 的 `/app` fail closed。

上述全部是 synthetic/machine 证据。第一次隔离 API 收集因遗漏 `appeal_continuity.py` 失败，修正归属后另一次运行因测试环境错误覆盖身份密钥产生 2 个配置测试失败；两次均未覆盖。Web 随后发现显式固定的 `nanoid 3.3.17` 生产依赖风险，只将该 override 提升至 `3.3.18` 并生成 V0.4 隔离树，最终 API、Web 与依赖审计均通过。独立评估仍为 `BLOCKED_CONTRACT`，不代表四模块真实内容闭环、真人 UAT 或 Release PASS。

## HUMAN_UAT_STATUS

`NOT_RUN`。四模块目标均为每模块至少 2 名真实用户；合成、AI 和开发者自证不得代替。

## P0_P1_LIST

- P0：无候选 SHA，因此无法开始候选级 UAT、独立 QA 或 Release Review。
- P0：四模块首批真实任务/内容/Rubric/Reviewer 尚未由对应 Owner 冻结。
- P1：工作树 V0.11 归因及仓库外物理源码隔离已完成（130 required / 270 deferred / 0 unknown），但候选 commit 尚未创建。
- P1：共享任务纵切尚未完成本候选级端到端复核。
- P1：现有数据库约束只允许每名学习者一个 `ACTIVE` Enrollment；四模块必须按受控阶段切换，不得假设并行激活。
- P1：现有离线导入器仅接受 `SYNTHETIC_VNEXT_FIXTURE`、仅限 local/test，且不能表达冻结 JourneyStage 谱系；不得作为 25 人正式名单导入。名单身份键、内容版本和导入执行合同待 Owner/Pro 决定。

## OWNER_SIGNOFF_STATUS

- Product/Tech/Data/Security/Release/Business Decider 刘默文：角色已接受；本次范围已确认；最终 GO `NOT_RUN`。
- 郑田源、屠元琦、段超群：模块内容与流程确认 `NOT_RUN`。

## INDEPENDENT_QA_STATUS

冯宇汀：角色任命与接受 `ACCEPTED_BY_OWNER_ATTESTATION`；候选级独立 QA `NOT_RUN`。

## RELEASE_REVIEW_STATUS

冯宇汀：独立 Release Reviewer 角色已接受；候选级 Release Review `NOT_RUN`。

## STAGING_STATUS

`NOT_RUN`。

## BACKUP_RESTORE_STATUS

- 当前工作树受控本地备份：`PASS`，路径 `/Users/liumowen/.codex/backups/muchen-journey/20260901-controlled-release-prep-20260825T172048Z`。
- development/test 数据库备份与实际恢复：`LOCAL_SYNTHETIC_PASS`。显式合成源库 `journey_controlled_release_recovery_20260826`，migration `0019_wp30_invitation_control`，正式业务数据 0；加密备份 manifest SHA-256 `68965395bf335c0dbd2f5e24ba7531a749330629953a6956688b80b5ac37b7b4`，密文 SHA-256 `caee777c44ae19f777a40e983b9ea684423d5b925cbd7b4ef64e37fca4ce72d9`。
- 隔离恢复报告：`restore=PASS / reupgrade=PASS / accepted_business_facts_rolled_back=false`，SHA-256 `aef6c84b06ab63e0ddd6de32a5d47d4ba974ebae471c35272be6b2620164bcb7`。
- 持久 development 卷只读发现 migration `0021_p0_identity_principal`，当前仓库无该 revision；自动演练已 fail closed，未清空、覆盖或降级该卷。
- off-host/候选级恢复：`NOT_RUN`。

## ROLLBACK_STATUS

`LOCAL_SYNTHETIC_PASS / NOT_RUN_FOR_CURRENT_CANDIDATE`。隔离库完成 `0019 → 0013 → 0019` 且业务事实不变；最终候选、staging 和 production 回滚仍未运行。

## PRODUCTION_PREFLIGHT_STATUS

`NOT_RUN`。

## RELEASE_DECISION_STATUS

`NO_GO / RELEASE_AUTHORIZED=false`。

## RISKS

- 现有大量 G3—G35 候选和 Legacy 产物可能污染首发候选；必须按清单隔离，不能删除。
- 工作树归属 UNKNOWN 已清零，270 个 frozen/deferred 状态条目已被隔离工具排除并由源码树 manifest 校验；后续任何源码变化都必须生成新树，不能原地补丁。
- 持久 development 卷 migration 高于当前分支；其来源未归因前不得重建、降级或作为候选数据库。
- 旧机器 PASS 可能绑定不同代码/配置，必须针对最终候选重跑。
- 模块 Owner 真实内容、Reviewer 排班和真人 UAT 是当前外部关键路径。
- 屠元琦不能同时成为同一场景的运营者、唯一 Reviewer 和唯一 UAT 签署人。

## BLOCKERS

- 四模块 Owner 正式内容包和流程确认未到位；
- 最终候选 SHA 未创建；
- 真人 UAT、独立 QA、Staging、候选级备份/回滚和 Preflight 均未运行；仅本地合成恢复演练通过。
- 25 人正式名单导入合同未闭合；旧 synthetic importer 不得放宽或冒充正式导入。

## NEXT_24_HOUR_PRIORITY

1. 冻结四模块 Owner 的首批真实任务、Rubric、Reviewer 和结果包内容输入；
2. 由 Owner/Pro 确认四模块按单一 ACTIVE Enrollment 顺序切换，以及 25 人名单的身份键和受控导入合同；
3. 冻结隔离源码树对应的内容包后，申请创建专用候选 commit；不得把仓库外源码树当作 commit；
4. 获授权后生成绑定 commit SHA、配置、migration、Web/API 构建和内容包版本的 RC，并再次重跑候选级机器基线。

## NEXT_GATE

`PRO_2026_09_01_RELEASE_CANDIDATE_REVIEW`
