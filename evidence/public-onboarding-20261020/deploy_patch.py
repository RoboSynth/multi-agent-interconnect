"""Apply this exact tested metadata patch under the existing seven-AIC handoff."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path('/opt/incident-pilot')
UPLOAD = Path('/home/ubuntu/.incident-public-onboarding-20261020')
OUT = ROOT / 'evidence/public-onboarding-20261020'
CONTEXT = UPLOAD / 'context'
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor/ACPs-community/acps-sdk')]


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def command(args, *, timeout=300):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed with exit {result.returncode}')
    return result.stdout


def build():
    if not CONTEXT.exists():
        CONTEXT.mkdir()
        with tarfile.open(UPLOAD / 'patch-source.tar.gz') as archive:
            archive.extractall(CONTEXT, filter='data')
    manifest = json.loads((CONTEXT / 'manifest.json').read_text())
    actual = json.loads(command(['docker', 'image', 'inspect', manifest['base_tag']]))[0]['Id']
    assert actual == manifest['base_image_id'], 'Base image has changed'
    for name, expected in {**manifest['files'], **manifest['tests']}.items():
        assert hashlib.sha256((CONTEXT / name).read_bytes()).hexdigest() == expected
    (CONTEXT / 'Dockerfile').write_text('FROM ' + manifest['base_tag'] + '\n' +
        '\n'.join(f'COPY {name} /srv/{name}' for name in manifest['files']) + '\n')
    log = command(['docker', 'build', '--pull=false', '--network=none', '-t', manifest['patch_tag'],
                   str(CONTEXT)], timeout=300)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'build.log').write_text(log)
    result = subprocess.run(['docker', 'run', '--rm', '--network=none',
        '-v', str(CONTEXT / 'tests') + ':/srv/tests:ro',
        '-v', str(ROOT / 'integration/incident/application.approved.acs.json') + ':/srv/integration/incident/application.approved.acs.json:ro',
        '-v', str(ROOT / 'deploy/fluent-bit') + ':/srv/deploy/fluent-bit:ro', manifest['patch_tag'],
        'python', '-B', '-m', 'unittest', 'discover', '-s', '/srv/tests', '-p', 'test_*.py'],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    (OUT / ('linux-tests-' + str(len(list(OUT.glob('linux-tests-*.txt'))) + 1) + '.txt')).write_text(result.stdout)
    assert result.returncode == 0, 'Linux offline tests failed; inspect saved output'
    check = ('import hashlib,json,pathlib; names=' + repr(list(manifest['files'])) +
             '; print(json.dumps({n:hashlib.sha256((pathlib.Path("/srv")/n).read_bytes()).hexdigest() for n in names}))')
    actual = json.loads(command(['docker', 'run', '--rm', '--network=none', manifest['patch_tag'],
                                 'python', '-B', '-c', check]))
    assert actual == manifest['files'], 'Image does not contain the tested patch'
    identifier = json.loads(command(['docker', 'image', 'inspect', manifest['patch_tag']]))[0]['Id']
    save('build.json', dict(status='built', image_id=identifier, linux_tests_exit_code=0, manifest=manifest))
    print(json.dumps(dict(status='built', image_id=identifier)))


async def activate():
    from ops.aic_lease import experiment_lease
    from deploy.prepare_deployment import load_deployment
    from eval.targets import DockerTarget
    from deploy.verify import verify
    manifest = json.loads((CONTEXT / 'manifest.json').read_text())
    host = json.loads((ROOT / 'runtime/private/cloud-longrun/host.json').read_text())
    state = json.loads((ROOT / 'runtime/private/cloud-longrun/control/host.json').read_text())
    prepared = load_deployment(ROOT / 'runtime/private/cloud-new7-20261019/deployment.json')
    target = DockerTarget.from_file(prepared['target_config'])
    report = dict(status='starting', fault_injections=0, model_calls=0)
    backup = UPLOAD / 'source-backup'
    backup.mkdir(exist_ok=False)
    async with experiment_lease(state['aics'], purpose='public-onboarding-upgrade-20261020',
            control_directory=ROOT / 'runtime/private/cloud-longrun/control',
            directory=ROOT / 'runtime/private/cloud-longrun/leases', timeout=840) as ownership:
        report['lease_id'] = ownership.lease.owner['lease_id']
        # Managed host pause itself proves all six consumers closed and lease released.
        paused = json.loads((ROOT / 'runtime/private/cloud-longrun/control/host.json').read_text())
        assert paused['status'] == 'paused' and paused['consumers_closed'] and paused['lease_released']
        report['pause_receipt'] = {key: paused[key] for key in ('status','consumers_closed','lease_released','session_id')}
        command(['docker', 'tag', manifest['base_image_id'], 'incident-pilot-pre-public-onboarding:20261020'])
        originals = {}
        for name in manifest['files']:
            path = ROOT / name
            originals[name] = path.exists()
            if path.exists():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, saved)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CONTEXT / name, path)
        command(['docker', 'tag', manifest['patch_tag'], manifest['base_tag']])
        h00 = await verify(target.order_url, OUT / 'upgrade-h00')
        report['h00_status'] = h00['status']
        assert h00['status'] == 'passed', 'Business H00 failed; preserve paused state'
        report['status'] = 'activated_resume_requested'
        ownership.mark_cleanup_verified(dict(resource_restored=True, h00_passed=True,
            consumers_closed=True, remote_groups_closed=True,
            evidence='existing managed-host normal close; this upgrade created no group'))
        save('activation.json', report)
    text = await asyncio.to_thread(command, [str(ROOT / '.venv/bin/python'), '-B',
        '/etc/incident-pilot/wait_cloud_workbench.py', '--project-root', str(ROOT),
        '--host-config', str(ROOT / 'runtime/private/cloud-longrun/host.json'), '--execute'])
    report['status'] = 'running'
    report['wait_receipt'] = json.loads(text)
    new_image = json.loads(command(['docker','image','inspect',manifest['patch_tag']]))[0]['Id']
    rows = json.loads(command(['docker', 'inspect', *command(['docker','ps','-q', '--filter',
        'label=com.docker.compose.project='+prepared['project']]).split()]))
    domains = [row for row in rows if row['Config']['Labels'].get('com.docker.compose.service','').endswith('-agent')]
    assert len(domains) == 6 and all(row['Image'] == new_image for row in domains)
    report['domain_image_id'] = new_image
    report['running_domains'] = len(domains)
    save('activation.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action', choices=['build','activate'])
    args=parser.parse_args()
    if args.action == 'build': build()
    else: asyncio.run(activate())
