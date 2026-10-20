# 使用自己的梧桐身份接入

本地演示不需要平台账户。正式接入使用[官方Registry](https://wt.ioa.pub/registry/)与[使用指南](https://wt.ioa.pub/docs.html)，平台登录、注册审核和证书签发由各自账户完成。

## 1. 准备七个身份

协调、应用、数据库主、数据库备、运维、业务验证、接入体检各一个AIC。复制 `integration/seven-identities.example.json` 到 `integration/private/my-team/identities.json`；修改每个角色的：

- `aic`：该角色获批的AIC。
- `endpoint`：官方提供的AMQPS inbox地址，必须与该AIC一致。
- `cert`：客户端证书链文件的本机绝对路径。
- `key`：对应私钥文件的本机绝对路径。
- 顶层`trust_bundle`：平台信任链的本机绝对路径；`discovery_url`、`mq_auth_url`按当前官方配置填写。

样例中的`REPLACE_WITH_...`及`X:/...`都必须替换；Linux使用`/home/...`等路径。私钥、证书、EAB、密码只保存在本机`private/`目录，不写回样例、不提交Git。七个身份均不能被另一台电脑同时使用。

## 2. 生成独立平台部署

按[开发说明](DEVELOPMENT.md)安装本项目Python 3.12依赖。以下以Linux为例；Windows把`.venv/bin/python`换成`.venv/Scripts/python.exe`。

```bash
.venv/bin/python deploy/prepare_deployment.py --mode seven --identity-file integration/private/my-team/identities.json --output runtime/private/my-team --project incident-my-team --app-v1-port 28081 --app-v2-port 28082 --order-port 28088 --reply-drop-port 28090
.venv/bin/python deploy/prepare_deployment.py --launch runtime/private/my-team/deployment.json --validate-only
.venv/bin/python deploy/prepare_deployment.py --launch runtime/private/my-team/deployment.json
```

仅使用WSL Docker的Windows机器在第一条准备命令追加`--wsl Ubuntu-22.04`。生成器保存同一项目的部署清单与Docker调用方式；后续通过同一manifest启动，不能手改其哈希。

## 3. 启动唯一协调者

上一步启动四个业务服务和六个领域容器；另启动一个协调者工作台：

```bash
.venv/bin/python workbench_server.py --config runtime/private/my-team/domains/coordinator/config.json --output artifacts/my-team-workbench --port 28766
```

访问`http://127.0.0.1:28766`，确认参与者发现和连接正常。此时使用正式AMQPS/AIC身份；检查证书有效期、私钥匹配、平台网络和该身份是否已被其他进程消费。

本步骤不自动运行故障实验、巡检或日志补发。采集配置与巡检源码保留在`deploy/fluent-bit/`和`ops/`，按自己的运行计划启用。不要为注册填写他人的平台凭据，也不要把同机stdio演示计为平台调用量。

## 停止并保留数据

先在协调者终端按Ctrl+C，让它正常关闭本次通信；再使用配置生成器给出的同一manifest停止其Docker服务：

```bash
.venv/bin/python -c "from pathlib import Path; from deploy.prepare_deployment import load_deployment,compose_command; import subprocess; m=load_deployment(Path('runtime/private/my-team/deployment.json')); subprocess.run(compose_command(m)+['stop','--timeout','30'],check=True)"
```

这会保留数据卷和记录。正式部署的实际连通性取决于自己的证书、审批状态和平台网络，配置文件生成成功不等于平台验收通过。
