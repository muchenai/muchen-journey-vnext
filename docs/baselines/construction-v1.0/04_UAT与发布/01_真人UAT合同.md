# UAT与发布 01｜真人 UAT 合同

> QA/UAT运营 Owner：屠元琦  
> 独立 QA：冯宇汀  
> 运行模式：`PRODUCTION_CANARY_UAT`  
> 规则：UAT必须由真实目标用户在固定候选SHA和最终生产基础设施执行；AI、合成脚本、开发者自证不能替代。

## 1. UAT 前置

- 干净候选 SHA/manifest 已固定；
- 四模块P0机器测试和负向合同通过；
- 候选环境禁用fixture身份；
- 内容包/Rubric/Reviewer绑定同一hash；
- 测试账户、名单、数据、安全边界和清理方案批准；
- 每模块至少2名目标用户，Reviewer和Operator真实在场；
- 缺陷记录、录像/截图/日志的隐私规则明确。
- 当前镜像安全扫描、同候选备份/恢复/回滚和具名真人告警回执通过；
- 8名具名参与者allowlist及其hash固定，非白名单失败关闭；
- `release_marker=PRODUCTION_CANARY_UAT`，页面显示受控内测，停邀请和回滚可执行；
- `CANARY_DEPLOYMENT_GO`绑定准确候选；该签署不是`RELEASE_GO`。

## 2. 生产 Canary 运行边界

- 使用最终生产域名、镜像、身份和数据库运行面，仅通过服务端allowlist/cohort scope开放给8人；
- 普通访客继续看到稳定公开页，非白名单不得进入四模块新路径；
- 允许写入8人UAT产生的Journey任务、提交、评审、结果和审计事实；
- 禁止外部生产作业、历史迁移、生产写凭证、高影响自动结论和白名单扩大；
- Canary事实必须绑定`canary_uat_id`、candidate SHA、content hash和participant ref；
- UAT通过后不换SHA；独立复核和`RELEASE_GO`通过后才把名单扩大至最多25人。

## 3. 通用场景

每模块都执行：

1. 受邀用户完成身份确认；
2. 在首页无需讲解找到下一行动；
3. 复述目标、交付物、边界、Reviewer和求助路径；
4. 开始并保存草稿；
5. 提交固定版本；
6. Reviewer领取并要求返工；
7. 学员修改并重新提交；
8. Reviewer通过并写理由；
9. 学员查看结果包，区分事实、AI建议、人工结论和积分；
10. 执行一次申诉或复核模拟；
11. Operator看见队列、SLA、通知和审计。

## 4. 模块专项场景

| 模块 | 必测 |
| --- | --- |
| 探索营 | 四宝藏顺序/内容；三实操；个人成长基线；下一训练阶段决定边界 |
| 新手村 | 任务授权/边界；真实任务生产隔离；NPC反馈；积分来源 |
| AI学院 | 阅读与能力分离；AI自查披露；组织资产候选 |
| 交付线公会 | 插件使命/能力；成员与任务状态分离；导师反馈；共享核心复用 |

## 5. 负向场景

- 点击学习完成不能生成PASS；
- 自证/AI初评/积分不能生成formal result；
- Learner不能查看他人数据；
- 未分配Reviewer不能审核；
- Reviewer不能审自己；
- 没有授权的真实任务不能发布；
- Journey不能直接写生产；
- 已finalize评审不能覆盖；
- 候选hash变化使旧签署失效；
- 通知失败不丢提交/评审事实。
- 非白名单不能进入Canary路径；
- `CANARY_DEPLOYMENT_GO`不能被解释为`RELEASE_GO`；
- 页面隐藏、客户端flag或robots规则不能代替服务端授权。

## 6. 通过标准

- 每模块真实目标用户≥2，全部P0场景通过；
- 学员成功完成率100%，无主持人代操作；
- 关键文案理解正确，无“AI/积分/点击即正式结论”误解；
- Reviewer返工与通过均成功，历史不丢；
- 0个P0/P1未处置缺陷；P2有Owner接受和修复时间；
- 权限/生产隔离负向场景100%通过；
- 结果、审计和候选manifest可对账。
- 8人名单无越界，非白名单访问拒绝率100%；
- release marker、候选SHA、镜像digest、配置hash和内容hash全程不漂移。

## 7. UAT 记录字段

`uat_id, canary_uat_id, release_marker, allowlist_hash, module, scenario_version, candidate_sha, deployed_image_digests, configuration_hash, content_hash, participant_role, participant_ref(受控), started_at, completed_at, steps, expected, actual, pass, defect_ids, evidence_refs, qa_signer, business_owner_signer, signed_at`。

公开/汇总报告使用匿名ref；个人证据受控保存。

## 8. 独立性

屠元琦组织UAT并确认业务可用，冯宇汀独立验证合同与候选。冯宇汀不得成为该候选Builder、模块内容批准人或Release Executor。角色已接受不等于本候选已签署。
