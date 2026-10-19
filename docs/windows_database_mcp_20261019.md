# Windows原生接手补证（2026-10-19）

数据库工具已在新的Windows虚拟环境中实际安装并验证：CPython3.12.14 AMD64、pglast7.2、postgres-mcp0.3.0和mcp1.30.0，项目requirements保持原字节。venv创建、安装、pip check、实际模块导入、SQL语法解析及CLI帮助均有成功退出记录。

## 数据库工具

直接使用`domains/database/requirements.txt`安装；其中Windows直链只覆盖CPython3.12 AMD64。实际取得的原版pglast wheel SHA256为`06a5b2d3dd63c44ca71e29fcc0fe162f959708bd348754e420ac1b9332d1d340`，安装后的7.2满足postgres-mcp要求的`==7.2.0`。模块与入口均来自新的`.venv-mcp-postgres`，没有向主`.venv`混装。

安装约83.5秒且使用部分缓存；69个实际解析包及归档哈希保存在[安装证据](../evidence/windows-database-mcp-20261019/README.md)。这是同机新环境验证，不是新机器15分钟冷部署或跨平台锁文件。

首个导入检查脚本用了工具requirements并未声明的`packaging`，因该检查器导入失败而exit1。随后只修正检查器，使用pip已有的版本比较模块，完成导入、官方wheel哈希、`SELECT 1`语法解析与`postgres-mcp.exe --help`验证；不重装、不增加生产依赖，原失败保留。解析SQL没有连接数据库。

## 一键启动与正常停机

Windows原生`deploy/local-up.ps1`现在使用已有`tools/workbench_host.py --launch`启动工作台，与分段接手路径一致。host核对实际PID、配置、五个本地参与者及就绪状态；运行信息带`session_nonce`，可按[环境与操作文档](本地开发环境与操作_20261018.md)中的PID＋nonce请求空闲时正常关闭工作台和参与者。

host关闭只管理工作台和参与者；原生业务底座与运维supervisor仍按文档分别核实并停止。`deploy/native.ps1 stop`不等于完整local-down，一键完整停机仍未实现。

重新启动前先按原会话正常关闭已有工作台，确认8766空闲。受控host沿用空闲端口检查，已有监听时不会新建第二个工作台。

入口的7个相关行为检查已通过：正常顺序与`--launch`路由、host失败不打印成功地址、前置配置失败提前结束、模型显式启用及Nginx路径处理，实际退出码0。见[入口证据](../evidence/windows-local-launcher-20261019/source-ready.json)。既有host源文件保持原字节，原host组件证据沿用。

本轮没有启动真实local-up、业务、数据库或平台消费者。入口路由、参数与失败传播使用隔离fixture验证；实际完整原生启动仍以接手电脑自己的新输出为准。旧`tools/start_workbench.ps1`仍作为独立入口保留，不将其旧metadata当作带nonce的host会话。
