# WP-31 身份交付与阶段衔接修复（2026-09-10）

状态：本地实现及受影响回归通过；未commit/push、未合入main、未构建新候选、未部署。
本文不是已上线证明，也不授予新环境或生产操作权限。

## 本次失败与历史失败的关系

Run `34429951107` 的失败日志只有 `<stdin>` 第7行 `AssertionError`，精确对应
旧 Workflow 的 `len(identity-result.json) < 446`。远端身份命令、scp、JSON解析、
字段集合和角色断言已通过。这不是“身份步骤又失败，所以旧修复无效”。

历史组织唯一性假设和容器读取0600请求文件的问题处于更早位置。历史诊断证据不全的
Run 不能倒推为同一根因。本次已越过这些位置，但不能据此声称所有历史问题永不复发。

确定的本次原因：九字段紧凑JSON含四个36字符UUID、43字符链接token、角色和时间，
无微秒样本501字节，有微秒样本508字节；RSA4096 OAEP-SHA256上限446字节。
这些字节数来自纯合成样本，不是读取实际身份结果。真实日志直接证明的只有长度断言失败。

## 一起修复的衔接缺陷

1. 直接RSA加密整个结果改为JWE紧凑序列化：`RSA-OAEP-256`包裹一次性32字节AES密钥，
   `A256GCM`加密完整JSON；96位随机nonce，128位认证tag。Run、candidate和公钥指纹在
   受认证的protected header中。九字段、角色、短期链接有效期不变，不压缩或截断结果。
2. 恢复完整性检查必须在身份写入之前：旧顺序先bootstrap提交用户/角色/审计/链接，
   再逐字节比较恢复facts与当前facts，必然把自身写入识别为drift。本修复将完整deploy
   （包含原有恢复漂移、迁移和迁移前后行数校验）放到bootstrap之前，不修改或跳过这些校验。
3. 顺序为：恢复证明 → deploy → bootstrap → 密文上传 → 最终inspect/部署证明。
   因此API/Web可能短暂运行但身份交付尚未完成；这不代表UAT就绪，不通知测试人员。
   bootstrap或密文上传失败、部署开始后取消均会请求现有回滚路径。强制终止/主机失联时不能仅凭配置断言回滚成功，
   必须查看实际运行证据。此修复不自动删除数据库。
4. fast最终部署证明的previous Run改用当前`GITHUB_RUN_ID`；独立deploy仍使用输入backup Run。
   旧fast默认空输入会被`wp31_phase_evidence.py`拒绝，不能复用或虚构旧backup Run。
5. 公钥和加密依赖在基础设施访问/建库前验证。依赖版本和下载hash复用已有requirements.lock，
   无新增应用依赖。旧身份job仍`if: false`，只消除重复加密实现与其临时文件清理遗漏。
6. 本地结果文件创建受限且禁止覆盖；身份步骤EXIT立即清理本地明文，现有always步骤负责远端
   清理。proof使用`plaintext_cleanup=ALWAYS_STEP_REQUIRED`，不在实际清理之前宣称明文已全部删除。

## 密文格式及受控读取

Artifact名称仍为 `wp31-identity-bootstrap-<Run ID>`；密文文件名仍为
`identity-bootstrap-result.json.enc`，但内容现为JWE五段格式，不再是512字节裸RSA块。
旧的`openssl pkeyutl -decrypt`不能直接读取新版。不要用试错方式读取旧文件。

账号持有人在受限本地目录使用对应私钥执行以下命令；示例是占位参数，不可原样执行：

```text
python scripts/wp31_identity_result.py decrypt --private-key <受限私钥文件> --input <密文文件> --output <尚不存在的受限结果文件> --run-id <真实Run> --candidate <binding中的完整候选SHA>
```

程序只输出PASS/FAIL，不打印身份、链接或私钥。解密成功不表示链接尚未过期或部署已成功；
还须检查对应Run状态，并由账号持有人在有效期内完成绑定。不得把解密结果粘贴到聊天或仓库。
POSIX输出文件权限0600；Windows需先保证父目录ACL受限，不能把chmod视为Windows ACL保证。
开发回归只生成临时测试密钥，不读取任何实际私钥。本文未授权自动解密真实身份结果。

## 数据库时间线（北京时间）

- 2026-09-09 20:15：用户报告组长删除指定数据库。
- 旧Run34350601787：建库未执行，不会使上述删除失效。
- 2026-09-10 10:36:14—10:36:21：Run34429951107成功重建指定库。
- 10:36:21—10:37:44：恢复成功；10:38:44身份交付失败；10:38:52 Run终止。
- 当前保留数据库，不请求删除，不运行新的Canary。需要清理时依据新候选准备情况、
  无活动运行及无引用证据协调组长，不由Codex尝试删除。

## 验证与发布边界

回归包含：真实尺寸加密解密、独立按JWE字段解密、随机性、密文/nonce/tag/包装密钥/header
篡改、错密钥/错Run/错候选、输入合同、受限输出/不覆盖/日志脱敏，Workflow顺序、回滚条件、
fast evidence绑定，以及已有身份幂等、组织选择、stdin、数据库guard/快照和Canary合同测试。

本次改变Workflow行为，需要新候选和新证据，不能标为Ops-only或沿用旧授权到新字节。
本地测试通过不等于已合入main、已构建候选或已满足真实Canary验收。

本轮实际结果（2026-09-10）：11个受影响测试文件合计132通过、1跳过；Windows专用
Python3.12测试环境，不冒充项目Python3.14/Linux全量CI。Workflow YAML解析通过，
37段相关Shell脚本`bash -n`通过，重复step id检查通过；Ops closure 41 discovered/
55 bound/missing 0、Canary contract-check和git diff --check通过。
没有执行本地Docker全栈、真实恢复数据库迁移或真人OAuth验收，这些仍需后续候选/环境验证。
已有用户未跟踪的历史计划文件保持原样；没有修改任何真实Secret、公钥/私钥或数据库。

规范：[JWE RFC7516](https://www.rfc-editor.org/rfc/rfc7516.html)、
[JWA RFC7518](https://www.rfc-editor.org/rfc/rfc7518.html)。使用项目现有cryptography实现的
AESGCM/RSA原语，不自制密码算法。
