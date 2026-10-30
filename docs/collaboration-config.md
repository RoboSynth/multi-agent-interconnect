# 协作副本的运行配置

本协作副本使用稳定的合成身份编号，保留角色关联与历史任务记录。A01至A07对应项目七个角色，外部目标单独编号。

## 外部调用目标

ops/external_rpc_once.py从LIANSHU_EXTERNAL_TARGET_AIC读取目标身份，默认值为同形状的合成示例。运行实际调用时，将此环境变量设置为目标的完整登记身份；脚本的命令行目标参数继续可用。

PowerShell示例：

    $env:LIANSHU_EXTERNAL_TARGET_AIC = "<目标智能体身份>"
    python -X utf8 ops/external_rpc_once.py

证书、私钥和审批凭据由各自的私有运行配置加载，配置文件位置沿用部署说明。合成身份与匿名提供者名称用于协作记录；记录中的任务次数、耗时、业务结果与失败状态保留原数值。
