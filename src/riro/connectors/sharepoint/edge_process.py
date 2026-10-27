"""Windows side of Edge: find msedge.exe, start it inside a kill-on-close Job Object, kill it (ADR-002).

The profile folder is only passed to Edge on its command line. Nothing inside it is opened, read or listed here.
"""

import contextlib
import ctypes
import os
import subprocess
import threading
from ctypes import wintypes
from pathlib import Path

from riro.connectors.sharepoint.errors import EdgeMissing, EdgeNotStarted

_JOB_EXTENDED_LIMITS = 9
_KILL_ON_JOB_CLOSE = 0x2000
_CREATE_SUSPENDED = 0x4
_PROCESS_ACCESS = 0x0001 | 0x0100 | 0x0800  # terminate, set quota, suspend/resume


def find_edge() -> Path:
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            exe = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if exe.is_file():
                return exe
    raise EdgeMissing()


def build_command(
    exe: Path, profile_dir: Path, port: int, *, headless: bool, url: str
) -> list[str]:
    command = [
        str(exe),
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        command.append("--headless=new")
    command.append(url)
    return command


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _win32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    return kernel32, ntdll


class EdgeProcess:
    """Edge and all its child processes in one Job Object. kill() ends them all at once, without waiting."""

    def __init__(self, popen: subprocess.Popen, job, kernel32):
        self._popen, self._job, self._kernel32 = popen, job, kernel32
        self._lock = threading.Lock()

    def wait(self, timeout_s: float) -> bool:
        """True if Edge exited within timeout_s."""
        try:
            self._popen.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return False
        return True

    def kill(self) -> None:
        """Safe from several threads: the job handle is taken once, so it is closed once."""
        with self._lock:
            job, self._job = self._job, None
        if job:
            self._kernel32.TerminateJobObject(job, 1)
            self._kernel32.CloseHandle(job)
        with contextlib.suppress(OSError):
            self._popen.kill()


def launch_edge(
    exe: Path, profile_dir: Path, port: int, *, headless: bool, url: str
) -> EdgeProcess:
    """Start Edge suspended, put it in a kill-on-close job, then let it run, so no child escapes the job."""
    kernel32, ntdll = _win32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise EdgeNotStarted("Edge could not be started")
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job, _JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        # Without kill-on-close, Edge would outlive a crash of the app and keep the profile in use.
        kernel32.CloseHandle(job)
        raise EdgeNotStarted("Edge could not be started")
    try:
        popen = subprocess.Popen(
            build_command(exe, profile_dir, port, headless=headless, url=url),
            creationflags=_CREATE_SUSPENDED,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        kernel32.CloseHandle(job)
        raise EdgeMissing() from exc
    process = EdgeProcess(popen, job, kernel32)
    handle = kernel32.OpenProcess(_PROCESS_ACCESS, False, popen.pid)
    try:
        if not handle or not kernel32.AssignProcessToJobObject(job, handle):
            process.kill()
            raise EdgeNotStarted("Edge could not be started")
        ntdll.NtResumeProcess(handle)
    finally:
        if handle:
            kernel32.CloseHandle(handle)
    return process
