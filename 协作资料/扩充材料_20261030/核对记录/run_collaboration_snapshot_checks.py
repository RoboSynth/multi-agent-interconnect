"""Run the four existing local suites against the isolated collaboration copy."""
from pathlib import Path
from datetime import datetime, timezone
import contextlib
import importlib
import io
import json
import re
import sys
import time
import unittest

SNAPSHOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
TEST_ROOT = SNAPSHOT / 'tests'
SDK_ROOT = SNAPSHOT / 'vendor/ACPs-community/acps-sdk'
sys.dont_write_bytecode = True
sys.path[:0] = [str(SNAPSHOT), str(SDK_ROOT), str(TEST_ROOT)]

FILES = ['test_onboarding_text.py', 'test_workbench.py',
         'test_wutong_transport.py', 'test_external_rotation.py']

def redact(value):
    value = re.sub(r'1\.2\.156\.3088(?:\.[A-Za-z0-9]+)+', '[AIC]', value)
    value = re.sub(r'(?:\d{1,3}\.){3}\d{1,3}', '[IP]', value)
    value = re.sub('(?i)(C:[\\\\/]+Users[\\\\/]+)[^\\\\/\\r\\n"<>]+', lambda m: m.group(1)+'shared-user', value)
    return value

started = datetime.now(timezone.utc).isoformat()
groups=[]
logs=[]
for filename in FILES:
    stream=io.StringIO()
    before=time.perf_counter()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        module=importlib.import_module(Path(filename).stem)
        assert Path(module.__file__).resolve() == (TEST_ROOT/filename).resolve()
        suite=unittest.defaultTestLoader.loadTestsFromModule(module)
        assert suite.countTestCases() > 0
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    failures=[{'test':test.id(),'detail':redact(detail)} for test,detail in result.failures]
    errors=[{'test':test.id(),'detail':redact(detail)} for test,detail in result.errors]
    groups.append({'test_file':filename,'tests_run':result.testsRun,
                   'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                   'failures':failures,'errors':errors,
                   'skipped':[{'test':test.id(),'reason':reason} for test,reason in result.skipped],
                   'successful':result.wasSuccessful(),
                   'elapsed_seconds':round(time.perf_counter()-before,3)})
    logs.append('FILE '+filename+'\n'+redact(stream.getvalue()))

module_paths={}
for name in ['domains.onboarding.text','domains.onboarding.check','incident.platform_worker',
             'workbench_server','incident.wutong_transport','ops.external_rotation','acps_sdk']:
    loaded=sys.modules.get(name)
    assert loaded is not None, name
    actual=Path(loaded.__file__).resolve()
    assert actual.is_relative_to(SNAPSHOT.resolve()), (name,str(actual))
    module_paths[name]=str(actual.relative_to(SNAPSHOT))

summary={'label':'10月30日协作源码快照检查','date':'2026-10-30',
         'snapshot_root':'.','python_executable':Path(sys.executable).name,
         'python_version':sys.version.split()[0],
         'started_at_utc':started,'finished_at_utc':datetime.now(timezone.utc).isoformat(),
         'test_files':FILES,'groups':groups,'loaded_source_modules':module_paths,
         'totals':{'tests_run':sum(x['tests_run'] for x in groups),
                   'passed':sum(x['passed'] for x in groups),
                   'failures':sum(len(x['failures']) for x in groups),
                   'errors':sum(len(x['errors']) for x in groups),
                   'skipped':sum(len(x['skipped']) for x in groups)},
         'successful':all(x['successful'] for x in groups),
         'execution_scope':'四组现有本地单测；模拟平台发现、群组传输与子进程；工作台使用进程内TestClient',
         'historical_results':'本次结果单列；10月29日146项中143通过3错误、本地4次3成功1启动失败仍按原记录保留'}
(OUTPUT/'协作源码检查.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUTPUT/'协作源码检查_完整日志.txt').write_text('\n\n'.join(logs),encoding='utf-8')

rows=['| 测试文件 | 用例 | 通过 | 失败 | 错误 | 跳过 |',
      '| --- | ---: | ---: | ---: | ---: | ---: |']
for group in groups:
    rows.append('| '+group['test_file']+' | '+' | '.join(str(x) for x in (
        group['tests_run'],group['passed'],len(group['failures']),len(group['errors']),len(group['skipped'])))+' |')
fail_lines=[]
for group in groups:
    for issue in group['failures']+group['errors']:
        last=next((line for line in reversed(issue['detail'].splitlines()) if line.strip()),'')
        fail_lines.append('- `'+issue['test']+'`：'+last)
status='四组共'+str(summary['totals']['tests_run'])+'项，'+str(summary['totals']['passed'])+'项通过。'
markdown='''# 10月30日协作源码快照检查

检查目录：`.`。

使用原开发项目`.venv/Scripts/python.exe`的依赖，运行器通过绝对路径将隔离副本、其SDK和测试目录置于导入路径首位。已核对相关业务模块与SDK均从隔离副本加载。

## 运行前检查

- `test_onboarding_text.py`：使用本地ACS文件、`AsyncMock`发现函数与模拟参与者。
- `test_workbench.py`：使用临时目录、缺失配置文件和进程内`TestClient`，协调运行替换为`AsyncMock`。
- `test_wutong_transport.py`：`AmpRuntime`、发现、发送与邀请由mock替换；操作记录写入临时目录。
- `test_external_rotation.py`：调用外部任务和停用定时器的`subprocess.run`均由mock替换，状态及结果写入临时目录。

## 执行结果

'''+status+'\n\n'+'\n'.join(rows)+'\n\n'+(
'## 失败摘要\n\n'+'\n'.join(fail_lines)+'\n\n' if fail_lines else '')+'''完整输出见`协作源码检查_完整日志.txt`，机器可读结果见`协作源码检查.json`。日志中的身份格式和IP已替换。

## 历史记录

本次只检查上述四组现有单测。10月29日的146项测试中143通过、3错误，以及本地进程4次执行中3成功、1启动失败继续按原记录保留。本次快照检查单独记录。
'''
(OUTPUT/'协作源码检查.md').write_text(markdown,encoding='utf-8')
print(json.dumps({'label':summary['label'],'groups':[{
    'file':x['test_file'],'run':x['tests_run'],'passed':x['passed'],
    'failures':len(x['failures']),'errors':len(x['errors'])} for x in groups],
    'totals':summary['totals'],'successful':summary['successful']},ensure_ascii=False))
raise SystemExit(0 if summary['successful'] else 1)
