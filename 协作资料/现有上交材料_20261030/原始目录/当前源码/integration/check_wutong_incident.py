"""One local business regression: real HTTP/SQLite, AIP callback transport stub."""
import asyncio
import json
from pathlib import Path
import socket
import uuid

import wutong_incident as incident
from wutong_smoke import (ACSObject, ManagedProbePartner, TaskCommand, TaskCommandType,
                          TaskState, TextDataItem, utc_now)

FIXTURE_LEADER = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
FIXTURE_PARTNER = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JUE"


class CallbackLab(incident.Lab):
    async def setup(self):
        self.database, _ = await self.launch("database")
        self.target, _ = await self.launch("target")
        self.runtimes, self.clients = {}, {}
        for role in incident.ROLES:
            runtime = incident.IncidentRuntime(role=role, target=self.target, database=self.database,
                leader_aic=FIXTURE_PARTNER, allowed_peer_aic=FIXTURE_LEADER,
                rabbitmq_config={}, record=self.event, identity_binding_enabled=True)
            client = ManagedProbePartner(partner_aic=FIXTURE_PARTNER,
                                         rabbitmq_user=None, rabbitmq_password=None)
            client._group_id = "offline-incident-group"
            self.runtimes[role], self.clients[role] = runtime, client

    async def call(self, mode, role, payload):
        self.calls += 1
        messages = []
        client, runtime = self.clients[role], self.runtimes[role]
        async def capture(message):
            messages.append(message)
        client._publish_message = capture
        task_id = "offline-business-" + uuid.uuid4().hex
        command = TaskCommand(id="offline-command-" + uuid.uuid4().hex, sentAt=utc_now(),
            senderRole="leader", senderId=FIXTURE_LEADER, mentions=[FIXTURE_PARTNER],
            groupId=client.group_id, sessionId=self.case_id, taskId=task_id,
            command=TaskCommandType.Start,
            dataItems=[TextDataItem(text=json.dumps({"capability": role, **payload}))])
        await runtime._probe_command(client, command, True)
        assert [message.status.state for message in messages] == [
            TaskState.Accepted, TaskState.Working, TaskState.AwaitingCompletion], messages
        product = json.loads(messages[-1].products[0].dataItems[0].text)
        assert product["capability"] == role and product["action"] == payload["action"]
        complete = command.model_copy(update={"command": TaskCommandType.Complete, "dataItems": None})
        await runtime._probe_command(client, complete, True)
        assert messages[-1].status.state == TaskState.Completed
        return product["result"]


async def main():
    output = incident.ROOT / "integration" / "artifacts" / ("incident-offline-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    lab = CallbackLab(output)
    reserved = socket.socket()
    reserved.bind(("127.0.0.1", 0))
    lab.closed_port = reserved.getsockname()[1]
    lab.ports.add(lab.closed_port)
    try:
        await lab.setup()
        result = await lab.run_case("offline-callback", "combined", 1)
        assert result["passed"] and result["aip_tasks"] == 8 and result["mutations"] == 2, result
        guards = await lab.guard_checks()
        assert all(guards.values()), guards
    finally:
        reserved.close()
        lab.close()
    summary = {"mode": "local-http-sqlite-and-aip-callback-regression", "passed": True,
               "platform_run_success": False, "platform_network_attempted": False,
               "result": result, "guards": guards,
               "processes_stopped": all(process.poll() is not None for process in lab.processes),
               "output": str(output)}
    incident.save_json(output / "RESULT.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
