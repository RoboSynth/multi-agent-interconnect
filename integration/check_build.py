"""Reproduce the minimum contest build checks using the official CLI.

Reads public discovery endpoints only. Does not log in, submit drafts, request
certificates, call model APIs, or treat draft metadata as platform connectivity.
"""
from datetime import datetime, timedelta, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    output = ROOT / 'artifacts' / f'contest-build-{stamp}-{uuid.uuid4().hex[:6]}'
    output.mkdir(parents=True)
    cli = Path(sys.executable).parent / ('acps-cli.exe' if os.name == 'nt' else 'acps-cli')
    commands = {
        'strict_acs_schema': [sys.executable, 'integration/validate_acs.py',
                              'integration/acs/application.draft.json', '--require-official-schema'],
        'official_cli_discovery_status': [str(cli), '--config', 'integration/acps-cli.toml', 'discover', 'status'],
        'official_cli_find_our_agent': [str(cli), '--config', 'integration/acps-cli.toml', 'discover', 'query',
                                       '--request-file', 'integration/discovery-application.request.json'],
    }
    results = {}
    for name, command in commands.items():
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding='utf-8', errors='replace', timeout=40,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            result = {'command': command, 'exit_code': process.returncode,
                      'stdout': process.stdout, 'stderr': process.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = {'command': command, 'error': f'{type(exc).__name__}: {exc}', 'exit_code': None}
        results[name] = result
        (output / f'{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    own_query = results['official_cli_find_our_agent']
    try:
        discover = json.loads(own_query.get('stdout', '{}'))
        our_agent_found = bool(discover.get('result', {}).get('acsMap'))
    except ValueError:
        our_agent_found = None
    metadata = {name: importlib.metadata.version(name) for name in ['acps-sdk', 'acps-cli', 'jsonschema', 'cryptography']}
    summary = {'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'environment': metadata,
               'checks': {name: row['exit_code'] == 0 for name, row in results.items()},
               'our_agent_discoverable': our_agent_found,
               'platform_state': 'DRAFT saved; no AIC/certificate; no authenticated platform task yet',
               'paid_model_api_used': False,
               'scope': 'Official code build, strict ACS schema, public platform discovery. Not full contest completion.'}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), **summary}, ensure_ascii=True, indent=2))
    return 0 if all(summary['checks'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
