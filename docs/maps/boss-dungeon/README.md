# BOSS副本：第一条黄金路径

状态：`ISOLATED_DRAFT_BUILD`

地图：`boss-dungeon`

契约：`outputs/map-workstreams/boss-dungeon/contract.json`

## 人可以完成什么

首次体验者从读取四条前置合成能力证据与三项目标能力开始，在明确合成模拟和 People AI 治理边界后，确认四个团队角色以及时间、范围、隐私约束，再提交一个引用至少一条证据和一项约束的项目决定。终点回执会将合成事实、AI 建议、人类选择和系统状态分开呈现。

## 可运行入口

从仓库根目录启动静态服务器：

```bash
python3 -m http.server 4173
```

访问 `http://127.0.0.1:4173/prototypes/boss-dungeon/index.html?reset=1`。

## 边界

- 所有公司、客户、人员、项目、证据和评估内容均为明确标记的合成模拟。
- 原型不调用 API，只使用 `sessionStorage` 保存当前浏览器会话中的合成演练进度。
- Person、Capability、Evidence、Progress、Identity 与共享导航、设计系统、API 均未修改。
- 本地图只生成练习回执，不生成真实雇佣、晋升、淘汰、薪酬或绩效结论。
- 机器验收不能代替真人对方向感、理解、吸引力与继续意愿的判断。

## 自动契约检查

```bash
node --test prototypes/boss-dungeon/contract.test.mjs
```
