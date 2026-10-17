# T91 匿名答辩开发稿内容源

本目录包含15页逐页内容、讲稿、可编辑图表数据、证据定位和Artifact Tool生成入口。它是开发稿的内容准备包，**PPTX与PDF尚未生成**。

证据截止：2026-10-17 12:50:41.317 UTC。纳入该时点已闭合的新版镜像断网验证及T07周期2；后续巡检、模型或平台运行不进入本包。原13页技术报告保持独立且未改动。

## 文件

- `content.json`：15页用途、页面文案、讲者备注及证据ID。
- `speaker-script.md`：与页面对应的讲稿和原项目相对定位。
- `chart-data.json`：4个原生可编辑图表的数据与单位。
- `evidence.json`：匿名派生事实、原项目定位和原件SHA。它不包含身份材料或原始日志。
- `assets/f12-unknown-missing-key.png`：既有真实UI验收截图，原图未修改。本轮已全尺寸显示并目视检查，无学校、账号、完整AIC、provider、密钥或绝对路径。
- `prepare.mjs`：从原项目的已闭合公开资料重新生成匿名数据、讲稿及单张素材。需要原项目证据可用，不能假定团队副本拥有全部原件。
- `build.mjs`：官方 `@oai/artifact-tool` JS入口，**未执行**。其原生表格/图表与布局尚待runtime验证，不保证当前API实现或版式已通过。
- `validate.mjs`、`validation.json`：内容、数据和匿名范围的检查，不能代替渲染或原生PowerPoint验收。
- `source-ready.json`：本内容包逐文件白名单和SHA，不代表PPTX已完成。该审核文件仅保留在原项目；团队副本以 `SNAPSHOT-MANIFEST.json` 溯源，不随10项内容包复制。

## 15页用途

1. 作品与证据截止
2. 真实错误动作时间线
3. 协调与资源权限
4. 总体架构及信任域
5. 原生、改造、新增
6. 平台注册、发现、互联、访问状态
7. 可接续任务与资源效果核验
8. MCP受控网关
9. M0/M1/M2定义及共享约束
10. 安全和原订单结案
11. 真实F12工作台截图
12. 历史模型结果三图
13. E1结果与两周期平台边界
14. 贡献准备和验收缺口
15. 工程结论

## 设计方向

16:9，暖白底、深蓝正文、青绿色强调和少量赭色数据对照。设计字体为本机已有的Microsoft YaHei，字体文件不随包分发。标题64px/44px，主体通常24–31px，脚注16px。以平面排版为主，表格与图表使用原生可编辑对象。架构和流程页属于证据图解，生成后须逐页检查关系和文字，避免把页面做成仪表盘。

第12页的三图分别为历史恢复估计中位数、探测总数、模型token总数。第13页为E1-b信息量与完整IFC字节。图表数据保留完整数值，显示精度可以简化，不能改变单位或比较范围。

## 事实边界

- 历史45主格是四场景v2与F06-v3的声明组合，原F06-v2九次失败保留。历史M1只自由选择观察。
- 完整工具M1只有F01三方法各一次的两版开发验收。首批M1错误动作导致unknown并停止，复验恢复但仍多一次不必要高权限动作。
- E1有18例最终及独立验证，17连续加1控制器续验，真实模型调用和token均0。三策略共用账本。
- 恢复包的信息量少于完整历史，但兼容重复编码让实际wire更大，不能声称wire或模型token收益。
- 正式平台是三旧参与域的两个健康巡检周期，不能称新七角色、24小时或7天验收。
- 新镜像只完成断网、只读、无env无挂载的临时验证。证书按用户安排暂缓，新七身份未启动，正式target preflight和新版45格未运行。
- 贡献仍是草稿和审阅补丁，未发布Issue或PR。指定范围凭据扫描为0不能扩展为系统永久保证。

## 当前格式阻塞

当前会话工具目录无 `load_workspace_dependencies`，Node不能解析 `@oai/artifact-tool`。已知项目缓存、官方插件目录和独立包目录未发现该bundle。官方演示技能要求使用其提供的runtime，并写明“Do not install substitutes or modify the bundled dependencies”。因此本轮不安装替代包，也不使用python-pptx或COM创建PPT。

本机PowerPoint可执行文件存在，中文字体存在；这只证明后续原生QA有候选环境，**尚未打开任何本稿PPTX，尚未导出PDF，尚未做逐页渲染QA**。

工具恢复后，应调用 `load_workspace_dependencies`，按技能给出的Node/modules/Python路径运行。先按演示技能记录创作操作，再把本目录 `node_modules` 链接到供应的包目录，设置 `SKILL_DIR` 与 `RUNTIME_PYTHON`，运行 `build.mjs`。生成后的candidate和final须独立保存，修订输出用新文件名。必须完成finalizer、全15页渲染、全尺寸目视检查、原生PowerPoint打开确切交付字节、PDF导出与页面检查后，才可改为成品交付状态。当前源中原生图表布局不是已验证模板。

## 可复现的本轮检查

在已有Node环境中：

```powershell
node --check build.mjs
node --check prepare.mjs
node --check validate.mjs
node validate.mjs
```

原项目重提取可运行 `node prepare.mjs`；它只读取列表中的已闭合公开原件并写本目录。`evidence.json`中的定位以原项目根目录为基准，SHA固定的是原件，不自动代表团队副本同路径。`team_copy`字段逐项说明本轮只读检查时副本有无同字节文件。公开派生材料在团队副本中的候选位置为 `deliverables/defense-content-development-20261017/`，其中 `assets/` 和JSON等引用均为包内相对路径。

## 后续成品检查

需复核15页总数、讲稿来源、中文字体、文字溢出、可编辑表格与图表、原生PowerPoint页面及PDF每页。匿名检查要覆盖PPTX的notes/属性、图表工作簿、图片和PDF，不能只搜当前JSON。最终上传应另给只包含已审定成品和必要生成源的精确白名单。
