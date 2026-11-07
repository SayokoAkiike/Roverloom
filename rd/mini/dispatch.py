#!/usr/bin/python3
"""Night dispatcher on the Mac mini: the only program the night SSH key may run.

Installed as ~/RoverloomNight/bin/dispatch.py, read-only, and named as the forced command in
authorized_keys. It reads the requested command from SSH_ORIGINAL_COMMAND (or argv when the owner
runs it directly), accepts a fixed set of verbs with validated arguments, and runs programs from
argument lists, never through a shell. Unreal processes run under sandbox-exec with night.sb, so
the kernel refuses their writes to the owner's clone and other protected paths. It never stops or
signals a process it did not start. Every call is logged to ~/RoverloomNight/logs/dispatch.jsonl.

Python 3.9 compatible: it runs with the system /usr/bin/python3.
"""

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tarfile
import time

HOME = os.path.expanduser("~")
BIN = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BIN, "charter.json")) as _f:
    CHARTER = json.load(_f)
M = CHARTER["mini"]
ROOT = os.path.expanduser(M["root"])
REPO = os.path.join(ROOT, "repo.git")
WORK = os.path.join(ROOT, "work")
PROJECT = os.path.join(WORK, "unreal", "Roverloom.uproject")
EVIDENCE = os.path.join(ROOT, "evidence")
RUN = os.path.join(ROOT, "run")
LOCK = os.path.join(RUN, "unreal.lock")
LOGS = os.path.join(ROOT, "logs")
ENGINE = os.path.expanduser(M["engine"])
EDITOR = os.path.join(ENGINE, "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")
BUILD = os.path.join(ENGINE, "Engine/Build/BatchFiles/Mac/Build.sh")
PROFILE = os.path.join(BIN, "night.sb")
# The dispatcher runs git outside the sandbox; never let the clone's own config start a program.
GIT = ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C"]
# Unreal's message bus binds 0.0.0.0 and joins multicast on every interface. The night needs
# neither, and the sandbox's refused multicast send is logged as an error that fails whichever
# test is running (measured 2026-11-07).
NO_UDP_MESSAGING = "-ini:Engine:[/Script/UdpMessaging.UdpMessagingSettings]:EnableTransport=False"
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
BRANCH = re.compile(r"^rd/[a-z0-9][a-z0-9._-]{0,59}$")
# Set only when the owner runs the dispatcher directly with their own key. A forced command never
# carries it: sshd accepts only LANG and LC_* from clients.
OWNER_OVERRIDE = (
    "SSH_ORIGINAL_COMMAND" not in os.environ and os.environ.get("RD_OWNER_PRESENT_OK") == "1"
)


class Refused(Exception):
    pass


def log(entry):
    os.makedirs(LOGS, exist_ok=True)
    entry["t"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(os.path.join(LOGS, "dispatch.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")


def out(obj):
    sys.stdout.write(json.dumps(obj, indent=1) + "\n")


# ------------------------------------------------------------------ observations
def processes():
    text = subprocess.run(
        ["/bin/ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True
    ).stdout
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            pid, _, cmd = line.partition(" ")
            rows.append((int(pid), cmd))
    return rows


def own_pids():
    pids = {}
    if os.path.isdir(RUN):
        for name in os.listdir(RUN):
            if name.endswith(".pid"):
                with open(os.path.join(RUN, name)) as f:
                    text = f.read().strip()
                if text.isdigit():
                    pids[int(text)] = name[:-4]
    return pids


def unreal_processes():
    """Unreal editor or game processes, by executable path. UnrealEditorServices is a helper."""
    return [
        (p, c)
        for p, c in processes()
        if "/MacOS/UnrealEditor " in c + " " or "UnrealEditor-Cmd" in c
    ]


def foreign_unreal():
    own = own_pids()
    return [(p, c) for p, c in unreal_processes() if p not in own and ROOT not in c]


def memory():
    text = subprocess.run(["/usr/bin/memory_pressure"], capture_output=True, text=True).stdout
    m = re.search(r"System-wide memory free percentage: (\d+)%", text)
    swap = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "vm.swapusage"], capture_output=True, text=True
    ).stdout
    used = re.search(r"used = ([\d.]+)M", swap)
    return {
        "free_pct": int(m.group(1)) if m else None,
        "swap_used_mb": float(used.group(1)) if used else None,
    }


def owner_idle_s():
    text = subprocess.run(
        ["/usr/sbin/ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True
    ).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', text)
    return int(m.group(1)) / 1e9 if m else None


def lock_holder():
    try:
        with open(LOCK) as f:
            return f.read().strip()
    except OSError:
        return None


# ------------------------------------------------------------------ guards
def night_user_forbidden_processes():
    """Processes of the night user whose command line names a forbidden program (charter)."""
    text = subprocess.run(
        ["/bin/ps", "-U", str(os.getuid()), "-ww", "-o", "pid=,command="],
        capture_output=True,
        text=True,
    ).stdout
    names = M.get("forbidden_night_processes", [])
    found = []
    for line in text.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if any(n in cmd for n in names):
            found.append(int(pid))
    return found


def preflight():
    """Refuse an Unreal step if the owner might be affected or memory is short."""
    banned = night_user_forbidden_processes()
    if banned:
        raise Refused(f"isolation: forbidden processes run as the night user: {banned}")
    foreign = foreign_unreal()
    if foreign:
        raise Refused(
            f"busy: an Unreal process the night did not start is running: {[p for p, _ in foreign]}"
        )
    idle = owner_idle_s()
    if idle is not None and idle < M["owner_idle_min_s"] and not OWNER_OVERRIDE:
        raise Refused(f"busy: the owner used the Mac mini {idle:.0f} s ago")
    mem = memory()
    if mem["free_pct"] is not None and mem["free_pct"] < M["min_free_memory_pct"]:
        raise Refused(f"memory: free {mem['free_pct']}% is under {M['min_free_memory_pct']}%")


def acquire(owner):
    os.makedirs(RUN, exist_ok=True)
    holder = lock_holder()
    if holder:
        pid = holder.split(":")[-1]
        alive = pid.isdigit() and any(p == int(pid) for p, _ in processes())
        if alive or not pid.isdigit():
            raise Refused(f"busy: lock held by {holder}")
        os.remove(LOCK)  # Stale: its process is gone.
    fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    os.write(fd, owner.encode())
    os.close(fd)


def release():
    if os.path.exists(LOCK):
        os.remove(LOCK)


def sandboxed(args):
    return ["/usr/bin/sandbox-exec", "-f", PROFILE] + args


def evidence_dir(run_id, create=True):
    if not RUN_ID.match(run_id):
        raise Refused("bad run id")
    path = os.path.join(EVIDENCE, run_id)
    if create:
        if os.path.exists(path):
            raise Refused("run id exists; evidence is never overwritten")
        os.makedirs(os.path.join(path, "shots"))
    elif not os.path.isdir(path):
        raise Refused("no such run")
    return path


# ------------------------------------------------------------------ verbs
def v_status(args):
    if args:
        raise Refused("status takes no arguments")
    head = subprocess.run(
        [*GIT, WORK, "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    out(
        {
            "lock": lock_holder(),
            "own": {str(k): v for k, v in own_pids().items()},
            "foreign_unreal": [p for p, _ in foreign_unreal()],
            "memory": memory(),
            "owner_idle_s": owner_idle_s(),
            "forbidden_processes": night_user_forbidden_processes(),
            "work_head": head,
        }
    )


def v_sync(args):
    if len(args) != 1 or not BRANCH.match(args[0]):
        raise Refused("sync <rd/branch>")
    if lock_holder():
        raise Refused("busy: lock held")
    dirty = subprocess.run(
        [*GIT, WORK, "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    if dirty.strip():
        raise Refused("night worktree has changes; not syncing over them")
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
    ref = "refs/remotes/origin/" + args[0]
    subprocess.run(
        [
            *GIT,
            WORK,
            "fetch",
            "--quiet",
            "origin",
            f"+refs/heads/{args[0]}:{ref}",
        ],
        check=True,
        env=env,
    )
    subprocess.run([*GIT, WORK, "checkout", "--quiet", "--detach", ref], check=True, env=env)
    v_status([])


def run_logged(cmd, logfile, timeout):
    with open(logfile, "w") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return "timeout: " + stop_gracefully(proc.pid, proc)


def v_build(args):
    if len(args) != 1 or not RUN_ID.match(args[0]):
        raise Refused("build <run-id>")
    preflight()
    ev = evidence_dir(args[0])
    acquire(f"build:{os.getpid()}")
    try:
        rc = run_logged(
            sandboxed(
                [
                    BUILD,
                    "RoverloomEditor",
                    "Mac",
                    "Development",
                    "-project=" + PROJECT,
                    "-WaitMutex",
                ]
            ),
            os.path.join(ev, "build.log"),
            M["build_timeout_s"],
        )
    finally:
        release()
    out({"build": rc, "log": os.path.join(ev, "build.log")})


def v_test(args):
    if len(args) != 1:
        raise Refused("test <run-id>")
    preflight()
    ev = evidence_dir(args[0])
    acquire(f"test:{os.getpid()}")
    try:
        rc = run_logged(
            sandboxed(
                [
                    EDITOR,
                    PROJECT,
                    "-nullrhi",
                    NO_UDP_MESSAGING,
                    "-unattended",
                    "-nosplash",
                    "-nosound",
                    "-culture=en",
                    "-ExecCmds=Automation RunTests " + M["automation_filter"],
                    "-TestExit=Automation Test Queue Empty",
                    "-ReportExportPath=" + ev,
                    "-abslog=" + os.path.join(ev, "editor.log"),
                ]
            ),
            os.path.join(ev, "stdout.txt"),
            M["test_timeout_s"],
        )
    finally:
        release()
    out({"test": rc, "report": os.path.join(ev, "index.json")})


def start_own(name, cmd, logfile):
    with open(logfile, "w") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    with open(os.path.join(RUN, name + ".pid"), "w") as f:
        f.write(str(proc.pid))
    return proc


def v_game(args):
    if len(args) != 2 or not args[1].isdigit():
        raise Refused("game <run-id> <seconds>")
    seconds = int(args[1])
    if not M["game_seconds_min"] <= seconds <= M["game_seconds_max"]:
        raise Refused("seconds out of range")
    preflight()
    ev = evidence_dir(args[0])
    acquire(f"game:{os.getpid()}")
    try:
        proc = start_own(
            "game",
            sandboxed(
                [
                    EDITOR,
                    PROJECT,
                    "/Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode",
                    "-game",
                    # No graphical session for the night user: render without a window.
                    "-RenderOffscreen",
                    NO_UDP_MESSAGING,
                    "-ResX=1600",
                    "-ResY=900",
                    "-nosplash",
                    "-abslog=" + os.path.join(ev, "game.log"),
                    "-RoverShotDir=" + os.path.join(ev, "shots"),
                    f"-RoverBench={seconds}",
                ]
            ),
            os.path.join(ev, "stdout.txt"),
        )
        try:
            rc = proc.wait(timeout=seconds + M["game_timeout_extra_s"])
        except subprocess.TimeoutExpired:
            rc = "timeout: " + stop_gracefully(proc.pid, proc)
    finally:
        forget("game")
        release()
    shots = sorted(os.listdir(os.path.join(ev, "shots")))
    out({"game": rc, "shots": shots, "log": os.path.join(ev, "game.log")})


def v_editor_start(args):
    if len(args) != 1:
        raise Refused("editor-start <run-id>")
    preflight()
    ev = evidence_dir(args[0])
    acquire(f"editor:{os.getpid()}")
    proc = start_own(
        "editor",
        sandboxed(
            [
                EDITOR,
                PROJECT,
                "-RenderOffscreen",
                NO_UDP_MESSAGING,
                "-ModelContextProtocolStartServer",
                f"-ModelContextProtocolPort={M['mcp_port']}",
                "-nosplash",
                "-abslog=" + os.path.join(ev, "editor.log"),
            ]
        ),
        os.path.join(ev, "stdout.txt"),
    )
    with open(LOCK, "w") as f:
        f.write(f"editor:{proc.pid}")
    out({"editor_pid": proc.pid, "mcp": f"127.0.0.1:{M['mcp_port']}"})


def stop_gracefully(pid, proc=None):
    """SIGINT, which Unreal's Mac handler turns into a normal exit; then SIGTERM, then SIGKILL.

    Called only for processes the night started: run_logged and start_own children (with their
    Popen, so an exited child is reaped instead of lingering as a zombie), and the PID in
    run/editor.pid after its command line is checked against the night project. macOS answers
    EPERM when a group holds only zombies; that counts as exited, not as an error.
    """

    def alive():
        if proc is not None:
            return proc.poll() is None
        return any(p == pid for p, _ in processes())

    def signal_group(sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return False
        except PermissionError:
            return alive()
        return True

    def wait(seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not alive():
                return True
            time.sleep(1)
        return not alive()

    if not signal_group(signal.SIGINT):
        return "gone"
    if wait(M["graceful_stop_wait_s"]):
        return "exited"
    if signal_group(signal.SIGTERM) and not wait(10):
        signal_group(signal.SIGKILL)
        wait(10)
        return "killed" if not alive() else "still running"
    return "terminated"


def forget(name):
    path = os.path.join(RUN, name + ".pid")
    if os.path.exists(path):
        os.remove(path)


def v_editor_stop_own(args):
    if args:
        raise Refused("editor-stop-own takes no arguments")
    own = {v: k for k, v in own_pids().items()}
    pid = own.get("editor")
    if pid is None:
        raise Refused("no editor started by the night")
    cmd = dict(processes()).get(pid)
    if cmd is not None and PROJECT not in cmd:
        forget("editor")
        raise Refused(f"pid {pid} is not the night's editor; not signaling it")
    result = stop_gracefully(pid) if cmd is not None else "gone"
    forget("editor")
    release()
    out({"editor": result})


def v_fetch_evidence(args):
    if len(args) != 1:
        raise Refused("fetch-evidence <run-id>")
    ev = evidence_dir(args[0], create=False)
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as tar:
        tar.add(ev, arcname=args[0])


def v_git(verb, args, entry):
    if len(args) != 1 or os.path.expanduser(args[0].strip("'")) not in (REPO, REPO + "/"):
        raise Refused("git transport only to the night repository")
    log(dict(entry, result="exec"))  # Only after the path is validated.
    os.execv("/usr/bin/" + verb, [verb, REPO])


VERBS = {
    "status": v_status,
    "sync": v_sync,
    "build": v_build,
    "test": v_test,
    "game": v_game,
    "editor-start": v_editor_start,
    "editor-stop-own": v_editor_stop_own,
    "fetch-evidence": v_fetch_evidence,
}


def main():
    raw = os.environ.get("SSH_ORIGINAL_COMMAND")
    entry = {"raw": raw, "forced": raw is not None}
    try:
        try:
            words = shlex.split(raw) if raw is not None else sys.argv[1:]
        except ValueError as e:
            raise Refused("unparsable command") from e
        if not words:
            raise Refused("no command")
        verb, args = words[0], words[1:]
        entry.update(verb=verb, args=args)
        if verb in ("git-receive-pack", "git-upload-pack"):
            v_git(verb, args, entry)
        if verb not in VERBS:
            raise Refused("unknown verb")
        VERBS[verb](args)
        log(dict(entry, result="ok"))
    except Refused as e:
        log(dict(entry, result="refused", reason=str(e)))
        sys.stderr.write(f"refused: {e}\n")
        sys.exit(2)
    except Exception as e:  # Logged, never retried here.
        log(dict(entry, result="error", reason=repr(e)))
        sys.stderr.write(f"error: {e!r}\n")
        sys.exit(3)


if __name__ == "__main__":
    main()
