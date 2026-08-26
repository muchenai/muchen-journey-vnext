# G7 当前 Golden Path 机器复核与语义校正合同 V0.1

> 状态：`MACHINE_READY_FOR_HUMAN / HUMAN_NOT_RUN / UNCOMMITTED_CANDIDATE / RELEASE_BLOCKED`  
> 日期：2026-08-24  
> Owner：Muchen Journey Program Controller  
> 范围：`/ → /join → /app → 第一份必读材料`

## 1. 使用者结果

首次受邀学员无需主持人解释，即可看见五张成长地图、知道当前从探索营开始，并在一个清晰主行动下打开第一份必读材料。Career Map 明确为贯穿五阶段的结果层，不与当前行动竞争。

## 2. 本阶段校正

1. `/app` 先显示探索营当前行动，完成当前一步后才显示全模块目录。
2. 公开五阶段从已延期的 BOSS 副本校正为第一发布的认证竞技场。
3. 首页与邀请页明确 Career Map 贯穿全程。
4. 390px 邀请页不再隐藏地图名称和 Career Map 说明，同时保留唯一验证按钮在首屏。

## 3. 机器 Gate

- 390、768、1280 CSS px 均无横向溢出。
- 首页与邀请页展示认证竞技场，不展示 BOSS 副本。
- `/app` 当前行动 CTA 在三种视口首屏内，且 CTA 之前没有模块目录链接。
- 第一份必读材料在任何输出表单之前出现。
- 无控制台 error/warning；reduced motion 和失效邀请恢复路径保留明确下一行动。
- Web 合同测试、TypeScript、ESLint 和生产构建通过。

## 4. 人类 Gate

机器通过只能进入 `READY_FOR_HUMAN`。需要 3/3 首次目标学员在无主持人救援下完成：

1. 10 秒内说出五张地图、当前探索营和下一步；
2. 60 秒内独立打开第一份必读材料；
3. 进度清晰度与继续意愿中位数均不低于 4/5；
4. 主持人干预为 0。

## 5. 不变量与禁止事项

- Journey 不直接执行生产作业。
- 正式能力结果只来自实操、证据和真人签署。
- AI、积分和自证不能单独产生正式人才状态。
- 高影响结论必须允许独立申诉。
- 本候选未提交，未经刘默文明确授权不得提交、合并、打标签、部署或迁移生产数据。

## 6. 证据

- 候选清单：`outputs/controller-integration/g7-current-golden-path-reconciliation/candidate-manifest.json`
- 基线失败：`outputs/controller-integration/g7-current-golden-path-reconciliation/baseline-machine-evaluator-report.json`
- 修正后复核：`outputs/controller-integration/g7-current-golden-path-reconciliation/machine-evaluator-report.json`
- 浏览器截图：`output/playwright/g7-current-golden-path/post-fix/`
- 真人结果：`outputs/controller-integration/g7-current-golden-path-reconciliation/human-validation.json`

## 7. 下一 Gate

`G7_HUMAN_GOLDEN_PATH_VALIDATION`。通过前不得把本阶段写成真人通过、可合并或可发布。
