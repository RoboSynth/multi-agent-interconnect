"""Prepare browser actions and ACS documents for the incident agents."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "integration" / "incident"
MODULE = "/registry/static/js/index-BBS9pLLM.js"
API = "https://wt.ioa.pub/registry-server/api/v1/agent/client"
ROLES = {
    "leader": ("故障协作协调智能体", "incident.coordinate", "由本机 wutong_incident.py --run 命令发起故障协作，通过梧桐发现和邀请应用、数据库与恢复分析智能体，收集故障信息，安排连接配置修正与数据库恢复，汇总任务和订单结果。", []),
    "application": ("故障协作应用智能体", "incident.application", "读取实验订单服务的访问结果和连接配置；根据数据库智能体返回的地址修正本实验应用连接配置，返回修改后的配置与版本。", ["inspect", "repair_endpoint"]),
    "database": ("故障协作数据库智能体", "incident.database", "读取实验数据库服务的可用状态、地址和配置版本；恢复本实验暂停的数据库服务，返回运行状态和修改次数。", ["inspect", "resume"]),
    "verification": ("故障协作恢复分析智能体", "incident.verification", "通过实验订单网站查询真实SQLite订单，返回HTTP状态、订单内容以及恢复结果。", ["verify"]),
}


def write_action(name, body, result_file):
    code = f"async page => {{ {body} }}"
    action = {"session": "wutong", "args": ["run-code", code], "resultFile": str(result_file)}
    path = OUT / f"browser-{name}.json"
    path.write_text(json.dumps(action, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "prepare", "register", "status", "eab"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    prelude = f"const {{aM:http}}=await import({json.dumps(MODULE)}); const api={json.dumps(API)};"
    if args.action == "list":
        body = "return await page.evaluate(async()=>{" + prelude + "const r=await http.request('get',api,{params:{page_num:1,page_size:50}});const d=r.data||r;return {at:new Date().toISOString(),data:d};});"
        write_action("list", body, OUT / "owner-agents-before.json")
        return
    if args.action == "prepare":
        base = json.loads((ROOT / "integration/two-agent/partner.approved.acs.json").read_text(encoding="utf-8"))
        records = []
        owner = json.loads((OUT / "owner-agents-before.json").read_text(encoding="utf-8"))["data"]
        items = owner.get("items", [])
        for role, (name, skill, description, actions) in ROLES.items():
            acs = {**base, "aic": "", "active": False, "name": name, "version": "0.2.0",
                   "lastModifiedTime": datetime.now(timezone.utc).isoformat(), "description": description,
                   "endPoints": [{"transport": "AMQP", "url": "amqps://wt.ioa.pub:5671/acps?inbox=inbox_{AIC}", "security": [{"mtls": []}]}],
                   "skills": [{"id": skill, "name": name.replace("故障协作", ""), "version": "0.2.0", "description": description,
                               "tags": ["incident-pilot", "故障协作", role],
                               "examples": [json.dumps({"action": actions[0]}, ensure_ascii=False)] if actions else [],
                               "inputModes": ["application/json"], "outputModes": ["application/json"]}]}
            (OUT / f"{role}.submission.acs.json").write_text(json.dumps(acs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            draft = next((item for item in items if role == "application" and item.get("name") == "故障协作应用探测智能体" and item.get("approval_status") == "DRAFT"), None)
            records.append({"role": role, "id": draft["id"] if draft else None, "acs": acs})
        (OUT / "registration-input.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(OUT / "registration-input.json")
        return
    if args.action == "register":
        records = json.loads((OUT / "registration-input.json").read_text(encoding="utf-8"))
        # Save drafts first. Submission is a separate concrete browser action.
        inner = prelude + "const records=" + json.dumps(records, ensure_ascii=False) + ";const agents=[];for(const row of records){const data={name:row.acs.name,version:row.acs.version,description:row.acs.description,acs:JSON.stringify(row.acs),is_ontology:false};const r=await http.request(row.id?'put':'post',api+(row.id?'/'+row.id:''),{data});const d=r.data||r;agents.push({role:row.role,id:d.id,name:d.name,status:d.approval_status});}return {at:new Date().toISOString(),agents};"
        write_action("register", "return await page.evaluate(async()=>{" + inner + "});", OUT / "draft-agents.json")
        return
    manifest = json.loads((OUT / "draft-agents.json").read_text(encoding="utf-8"))["agents"]
    if args.action == "status":
        inner = prelude + "const records=" + json.dumps(manifest, ensure_ascii=False) + ";const agents=[];for(const row of records){const r=await http.request('get',api+'/'+row.id,{params:{_t:Date.now()}});const d=r.data||r;agents.push({role:row.role,id:d.id,name:d.name,aic:d.aic,status:d.approval_status,comments:d.process_comments,acs:typeof d.acs==='string'?JSON.parse(d.acs):d.acs});}return {at:new Date().toISOString(),agents};"
        write_action("status", "return await page.evaluate(async()=>{" + inner + "});", OUT / "registration-status.json")
        inner = prelude + "const records=" + json.dumps(manifest, ensure_ascii=False) + ";const agents=[];for(const row of records){const r=await http.request('post',api+'/'+row.id+'/submit');const d=r.data||r;agents.push({role:row.role,id:d.id,name:d.name,status:d.approval_status});}return {at:new Date().toISOString(),agents};"
        write_action("submit", "return await page.evaluate(async()=>{" + inner + "});", OUT / "submitted-agents.json")
        return
    agents = json.loads((OUT / "registration-status.json").read_text(encoding="utf-8"))["agents"]
    if any(row["status"] != "APPROVED" or not row["aic"] for row in agents):
        raise RuntimeError("All incident identities must be approved before requesting EAB")
    private = ROOT / "integration/private/incident"
    private.mkdir(parents=True, exist_ok=True)
    body = "const agents=" + json.dumps([{k: row[k] for k in ("role", "aic")} for row in agents]) + ";const reports=[];for(const row of agents){await page.evaluate(async row=>{" + prelude + "const r=await http.request('post','https://wt.ioa.pub/registry-server/acps-atr-v2/eab/'+encodeURIComponent(row.aic));const e=r.data||r;if(!e.keyId||!e.macKey||e.aic!==row.aic)throw new Error('EAB identity mismatch');const el=document.createElement('a');el.id='incident-eab';el.download=row.role+'-eab.json';el.textContent='Download identity';el.href=URL.createObjectURL(new Blob([JSON.stringify(e)],{type:'application/json'}));document.body.appendChild(el);},row);const pending=page.waitForEvent('download');await page.locator('#incident-eab').click();const download=await pending;await download.saveAs(" + json.dumps(private.as_posix() + "/") + "+row.role+'-eab.json');await page.evaluate(()=>{const el=document.querySelector('#incident-eab');URL.revokeObjectURL(el.href);el.remove();});reports.push({...row,downloaded:true});}return {at:new Date().toISOString(),agents:reports};"
    write_action("eab", body, OUT / "eab-acquisition.json")


if __name__ == "__main__":
    main()
