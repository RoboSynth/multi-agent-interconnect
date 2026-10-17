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


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--version")
    parser.add_argument("--terminate", action="store_true")
    args = parser.parse_args()
    result = managed_process(args.pid, script_name=args.script, version=args.version, terminate=args.terminate)
    print(json.dumps({"ProcessId": result["pid"], "running": result["running"]} if result else None))
