"""Disposable loopback test services. Never point these at production systems."""
import argparse
import json
import os
import sqlite3
import uuid
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from acps_sdk.aip import Product, StructuredDataItem, TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers, DefaultHandlers, TaskManager, add_aip_rpc_router,
)
from acps_sdk.aip.aip_identity import AipIdentityError


async def execute_business_action(role, payload, *, target, database):
    """Execute one existing disposable-lab capability over its loopback tools."""
    async def request(method, url, **kwargs):
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            result = await client.request(method, url, **kwargs)
            result.raise_for_status()
            return result.json()

    action = payload['action']
    capability = role.removesuffix('-agent')
    if capability == 'application':
        if action == 'inspect':
            async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
                result = await client.get(target + '/orders')
            cfg = await request('GET', target + '/admin/config')
            return {'http_status': result.status_code, 'response': result.json(), 'config': cfg}
        if action == 'repair_endpoint':
            return await request('POST', target + '/admin/config', json={
                'database_url': payload['database_url'],
                'expected_revision': payload['expected_revision']})
    elif capability == 'database':
        if action == 'inspect':
            return await request('GET', database + '/admin/status')
        if action == 'resume':
            return await request('POST', database + '/admin/resume', json={
                'expected_revision': payload['expected_revision']})
    elif capability == 'verification' and action == 'verify':
        samples = []
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            for _ in range(3):
                result = await client.get(target + '/orders')
                body = result.json()
                samples.append({'status': result.status_code, 'body': body})
        expected = [[1, 'book'], [2, 'keyboard'], [3, 'monitor']]
        return {'passed': all(s['status'] == 200 and s['body'].get('orders') == expected
                              for s in samples), 'samples': samples}
    raise ValueError(f'Action {action!r} is not provided by {role}')


def make_app(args):
    app = FastAPI(title=f"Incident pilot: {args.role}")

    @app.get('/health')
    async def health():
        return {'ok': True, 'role': args.role, 'pid': os.getpid()}

    if args.role == 'directory':
        records = {}

        @app.post('/register')
        async def register(record: dict):
            records[record['id']] = record
            return {'registered': record['id']}

        @app.get('/discover')
        async def discover(capability: str):
            return {'agents': [r for r in records.values() if capability in r['capabilities']]}

    elif args.role == 'database':
        db_path = Path(args.data_dir) / 'orders.sqlite'
        with sqlite3.connect(db_path) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, item TEXT)')
            conn.executemany('INSERT OR IGNORE INTO orders VALUES (?, ?)',
                             [(1, 'book'), (2, 'keyboard'), (3, 'monitor')])
        state = {'available': True, 'revision': 0, 'mutations': 0}

        @app.get('/query')
        async def query():
            if not state['available']:
                return JSONResponse({'error': 'database_unavailable'}, status_code=503)
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute('SELECT id, item FROM orders ORDER BY id').fetchall()
            return {'orders': rows}

        @app.get('/admin/status')
        async def status():
            return {**state, 'endpoint': f'http://127.0.0.1:{args.port}'}

        @app.post('/admin/reset')
        async def reset(body: dict):
            state.update(available=body['available'], revision=state['revision'] + 1, mutations=0)
            return state

        @app.post('/admin/resume')
        async def resume(body: dict):
            if body['expected_revision'] != state['revision']:
                raise HTTPException(409, 'stale_database_evidence')
            if not state['available']:
                state.update(available=True, revision=state['revision'] + 1,
                             mutations=state['mutations'] + 1)
            return state

    elif args.role == 'target':
        state = {'database_url': args.database, 'revision': 0, 'mutations': 0,
                 'unsupported_fault': False}

        @app.get('/orders')
        async def orders():
            if state['unsupported_fault']:
                return JSONResponse({'error': 'unsupported_business_fault'}, status_code=500)
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=0.7) as client:
                    result = await client.get(state['database_url'] + '/query')
                return JSONResponse(result.json(), status_code=result.status_code)
            except httpx.TransportError:
                return JSONResponse({'error': 'database_connection_failed'}, status_code=503)

        @app.get('/admin/config')
        async def config():
            return dict(state)

        @app.post('/admin/reset')
        async def reset(body: dict):
            state.update(database_url=body['database_url'], unsupported_fault=body.get('unsupported_fault', False),
                         revision=state['revision'] + 1, mutations=0)
            return state

        @app.post('/admin/config')
        async def update(body: dict):
            if body['expected_revision'] != state['revision']:
                raise HTTPException(409, 'stale_application_evidence')
            # Only the disposable database is an allowed repair destination.
            if body['database_url'] != args.database:
                raise HTTPException(400, 'destination_not_allowlisted')
            if state['database_url'] != body['database_url']:
                state.update(database_url=body['database_url'], revision=state['revision'] + 1,
                             mutations=state['mutations'] + 1)
            return dict(state)

    else:
        terminal_states = {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}

        def check_context(command, task):
            # Local consistency guard only. Declared sender/session are NOT authenticated identities.
            owner = task.commandHistory[0]
            if command.sessionId != task.sessionId or command.senderId != owner.senderId:
                raise AipIdentityError('Task belongs to another session or declared sender')

        def guarded(handler):
            async def wrapped(command, task):
                check_context(command, task)
                return await handler(command, task)
            return wrapped

        async def execute(payload):
            return await execute_business_action(args.role, payload, target=args.target, database=args.database)

        async def start(command, task):
            if task:
                check_context(command, task)
                return task
            # AIP permits a new Start without taskId; the server supplies one.
            if not command.taskId:
                command.taskId = 'task-' + uuid.uuid4().hex
            try:
                text = next((x.text for x in command.dataItems or [] if isinstance(x, TextDataItem)), None)
                if text is None:
                    raise ValueError('Start requires a text item containing a JSON object')
                payload = json.loads(text)
                if not isinstance(payload, dict) or not isinstance(payload.get('action'), str):
                    raise ValueError('Start requires a JSON object with a string action')
            except (ValueError, TypeError) as exc:
                # AIP requires rejection directly from no task, not Accepted -> Rejected.
                task = TaskManager.create_task(command, initial_state=TaskState.Rejected,
                                              data_items=[TextDataItem(text=str(exc))])
                task.senderId = args.agent_id
                return task
            task = TaskManager.create_task(command, initial_state=TaskState.Accepted)
            task.senderId = args.agent_id
            TaskManager.update_task_status(task.taskId, TaskState.Working)
            try:
                output = await execute(payload)
                # A Cancel may have arrived during the awaited HTTP operation.
                # Preserve its terminal state; cancellation cannot undo an already committed side effect.
                if task.status.state in terminal_states:
                    return task
                TaskManager.set_products(task.taskId, [Product(
                    id='product-' + task.taskId, name=payload['action'],
                    dataItems=[StructuredDataItem(data=output)])])
                TaskManager.update_task_status(task.taskId, TaskState.AwaitingCompletion)
            except Exception as exc:
                if task.status.state not in terminal_states:
                    TaskManager.update_task_status(task.taskId, TaskState.Failed,
                                                  [TextDataItem(text=str(exc))])
            return task

        async def complete(command, task):
            result = await DefaultHandlers.complete(command, task)
            result.senderId = args.agent_id
            return result

        # Explicit local-only exception: no Wutong AIC/certificates exist yet.
        add_aip_rpc_router(app, '/rpc', CommandHandlers(
            on_start=start, on_get=guarded(DefaultHandlers.get),
            on_cancel=guarded(DefaultHandlers.cancel), on_complete=guarded(complete),
            on_continue=guarded(DefaultHandlers.continue_)),
                           local_aic=args.agent_id, identity_binding_enabled=False)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--target', default='')
    parser.add_argument('--database', default='')
    parser.add_argument('--agent-id', default='')
    parser.add_argument('--data-dir', default='.')
    options = parser.parse_args()
    uvicorn.run(make_app(options), host='127.0.0.1', port=options.port, log_level='warning')
