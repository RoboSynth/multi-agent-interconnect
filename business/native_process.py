"""Windows process identity and termination without WMI or PID reuse races."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _libraries():
    if os.name != "nt":
        raise RuntimeError("Windows native process backend required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p,
                                               wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    ntdll.NtQueryInformationProcess.restype = wintypes.LONG
    return kernel, ntdll


def _command_line(ntdll, handle):
    class UnicodeString(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]
    required = wintypes.ULONG()
    ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(required))
    if required.value < ctypes.sizeof(UnicodeString) or required.value > 1024 * 1024:
        raise OSError("Cannot query the registered process command line")
    buffer = ctypes.create_string_buffer(required.value)
    status = ntdll.NtQueryInformationProcess(handle, 60, buffer, required.value, ctypes.byref(required))
    if status != 0:
        raise OSError(f"Cannot query the registered process command line (NTSTATUS {status & 0xffffffff:08x})")
    value = UnicodeString.from_buffer(buffer)
    start = ctypes.addressof(buffer)
    if value.Buffer < start or value.Buffer + value.Length > start + len(buffer):
        raise OSError("Invalid process command line response")
    return ctypes.string_at(value.Buffer, value.Length).decode("utf-16-le")


def managed_process(pid, *, script_name, version=None, terminate=False):
    if type(pid) is not int or pid <= 0:
        raise ValueError("A registered positive process ID is required")
    kernel, ntdll = _libraries()
    rights = 0x1000 | (0x0001 | 0x100000 if terminate else 0)
    handle = kernel.OpenProcess(rights, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return None
        raise OSError(error, "Cannot open the registered experiment process")
    try:
        command = _command_line(ntdll, handle)
        normalized = command.replace("\\", "/").lower()
        expected = (ROOT / "business" / script_name).as_posix().lower()
        if expected not in normalized:
            raise ValueError("Registered PID is not the expected project script")
        if version and f"--version {version}" not in normalized:
            raise ValueError("Registered PID has the wrong app version")
        result = {"pid": pid, "command_line": command, "running": True}
        if terminate:
            if not kernel.TerminateProcess(handle, 1):
                raise OSError(ctypes.get_last_error(), "Could not stop the registered experiment process")
            if kernel.WaitForSingleObject(handle, 5000) != 0:
                raise OSError("Registered experiment process did not stop within 5 seconds")
            result["running"] = False
        return result
    finally:
        kernel.CloseHandle(handle)


def _argv(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values:
        raise OSError(ctypes.get_last_error(), "Cannot parse the registered app command line")
    try:
        return [values[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(values)


def _normalized_path(value):
    return os.path.normcase(str(Path(value).resolve()))


def _app_command(command, version, port):
    values = _argv(command)
    return (len(values) == 6
            and Path(values[1]).is_absolute()
            and _normalized_path(values[1]) == _normalized_path(ROOT / "business/run_app.py")
            and values[2:] == ["--version", version, "--port", str(port)])


def _process_snapshot(kernel):
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "Cannot enumerate app launcher children")
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        rows = []
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            rows.append((entry.th32ProcessID, entry.th32ParentProcessID))
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise OSError(ctypes.get_last_error(), "Cannot enumerate app launcher children")
        return rows
    finally:
        kernel.CloseHandle(snapshot)


def _creation_time(kernel, handle):
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                  ctypes.byref(system), ctypes.byref(user)):
        raise OSError(ctypes.get_last_error(), "Cannot verify the app process creation time")
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def _python_images(python_executable):
    executable = Path(python_executable)
    if not executable.is_absolute():
        raise ValueError("The configured app Python must be an absolute path")
    image = _normalized_path(executable)
    config_path = executable.parent.parent / "pyvenv.cfg"
    if executable.parent.name.lower() != "scripts" and not config_path.exists():
        return None, {image}  # Explicit base interpreter, without a venv shim.
    config = config_path.read_text(encoding="utf-8-sig")
    settings = dict((key.strip(), value.strip()) for line in config.splitlines()
                    for key, separator, value in [line.partition("=")] if separator)
    home = Path(settings["home"])
    if not home.is_absolute():
        raise ValueError("App environment has no absolute base Python home")
    base_name = "pythonw.exe" if executable.name.lower() == "pythonw.exe" else "python.exe"
    return image, {image, _normalized_path(home / base_name)}


def _image_path(kernel, handle):
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
    buffer = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(buffer))
    if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
        raise OSError(ctypes.get_last_error(), "Cannot verify the app process executable")
    return _normalized_path(buffer.value)


def _parent_pid(ntdll, handle):
    class ProcessBasicInformation(ctypes.Structure):
        _fields_ = [("reserved1", ctypes.c_void_p), ("peb", ctypes.c_void_p),
                    ("reserved2", ctypes.c_void_p * 2), ("pid", ctypes.c_size_t),
                    ("parent_pid", ctypes.c_size_t)]
    value = ProcessBasicInformation()
    size = wintypes.ULONG()
    status = ntdll.NtQueryInformationProcess(handle, 0, ctypes.byref(value), ctypes.sizeof(value),
                                             ctypes.byref(size))
    if status != 0:
        raise OSError("Cannot verify the app child's parent on its owned handle")
    return value.parent_pid


def _app_record(kernel, ntdll, pid, version, port, python_executable, terminate):
    rights = 0x1000 | 0x100000 | (0x0001 if terminate else 0)
    handle = kernel.OpenProcess(rights, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise OSError(ctypes.get_last_error(), "Cannot open the app family process")
    try:
        state = kernel.WaitForSingleObject(handle, 0)
        if state == 0:
            kernel.CloseHandle(handle)
            return None
        if state != 0x102:
            raise OSError("Cannot verify whether the app family process is running")
        command = _command_line(ntdll, handle)
        if not _app_command(command, version, port):
            raise ValueError("App family PID is not the exact project script, version and port")
        launcher, allowed = _python_images(python_executable)
        image = _image_path(kernel, handle)
        if image not in allowed:
            raise ValueError("App family PID is not the configured project Python")
        return {"pid": pid, "handle": handle, "created": _creation_time(kernel, handle),
                "launcher": image == launcher, "parent_pid": _parent_pid(ntdll, handle)}
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def managed_app_family(pid, *, version, port, python_executable, terminate=False):
    """Explicit native-stop scope: one registered app and its verified venv child.

    The single-PID managed_process API above deliberately retains its fault-tool
    semantics. Every family handle stays open from identity check through stop.
    """
    if type(pid) is not int or pid <= 0 or version not in {"v1", "v2"}:
        raise ValueError("A registered app PID and exact version are required")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("The configured app port is required")
    if not isinstance(python_executable, (str, Path)) or not Path(python_executable).is_absolute():
        raise ValueError("The configured app Python must be an absolute path")
    kernel, ntdll = _libraries()
    records = []
    try:
        parent = _app_record(kernel, ntdll, pid, version, port, python_executable, terminate)
        if parent:
            records.append(parent)
        for child_pid, parent_pid in _process_snapshot(kernel):
            if parent_pid != pid:
                continue
            try:
                child = _app_record(kernel, ntdll, child_pid, version, port, python_executable, terminate)
            except ValueError:
                continue  # Unrelated children are outside this app's stop scope.
            if not child:
                continue
            records.append(child)
            if child["parent_pid"] != pid:
                raise ValueError("App child no longer belongs to the registered launcher")
            if parent is None:
                raise RuntimeError("Registered launcher is gone but a matching app child remains; preserve its record")
            if child["created"] < parent["created"]:
                raise ValueError("App child predates the registered launcher")
            if child["launcher"]:
                raise ValueError("Unexpected nested app launcher; preserve the registered family")
        if not parent:
            return None
        if parent["launcher"] and len(records) != 2:
            raise RuntimeError("Registered venv launcher must have exactly one verified app child before stopping")
        result = {"pid": pid, "process_ids": [record["pid"] for record in reversed(records)], "running": True}
        if terminate:
            for record in reversed(records):
                state = kernel.WaitForSingleObject(record["handle"], 0)
                if state == 0:
                    continue
                if state != 0x102 or not kernel.TerminateProcess(record["handle"], 1):
                    raise OSError(ctypes.get_last_error(), "Could not stop the verified app family process")
                if kernel.WaitForSingleObject(record["handle"], 5000) != 0:
                    raise OSError("Verified app family process did not stop within 5 seconds")
            result["running"] = False
        return result
    finally:
        for record in records:
            kernel.CloseHandle(record["handle"])


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--version")
    parser.add_argument("--port", type=int)
    parser.add_argument("--python-executable", help="Absolute app interpreter from native-runtime.json")
    parser.add_argument("--app-family", action="store_true",
                        help="Explicit native app stop scope, including its verified venv child")
    parser.add_argument("--terminate", action="store_true")
    args = parser.parse_args()
    if args.app_family:
        if args.script != "run_app.py" or not args.python_executable:
            parser.error("--app-family requires run_app.py and --python-executable")
        result = managed_app_family(args.pid, version=args.version, port=args.port,
                                    python_executable=args.python_executable, terminate=args.terminate)
    else:
        result = managed_process(args.pid, script_name=args.script, version=args.version, terminate=args.terminate)
    output = {"ProcessId": result["pid"], "running": result["running"]} if result else None
    if result and args.app_family:
        output["process_ids"] = result["process_ids"]
    print(json.dumps(output))
