# 安装与指定离线检查日志
固定提交 `659b4b5`；原始日志留在本机。以下仅替换本机目录前缀，保留安装输出、测试结果和警告。

## install-project-requirements.stdout.log

```text
Collecting aio-pika==10.1.1 (from -r <CHECKOUT>\requirements-lock.txt (line 1))
  Downloading aio_pika-10.1.1-py3-none-any.whl.metadata (15 kB)
Collecting aiormq==7.2.2 (from -r <CHECKOUT>\requirements-lock.txt (line 2))
  Downloading aiormq-7.2.2-py3-none-any.whl.metadata (26 kB)
Collecting annotated-doc==0.0.5 (from -r <CHECKOUT>\requirements-lock.txt (line 3))
  Downloading annotated_doc-0.0.5-py3-none-any.whl.metadata (6.5 kB)
Collecting annotated-types==0.8.0 (from -r <CHECKOUT>\requirements-lock.txt (line 4))
  Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
Collecting anyio==4.15.1 (from -r <CHECKOUT>\requirements-lock.txt (line 5))
  Downloading anyio-4.15.1-py3-none-any.whl.metadata (4.7 kB)
Collecting certifi==2026.7.22 (from -r <CHECKOUT>\requirements-lock.txt (line 6))
  Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
Collecting click==8.5.0 (from -r <CHECKOUT>\requirements-lock.txt (line 7))
  Downloading click-8.5.0-py3-none-any.whl.metadata (2.6 kB)
Collecting fastapi==0.143.3 (from -r <CHECKOUT>\requirements-lock.txt (line 8))
  Downloading fastapi-0.143.3-py3-none-any.whl.metadata (26 kB)
Collecting h11==0.16.0 (from -r <CHECKOUT>\requirements-lock.txt (line 9))
  Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Collecting httpcore==1.0.9 (from -r <CHECKOUT>\requirements-lock.txt (line 10))
  Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
Collecting httpx==0.28.1 (from -r <CHECKOUT>\requirements-lock.txt (line 11))
  Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
Collecting idna==3.20 (from -r <CHECKOUT>\requirements-lock.txt (line 12))
  Downloading idna-3.20-py3-none-any.whl.metadata (7.2 kB)
Collecting multidict==7.1.0 (from -r <CHECKOUT>\requirements-lock.txt (line 13))
  Downloading multidict-7.1.0-cp312-cp312-win_amd64.whl.metadata (6.4 kB)
Collecting opentelemetry-api==1.45.1 (from -r <CHECKOUT>\requirements-lock.txt (line 14))
  Downloading opentelemetry_api-1.45.1-py3-none-any.whl.metadata (1.4 kB)
Collecting pamqp==4.0.1 (from -r <CHECKOUT>\requirements-lock.txt (line 15))
  Downloading pamqp-4.0.1-py3-none-any.whl.metadata (3.0 kB)
Collecting propcache==0.5.4 (from -r <CHECKOUT>\requirements-lock.txt (line 16))
  Downloading propcache-0.5.4-cp312-cp312-win_amd64.whl.metadata (25 kB)
Collecting pydantic==2.14.1 (from -r <CHECKOUT>\requirements-lock.txt (line 17))
  Downloading pydantic-2.14.1-py3-none-any.whl.metadata (133 kB)
Collecting pydantic_core==2.50.1 (from -r <CHECKOUT>\requirements-lock.txt (line 18))
  Downloading pydantic_core-2.50.1-cp312-cp312-win_amd64.whl.metadata (6.7 kB)
Collecting starlette==1.8.0 (from -r <CHECKOUT>\requirements-lock.txt (line 19))
  Downloading starlette-1.8.0-py3-none-any.whl.metadata (6.6 kB)
Collecting typing-inspection==0.4.4 (from -r <CHECKOUT>\requirements-lock.txt (line 20))
  Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
Collecting typing_extensions==4.16.0 (from -r <CHECKOUT>\requirements-lock.txt (line 21))
  Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Collecting uvicorn==0.54.0 (from -r <CHECKOUT>\requirements-lock.txt (line 22))
  Downloading uvicorn-0.54.0-py3-none-any.whl.metadata (6.6 kB)
Collecting yarl==1.25.1 (from -r <CHECKOUT>\requirements-lock.txt (line 23))
  Downloading yarl-1.25.1-cp312-cp312-win_amd64.whl.metadata (115 kB)
Collecting mcp==1.30.0 (from -r requirements-high-score.txt (line 3))
  Downloading mcp-1.30.0-py3-none-any.whl.metadata (9.3 kB)
Collecting PyYAML==6.0.3 (from -r requirements-high-score.txt (line 4))
  Downloading pyyaml-6.0.3-cp312-cp312-win_amd64.whl.metadata (2.4 kB)
Collecting asyncpg==0.32.0 (from -r requirements-high-score.txt (line 5))
  Downloading asyncpg-0.32.0-cp312-cp312-win_amd64.whl.metadata (4.5 kB)
Collecting jsonschema==4.26.0 (from -r requirements-high-score.txt (line 6))
  Downloading jsonschema-4.26.0-py3-none-any.whl.metadata (7.6 kB)
Collecting httpx-sse>=0.4 (from mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading httpx_sse-0.4.3-py3-none-any.whl.metadata (9.7 kB)
Collecting pydantic-settings>=2.5.2 (from mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading pydantic_settings-2.16.0-py3-none-any.whl.metadata (4.0 kB)
Collecting pyjwt>=2.10.1 (from pyjwt[crypto]>=2.10.1->mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading pyjwt-2.15.1-py3-none-any.whl.metadata (3.5 kB)
Collecting python-multipart>=0.0.9 (from mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading python_multipart-0.0.32-py3-none-any.whl.metadata (2.1 kB)
Collecting pywin32>=310 (from mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading pywin32-312-cp312-cp312-win_amd64.whl.metadata (11 kB)
Collecting sse-starlette>=1.6.1 (from mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading sse_starlette-3.5.0-py3-none-any.whl.metadata (15 kB)
Collecting attrs>=22.2.0 (from jsonschema==4.26.0->-r requirements-high-score.txt (line 6))
  Downloading attrs-26.1.0-py3-none-any.whl.metadata (8.8 kB)
Collecting jsonschema-specifications>=2023.03.6 (from jsonschema==4.26.0->-r requirements-high-score.txt (line 6))
  Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl.metadata (2.9 kB)
Collecting referencing>=0.28.4 (from jsonschema==4.26.0->-r requirements-high-score.txt (line 6))
  Downloading referencing-0.37.0-py3-none-any.whl.metadata (2.8 kB)
Collecting rpds-py>=0.25.0 (from jsonschema==4.26.0->-r requirements-high-score.txt (line 6))
  Downloading rpds_py-2026.9.1-cp312-cp312-win_amd64.whl.metadata (4.2 kB)
Collecting python-dotenv>=1.2.2 (from pydantic-settings>=2.5.2->mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading python_dotenv-1.2.4-py3-none-any.whl.metadata (29 kB)
Collecting cryptography>=3.4.0 (from pyjwt[crypto]>=2.10.1->mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading cryptography-50.0.2-cp311-abi3-win_amd64.whl.metadata (4.4 kB)
Collecting cffi>=2.0.0 (from cryptography>=3.4.0->pyjwt[crypto]>=2.10.1->mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading cffi-2.1.1-cp312-cp312-win_amd64.whl.metadata (2.6 kB)
Collecting pycparser (from cffi>=2.0.0->cryptography>=3.4.0->pyjwt[crypto]>=2.10.1->mcp==1.30.0->-r requirements-high-score.txt (line 3))
  Downloading pycparser-3.11-py3-none-any.whl.metadata (8.2 kB)
Downloading aio_pika-10.1.1-py3-none-any.whl (59 kB)
Downloading aiormq-7.2.2-py3-none-any.whl (39 kB)
Downloading annotated_doc-0.0.5-py3-none-any.whl (5.3 kB)
Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
Downloading anyio-4.15.1-py3-none-any.whl (132 kB)
Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
Downloading click-8.5.0-py3-none-any.whl (125 kB)
Downloading fastapi-0.143.3-py3-none-any.whl (144 kB)
Downloading h11-0.16.0-py3-none-any.whl (37 kB)
Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
Downloading idna-3.20-py3-none-any.whl (69 kB)
Downloading multidict-7.1.0-cp312-cp312-win_amd64.whl (93 kB)
Downloading opentelemetry_api-1.45.1-py3-none-any.whl (60 kB)
Downloading pamqp-4.0.1-py3-none-any.whl (32 kB)
Downloading propcache-0.5.4-cp312-cp312-win_amd64.whl (46 kB)
Downloading pydantic-2.14.1-py3-none-any.whl (488 kB)
Downloading pydantic_core-2.50.1-cp312-cp312-win_amd64.whl (2.2 MB)
   ---------------------------------------- 2.2/2.2 MB 379.7 kB/s eta 0:00:00
Downloading starlette-1.8.0-py3-none-any.whl (79 kB)
Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Downloading uvicorn-0.54.0-py3-none-any.whl (87 kB)
Downloading yarl-1.25.1-cp312-cp312-win_amd64.whl (102 kB)
Downloading mcp-1.30.0-py3-none-any.whl (234 kB)
Downloading pyyaml-6.0.3-cp312-cp312-win_amd64.whl (154 kB)
Downloading asyncpg-0.32.0-cp312-cp312-win_amd64.whl (626 kB)
   -------------------------------------- 626.8/626.8 kB 597.7 kB/s eta 0:00:00
Downloading jsonschema-4.26.0-py3-none-any.whl (90 kB)
Downloading attrs-26.1.0-py3-none-any.whl (67 kB)
Downloading httpx_sse-0.4.3-py3-none-any.whl (9.0 kB)
Downloading jsonschema_specifications-2025.9.1-py3-none-any.whl (18 kB)
Downloading pydantic_settings-2.16.0-py3-none-any.whl (80 kB)
Downloading pyjwt-2.15.1-py3-none-any.whl (33 kB)
Downloading python_multipart-0.0.32-py3-none-any.whl (30 kB)
Downloading pywin32-312-cp312-cp312-win_amd64.whl (6.9 MB)
   ---------------------------------------- 6.9/6.9 MB 774.1 kB/s eta 0:00:00
Downloading referencing-0.37.0-py3-none-any.whl (26 kB)
Downloading rpds_py-2026.9.1-cp312-cp312-win_amd64.whl (222 kB)
Downloading sse_starlette-3.5.0-py3-none-any.whl (17 kB)
Downloading cryptography-50.0.2-cp311-abi3-win_amd64.whl (3.8 MB)
   ---------------------------------------- 3.8/3.8 MB 1.3 MB/s eta 0:00:00
Downloading python_dotenv-1.2.4-py3-none-any.whl (23 kB)
Downloading cffi-2.1.1-cp312-cp312-win_amd64.whl (185 kB)
Downloading pycparser-3.11-py3-none-any.whl (51 kB)
Installing collected packages: typing_extensions, rpds-py, PyYAML, pywin32, python-multipart, python-dotenv, pyjwt, pycparser, propcache, pamqp, multidict, idna, httpx-sse, h11, click, certifi, attrs, asyncpg, annotated-types, annotated-doc, yarl, uvicorn, typing-inspection, referencing, pydantic_core, opentelemetry-api, httpcore, cffi, anyio, starlette, pydantic, jsonschema-specifications, httpx, cryptography, aiormq, sse-starlette, pydantic-settings, jsonschema, fastapi, aio-pika, mcp
Successfully installed PyYAML-6.0.3 aio-pika-10.1.1 aiormq-7.2.2 annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.15.1 asyncpg-0.32.0 attrs-26.1.0 certifi-2026.7.22 cffi-2.1.1 click-8.5.0 cryptography-50.0.2 fastapi-0.143.3 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 httpx-sse-0.4.3 idna-3.20 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 mcp-1.30.0 multidict-7.1.0 opentelemetry-api-1.45.1 pamqp-4.0.1 propcache-0.5.4 pycparser-3.11 pydantic-2.14.1 pydantic-settings-2.16.0 pydantic_core-2.50.1 pyjwt-2.15.1 python-dotenv-1.2.4 python-multipart-0.0.32 pywin32-312 referencing-0.37.0 rpds-py-2026.9.1 sse-starlette-3.5.0 starlette-1.8.0 typing-inspection-0.4.4 typing_extensions-4.16.0 uvicorn-0.54.0 yarl-1.25.1
```

## install-sdk-amp-sign.stdout.log

```text
Processing <CHECKOUT>\vendor\acps-community\acps-sdk
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
Requirement already satisfied: aio-pika>=9.0.0 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (10.1.1)
Requirement already satisfied: fastapi>=0.100.0 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (0.143.3)
Requirement already satisfied: httpx>=0.24.0 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (0.28.1)
Requirement already satisfied: pydantic>=2.0.0 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (2.14.1)
Requirement already satisfied: uvicorn>=0.30.0 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (0.54.0)
Requirement already satisfied: cryptography>=48.0.1 in <CHECKOUT>\.venv\lib\site-packages (from acps-sdk==2.2.0) (50.0.2)
Collecting jcs>=0.2.0 (from acps-sdk==2.2.0)
  Downloading jcs-0.2.1-py3-none-any.whl.metadata (1.4 kB)
Requirement already satisfied: aiormq<8,>=7.1.3 in <CHECKOUT>\.venv\lib\site-packages (from aio-pika>=9.0.0->acps-sdk==2.2.0) (7.2.2)
Requirement already satisfied: yarl in <CHECKOUT>\.venv\lib\site-packages (from aio-pika>=9.0.0->acps-sdk==2.2.0) (1.25.1)
Requirement already satisfied: cffi>=2.0.0 in <CHECKOUT>\.venv\lib\site-packages (from cryptography>=48.0.1->acps-sdk==2.2.0) (2.1.1)
Requirement already satisfied: starlette>=0.46.0 in <CHECKOUT>\.venv\lib\site-packages (from fastapi>=0.100.0->acps-sdk==2.2.0) (1.8.0)
Requirement already satisfied: typing-extensions>=4.8.0 in <CHECKOUT>\.venv\lib\site-packages (from fastapi>=0.100.0->acps-sdk==2.2.0) (4.16.0)
Requirement already satisfied: typing-inspection>=0.4.2 in <CHECKOUT>\.venv\lib\site-packages (from fastapi>=0.100.0->acps-sdk==2.2.0) (0.4.4)
Requirement already satisfied: annotated-doc>=0.0.2 in <CHECKOUT>\.venv\lib\site-packages (from fastapi>=0.100.0->acps-sdk==2.2.0) (0.0.5)
Requirement already satisfied: opentelemetry-api>=1.44.0 in <CHECKOUT>\.venv\lib\site-packages (from fastapi>=0.100.0->acps-sdk==2.2.0) (1.45.1)
Requirement already satisfied: anyio in <CHECKOUT>\.venv\lib\site-packages (from httpx>=0.24.0->acps-sdk==2.2.0) (4.15.1)
Requirement already satisfied: certifi in <CHECKOUT>\.venv\lib\site-packages (from httpx>=0.24.0->acps-sdk==2.2.0) (2026.7.22)
Requirement already satisfied: httpcore==1.* in <CHECKOUT>\.venv\lib\site-packages (from httpx>=0.24.0->acps-sdk==2.2.0) (1.0.9)
Requirement already satisfied: idna in <CHECKOUT>\.venv\lib\site-packages (from httpx>=0.24.0->acps-sdk==2.2.0) (3.20)
Requirement already satisfied: h11>=0.16 in <CHECKOUT>\.venv\lib\site-packages (from httpcore==1.*->httpx>=0.24.0->acps-sdk==2.2.0) (0.16.0)
Requirement already satisfied: annotated-types>=0.6.0 in <CHECKOUT>\.venv\lib\site-packages (from pydantic>=2.0.0->acps-sdk==2.2.0) (0.8.0)
Requirement already satisfied: pydantic-core==2.50.1 in <CHECKOUT>\.venv\lib\site-packages (from pydantic>=2.0.0->acps-sdk==2.2.0) (2.50.1)
Requirement already satisfied: click>=7.0 in <CHECKOUT>\.venv\lib\site-packages (from uvicorn>=0.30.0->acps-sdk==2.2.0) (8.5.0)
Requirement already satisfied: pamqp<5,>=4 in <CHECKOUT>\.venv\lib\site-packages (from aiormq<8,>=7.1.3->aio-pika>=9.0.0->acps-sdk==2.2.0) (4.0.1)
Requirement already satisfied: pycparser in <CHECKOUT>\.venv\lib\site-packages (from cffi>=2.0.0->cryptography>=48.0.1->acps-sdk==2.2.0) (3.11)
Requirement already satisfied: multidict>=4.0 in <CHECKOUT>\.venv\lib\site-packages (from yarl->aio-pika>=9.0.0->acps-sdk==2.2.0) (7.1.0)
Requirement already satisfied: propcache>=0.2.1 in <CHECKOUT>\.venv\lib\site-packages (from yarl->aio-pika>=9.0.0->acps-sdk==2.2.0) (0.5.4)
Downloading jcs-0.2.1-py3-none-any.whl (7.6 kB)
Building wheels for collected packages: acps-sdk
  Building wheel for acps-sdk (pyproject.toml): started
  Building wheel for acps-sdk (pyproject.toml): finished with status 'done'
  Created wheel for acps-sdk: filename=acps_sdk-2.2.0-py3-none-any.whl size=198929 sha256=b0bd4fb6d6c49cca855dfc7135e34d55e8cf033f98de78cc9a64b58e3b6e9fd1
  Stored in directory: <PROJECT>\artifacts\clean-checkout-preparation-20261018\.cache\pip\wheels\12\cf\be\9887528fa8c245ba6e67f807b98c0244881fe64e16dfe0dc78
Successfully built acps-sdk
Installing collected packages: jcs, acps-sdk
Successfully installed acps-sdk-2.2.0 jcs-0.2.1
```

## pip-check.stdout.log

```text
No broken requirements found.
```

## test-native_preparation.stderr.log

```text
.........
----------------------------------------------------------------------
Ran 9 tests in 0.418s

OK
```

## test-workbench_model_config.stderr.log

```text
<CHECKOUT>\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
.........
----------------------------------------------------------------------
Ran 9 tests in 0.644s

OK
```

## test-platform_smoke.stderr.log

```text
.....
----------------------------------------------------------------------
Ran 5 tests in 0.301s

OK
```

## test-platform_smoke.stdout.log

```text
{"started_at": "2026-10-18T09:47:24.518477+00:00", "mode": "wutong-amqps", "scope": ["application"], "full_p0_acceptance": false, "fault_injection": false, "status": "failed", "participants": [{"role": "application"}], "tools": ["application.status"], "observation": {"status": "ok", "facts": [{"key": "application_reachable", "value": true}]}, "task_phase_status": "completed", "close_error_class": "OSError", "close_status": "failed", "finished_at": "2026-10-18T09:47:24.527989+00:00"}
{"status": "failed", "error_class": "ValueError"}
{"started_at": "2026-10-18T09:47:24.658782+00:00", "mode": "wutong-amqps", "scope": ["application"], "full_p0_acceptance": false, "fault_injection": false, "status": "failed", "participants": [{"role": "application"}], "tools": ["application.status"], "error_class": "ValueError", "error_stack": [{"file": "eval\\platform_smoke.py", "line": 90, "function": "run"}, {"file": "mock.py", "line": 2291, "function": "_execute_mock_call"}], "task_phase_status": "failed", "close_error_class": "OSError", "close_status": "failed", "finished_at": "2026-10-18T09:47:24.663810+00:00"}
{"started_at": "2026-10-18T09:47:24.717724+00:00", "mode": "wutong-amqps", "scope": ["application"], "full_p0_acceptance": false, "fault_injection": false, "status": "completed", "participants": [{"role": "application"}], "tools": ["application.status"], "observation": {"status": "ok", "facts": [{"key": "application_reachable", "value": true}]}, "task_phase_status": "completed", "close_status": "completed", "finished_at": "2026-10-18T09:47:24.721726+00:00"}
```
