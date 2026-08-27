# Pro 独立复核清单

Mini 只有在提交单一审计包后才进入本清单。Pro 不从 Mini 的总结文字推断 Gate。

## A. 来源与候选

- 完整 SHA 存在、分支正确、候选提交可读取。
- `7c57a2f...` 是候选祖先，V2 控制包 hash 通过。
- 候选提交 clean，manifest 位于仓库外且未造成 post-freeze commit。
- V1.0.3 只作产品语义基线，旧进度和旧机器证据没有被当作当前 PASS。

## B. 内容包

- 四个正式包全部通过当前 Runtime Pydantic 模型。
- root/content/task/rubric 每一层 hash 与 Runtime canonical rule 一致。
- Owner 批准绑定的候选 module hash、探索营 source binding 没有改变。
- 如有业务字段变化，存在新的 Owner 批准；否则判定 FAIL。
- 篡改、Owner role、Reviewer overlap、unsafe data policy 负向测试通过。

## C. G2

- API、Web、Worker、OpenAPI、migration、secret、dependency 均绑定同一 SHA。
- Docker Compose 使用独立 project，证据中没有采用另一工作区容器。
- fresh database 从 0001 到唯一 head 通过；旧数据迁移数为 0。
- Web production build 与真实可执行 golden path 证据存在；机器结果未冒充真人理解。

## D. 供应链与候选

- 三镜像 digest、三 SBOM、扫描器/数据库身份和扫描时间齐全。
- 当前扫描无法完成时状态为 BLOCKED，未复用旧结果。
- candidate manifest 无自引用；候选 tag 晚于全部 G2 PASS。

## E. 恢复与边界

- 只在隔离合成环境执行备份、恢复与应用回滚。
- off-host、告警真人回执没有实际证据时保持 NOT_RUN。
- 六项 production effects 全为 false。
- UAT、独立 QA/Release Reviewer 候选签署、Release GO 均未由 Mini 填写。

## Pro 输出

只允许以下结论之一：

- `PRO_FINAL_CANDIDATE_FREEZE_REVIEW=PASS`；
- `PRO_FINAL_CANDIDATE_FREEZE_REVIEW=CONDITIONAL_FAIL`，列出可在同一候选修复的机器问题；
- `PRO_FINAL_CANDIDATE_FREEZE_REVIEW=FAIL_REOPEN_CANDIDATE`；
- `PRO_FINAL_CANDIDATE_FREEZE_REVIEW=BLOCKED_EXTERNAL_EVIDENCE`。

Pro PASS 仍不构成生产 Canary 或发布授权。
