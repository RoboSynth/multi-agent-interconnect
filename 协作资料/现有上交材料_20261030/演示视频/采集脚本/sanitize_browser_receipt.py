"""Remove identity metadata from browser receipts without changing outcomes/times."""
import json
from pathlib import Path
import re
import sys

def sanitize(path: Path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    names = set()
    def collect(item):
        if isinstance(item, dict):
            provider = item.get('provider')
            if isinstance(provider, dict):
                for key in ('name', 'email', 'account'):
                    if isinstance(provider.get(key), str):
                        names.add(provider[key])
            for part in item.values():
                collect(part)
        elif isinstance(item, list):
            for part in item:
                collect(part)
    collect(value)
    def clean(item, parent=None):
        if isinstance(item, dict):
            return {k: ('[identity removed]' if parent == 'provider' and isinstance(v, str)
                        else clean(v, k)) for k, v in item.items()}
        if isinstance(item, list):
            return [clean(v, parent) for v in item]
        if isinstance(item, str):
            for name in sorted(names, key=len, reverse=True):
                if name:
                    item = item.replace(name, '[identity removed]')
            return item
        return item
    result = clean(value)
    result['identity_metadata_redacted'] = True
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'file': path.name, 'provider_identity_values_removed': len(names)}

if __name__ == '__main__':
    for name in sys.argv[1:]:
        print(json.dumps(sanitize(Path(name)), ensure_ascii=False))
