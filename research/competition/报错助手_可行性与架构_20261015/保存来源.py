"""Save the primary sources used in the feasibility study, with content hashes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent / '来源快照'
ROOT.mkdir(exist_ok=True)
EIR_SHA = 'c67ae5c951fbc8b0e0a502b4a7b33141976d6966'
SOURCES = [
    ('Eir_README.md', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/README.md'),
    ('Eir_ARCHITECTURE.md', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/ARCHITECTURE.md'),
    ('Eir_feedback.rs', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/eir-svc/src/feedback/mod.rs'),
    ('Eir_screen_watch.rs', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/eir-ui/src/screen_watch.rs'),
    ('Eir_services.rs', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/eir-svc/src/executor/services/windows.rs'),
    ('Eir_LICENSE', f'https://raw.githubusercontent.com/Swatto86/eir/{EIR_SHA}/LICENSE'),
    ('IntelligentTerminal_README.md', 'https://raw.githubusercontent.com/microsoft/intelligent-terminal/main/README.md'),
    ('IntelligentTerminal_integration.md', 'https://raw.githubusercontent.com/microsoft/intelligent-terminal/main/doc/installing-dependencies.md'),
    ('BrowserTools_README.md', 'https://raw.githubusercontent.com/AgentDeskAI/browser-tools-mcp/main/README.md'),
    ('BrowserTools_LICENSE', 'https://raw.githubusercontent.com/AgentDeskAI/browser-tools-mcp/main/LICENSE'),
    ('NodePTY_README.md', 'https://raw.githubusercontent.com/microsoft/node-pty/main/README.md'),
    ('NodePTY_LICENSE', 'https://raw.githubusercontent.com/microsoft/node-pty/main/LICENSE'),
    ('FlaUI_README.md', 'https://raw.githubusercontent.com/FlaUI/FlaUI/master/README.md'),
    ('FlaUI_LICENSE', 'https://raw.githubusercontent.com/FlaUI/FlaUI/main/LICENSE.txt'),
    ('AISDK_LICENSE', 'https://raw.githubusercontent.com/vercel/ai/main/LICENSE'),
    ('Electron_LICENSE', 'https://raw.githubusercontent.com/electron/electron/main/LICENSE'),
    ('Windows_EventSubscription.html', 'https://learn.microsoft.com/en-us/windows/win32/wes/subscribing-to-events'),
    ('Windows_UIAEvents.html', 'https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-eventsforclients'),
    ('Windows_InteractiveServices.html', 'https://learn.microsoft.com/en-us/windows/win32/services/interactive-services'),
    ('Windows_ConPTY.html', 'https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session'),
    ('DotNet_EventLogWatcher.html', 'https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.eventing.reader.eventlogwatcher?view=windowsdesktop-10.0'),
    ('DotNet_FileSystemWatcher.html', 'https://learn.microsoft.com/en-us/dotnet/api/system.io.filesystemwatcher?view=net-10.0'),
    ('DotNet_SingleFile.html', 'https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview'),
    ('DotNet_WindowsSupport.html', 'https://learn.microsoft.com/en-us/dotnet/core/install/windows'),
    ('Chrome_Debugger.html', 'https://developer.chrome.com/docs/extensions/reference/api/debugger'),
    ('Chrome_NativeMessaging.html', 'https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging'),
    ('Chrome_RemoteDebugging.html', 'https://developer.chrome.com/blog/remote-debugging-port'),
    ('Chrome_WebRequest.html', 'https://developer.chrome.com/docs/extensions/reference/api/webRequest'),
    ('Chrome_Permissions.html', 'https://developer.chrome.com/docs/extensions/reference/api/permissions'),
    ('AISDK_CompatibleProvider.html', 'https://ai-sdk.dev/providers/openai-compatible-providers'),
    ('AISDK_Tools.html', 'https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling'),
    ('Electron_SafeStorage.html', 'https://www.electronjs.org/docs/latest/api/safe-storage'),
    ('Electron_UtilityProcess.html', 'https://www.electronjs.org/docs/latest/api/utility-process'),
    ('Electron_Security.html', 'https://www.electronjs.org/docs/latest/tutorial/security'),
    ('SQLite_FTS5.html', 'https://www.sqlite.org/fts5.html'),
]

def fetch(source):
    filename, url = source
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'ErrorAssistant-Feasibility-Research/1.0'})
        with urllib.request.urlopen(request, timeout=35) as response:
            data = response.read()
            record = {'file': filename, 'url': url, 'final_url': response.url,
                      'status': response.status, 'bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(),
                      'checked_date': '2026-10-15', 'evidence': 'source_text_not_runtime_test'}
        (ROOT / filename).write_bytes(data)
        return record
    except Exception as exc:
        return {'file': filename, 'url': url, 'checked_date': '2026-10-15', 'error': str(exc)}

with ThreadPoolExecutor(max_workers=6) as pool:
    records = list(pool.map(fetch, SOURCES))
(ROOT / '来源索引.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'saved': sum('sha256' in x for x in records), 'total': len(records),
                  'failures': [x for x in records if 'error' in x], 'eir_commit': EIR_SHA}, ensure_ascii=False, indent=2))
