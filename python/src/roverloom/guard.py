"""Limits for an agent process in the local mock evaluator. A tripwire, NOT a sandbox.

Python's documentation states that audit hooks are not suitable for containing malicious code. Code
using ctypes, native extensions, or interpreter tricks can get past this guard. It exists to catch
mistakes and casual cheating in local tests, and to make limits easy to test. It must never be the
reason to run code from someone you do not trust. See docs/evaluator-safety.md.
"""

import os
import sys
from pathlib import Path

GUARD_ROOT_VARIABLE = "ROVERLOOM_SUBMISSION_ROOT"
MAX_MEMORY_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_CPU_S = 600
_FORBIDDEN_MODULES = ("ctypes", "_ctypes", "multiprocessing")
_BLOCKED_EVENTS = (
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.spawn",
    "os.startfile",
    "socket.bind",
    "socket.gethostbyname",
)


class GuardViolation(RuntimeError):
    """Raised inside an agent process when it attempts something the guard refuses."""


def _allowed_read_roots(root: Path) -> list[Path]:
    # The agent's own files, and the Python installation it runs on. Nothing else.
    roots = [root]
    for entry in {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix, *sys.path}:
        if entry:
            roots.append(Path(entry).resolve())
    return roots


def _within(path: Path, roots: list[Path]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


def _address_space_limit() -> int:
    if sys.platform != "darwin":
        return MAX_MEMORY_BYTES
    # macOS maps hundreds of GiB per process before any Python runs, and refuses a limit below that.
    import subprocess

    command = ["/bin/ps", "-o", "vsz=", "-p", str(os.getpid())]
    return int(subprocess.check_output(command)) * 1024 + MAX_MEMORY_BYTES


def apply_resource_limits() -> str:
    """Limit memory, CPU, and file size. Returns which mechanism applied on this platform."""
    if sys.platform == "win32":
        return _limit_windows_job()
    else:
        import resource

        for limit, value in (
            (resource.RLIMIT_AS, _address_space_limit()),
            (resource.RLIMIT_CPU, MAX_CPU_S),
            (resource.RLIMIT_FSIZE, MAX_FILE_BYTES),
            (resource.RLIMIT_CORE, 0),
        ):
            resource.setrlimit(limit, (value, value))
        return "rlimit"


if sys.platform == "win32":

    def _limit_windows_job() -> str:
        """Put this process in a Job Object with a memory cap, using only the standard library."""
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
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

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob")]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("Basic", Basic),
                ("Io", Counters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        job = kernel.CreateJobObjectW(None, None)
        info = Extended()
        process_memory_limit, kill_on_close, active_process_limit = 0x100, 0x2000, 0x8
        info.Basic.LimitFlags = process_memory_limit | kill_on_close | active_process_limit
        info.Basic.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = MAX_MEMORY_BYTES
        extended_limit_information = 9
        if not kernel.SetInformationJobObject(
            job, extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)
        ) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise OSError(ctypes.get_last_error(), "could not apply the Windows job limit")
        return "job_object"


def install_guard(port: int) -> None:
    """Apply limits, then refuse forbidden actions in this process for the rest of its life."""
    from roverloom.contract import _validators

    root = Path(os.environ.get(GUARD_ROOT_VARIABLE, os.getcwd())).resolve()
    apply_resource_limits()
    _validators()  # Load the schemas now, because the repository is out of reach afterward.
    read_roots = _allowed_read_roots(root)
    write_root = root
    # This process connects only to the simulator that started it.
    allowed_address = ("127.0.0.1", port)

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event == "open":
            target, mode = args[0], args[1]
            if not isinstance(target, str | bytes | os.PathLike):
                return
            path = Path(os.fsdecode(target)).resolve()
            writing = isinstance(mode, str) and any(c in mode for c in "wax+")
            if writing and not path.is_relative_to(write_root):
                raise GuardViolation(f"writing outside the submission: {path.name}")
            if not writing and not _within(path, read_roots):
                raise GuardViolation(f"reading outside the submission: {path.name}")
        elif event == "socket.connect":
            if args[1] != allowed_address:
                raise GuardViolation("network connection refused")
        elif event == "socket.getaddrinfo":
            if args[:2] != allowed_address:
                raise GuardViolation("network lookup refused")
        elif event == "import":
            if args[0] in _FORBIDDEN_MODULES:
                raise GuardViolation(f"module not allowed: {args[0]}")
        elif event in _BLOCKED_EVENTS:
            raise GuardViolation(f"not allowed: {event}")

    # Keeping a module out of reach beats refusing it after a copy is already loaded.
    for name in _FORBIDDEN_MODULES:
        sys.modules.pop(name, None)
    sys.addaudithook(hook)
