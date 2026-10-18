"""Download official portable Windows runtimes into this project only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tools/runtime"
SOURCES = {
    "postgresql-16.15.zip": "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260623",
    "nginx-1.30.6.zip": "https://nginx.org/download/nginx-1.30.6.zip",
}
REQUIRED = {
    "postgresql-16.15.zip": {"pgsql/bin/" + name for name in
        ("postgres.exe", "pg_ctl.exe", "initdb.exe", "psql.exe", "pg_isready.exe")},
    "nginx-1.30.6.zip": {"nginx-1.30.6/nginx.exe"},
}


def install(item):
    name, url = item
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / name
    candidate = archive
    if not archive.exists():
        temporary = archive.with_name(name + "." + uuid.uuid4().hex + ".download")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        candidate = temporary
    try:
        with zipfile.ZipFile(candidate) as package:
            damaged = package.testzip()
            if damaged:
                raise ValueError("archive member failed its CRC check")
            entries = {member.filename for member in package.infolist()
                       if not member.is_dir() and member.file_size > 0}
            if not REQUIRED[name].issubset(entries):
                raise ValueError("archive is missing required runtime executables")
            # Extract executable/share/lib files, never pgAdmin/doc resources.
            selected = [m for m in package.infolist() if name.startswith("nginx") or
                        m.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/"))]
            for member in selected:
                path = (DEST / member.filename).resolve()
                if not path.is_relative_to(DEST.resolve()):
                    raise ValueError("archive path escapes runtime directory")
    except (zipfile.BadZipFile, ValueError, OSError, EOFError) as error:
        raise RuntimeError(f"Runtime archive validation failed; preserved {candidate.name}. "
                           "Inspect or move it explicitly before retrying.") from error
    if candidate != archive:
        candidate.replace(archive)
    with zipfile.ZipFile(archive) as package:
        for member in selected:
            package.extract(member, DEST)
    return {"archive": str(archive), "source": url, "bytes": archive.stat().st_size,
            "extracted_members": len(selected)}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(install, SOURCES.items()))
    (DEST / "sources.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results))
