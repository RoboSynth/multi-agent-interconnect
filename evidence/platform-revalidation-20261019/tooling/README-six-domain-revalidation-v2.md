# 六域采集v2：mount数组顺序修正

原采集session69771实际exit1（chunk `d86fbb`），`runtime-amp-capture/collection-failure.json`与已复制文件、14条命令元数据全部保留。14次Docker命令实际exit0：首inspect、6次卷inspect、6次cp、末inspect；由控制流定位为最后的前后identity比较guard失败，而不是ownership、只读mount或cp失败。原始两次inspect仅保留stdout哈希，没有保存完整原文，不能重建其原始数组。

本次另执行2次只读inspect（chunk `31d797`，实际exit0），六个具名容器均已停止。白名单证据在 `amp-capture-diagnosis-20261019T060942465606Z/diagnosis.json`，SHA256为 `35054152266ce145b1b07246d59533a5f954f60064f1f28e5e5d8b3e0220ac87`。结果直接观察到ops-agent的mount数组返回顺序变化；按Destination排序后的完整mount字典SHA相同，容器ID、image、name、StartedAt、FinishedAt、status、running、labels均相同；其余五容器无投影字段变化。没有启动、exec、cp或修改容器。先前受限WSL探测exit4294967295的诊断目录亦保留。

v2仅把原identity中的Mounts数组按Destination排序再比较，仍保留每个mount字典的所有字段；其他identity/停止状态/域/只读bind/own-volume guard不变。该变化修正集合顺序的比较语义，不取消真实mount变化检测。旧checker、collector、tools配置与失败原件均不改。

供根代理审核的新入口：

- `collect_six_revalidation_domains_v2.py --collect --terminal <真实batch-terminal.json> --terminal-sha <真实SHA>`，默认创建全新的 `runtime-amp-capture-v2`，不复用旧失败目录。
- 采集成功后，`check_closed_revalidation_access_credentials_v2.py --scan --terminal <真实终态> --terminal-sha <SHA> --domain-snapshot-manifest <v2采集manifest> --domain-snapshot-sha <SHA> --output <本publication下全新分析目录>`。配置固定于 `revalidation-analysis-tools-v2.json`。

checker v1 SHA `2b91078d80ce1cc7f3bf459355aa47c7818d21aef481bde29fe00e1d2c74a5e2`；v2 SHA `eb598b462a91b04597093ae04f68e0f0cd353155ee93ea62d56bb54308f20634`。准备v2时未执行新采集或分析；根审核后另行调用。正式12例与11/1结果不改，不重跑任何案例。日志对账的坏行、缺端及T05=false应原样保存，不能由实验通过数改判。
