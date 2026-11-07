#!/usr/bin/python3
"""Night wrapper on the MacBook Air: the Director's cycles, inside limits this process enforces.

The model is never the stop mechanism. This process holds the lock, the deadline, the counters,
and a watcher thread that ends the current cycle on STOP, time, or memory, by stopping only its
own child process group. Each cycle is one `claude -p` call in the night's worktree, under the Air
sandbox profile and the night settings, hook, agents, MCP config, and JSON schema. Nothing is
pushed: commits stay on the night branch in the night's own clone.

  night.py --check               preflight only: charter, caps, files, STOP, lock; no cycle
  night.py                       a real night; refused until the charter is approved, caps set
  night.py --fake OUTCOMES.json  replay scripted cycles with no model and no SSH, for tests

Python 3.9 compatible.
"""

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))


class Refused(Exception):
    pass


def load_json(path):
    with open(path) as f:
        return json.load(f)


def now_stamp():
    return time.strftime("%Y%m%d-%H%M")


class Night:
    def __init__(self, args):
        self.args = args
        self.charter_path = os.path.join(REPO_ROOT, "rd", "charter.json")
        if args.test_charter:
            if not (args.fake or args.check):
                raise SystemExit("--test-charter is only for fake nights and --check")
            self.charter_path = args.test_charter
        self.charter = load_json(self.charter_path)
        air = self.charter["air"]
        self.limits = self.charter["night"]
        self.state = os.path.expanduser(args.state_dir or air["state_dir"])
        self.night_root = os.path.expanduser(args.night_root or air["night_root"])
        self.stamp = args.stamp or now_stamp()
        self.dir = os.path.join(self.state, "nights", self.stamp)
        self.stop_file = os.path.join(self.state, "STOP")
        self.lock = os.path.join(self.state, "night.lock")
        self.started = time.time()
        self.deadline = self.started + 60 * self.limits["max_minutes"]
        self.child = None
        self.stop_reason = None
        self.cycles = []
        self.failures = {}
        self.builds = 0
        self.launches = 0
        self.cost = 0.0
        self.owner_skips = 0
        self.busy_since = None
        self.unreachable_since = None
        self.fake = load_json(args.fake) if args.fake else None
        self.worktree = None
        self.tunnel = None

    # ------------------------------------------------------------ preflight
    def preflight(self):
        problems = []
        if not self.fake:
            if not self.charter.get("approved_by_owner"):
                problems.append("charter is not approved by the owner")
            if self.limits.get("usd_per_cycle") is None or self.limits.get("usd_per_night") is None:
                problems.append("spending caps are not set in the charter")
            local = os.path.join(self.state, "local.json")
            if not os.path.exists(local):
                problems.append(f"{local} is missing (mini host, user, night key)")
            if shutil.which("claude") is None:
                problems.append("claude is not on PATH")
        if os.path.exists(self.stop_file):
            problems.append(f"STOP file present: {self.stop_file}")
        if os.path.exists(self.lock):
            problems.append(f"another night holds {self.lock}")
        for name in (
            "hook.py",
            "settings.json",
            "agents.json",
            "cycle.schema.json",
            "mcp-night.json",
            "air.sb",
            "cycle-prompt.md",
            "mini.sh",
        ):
            if not os.path.exists(os.path.join(HERE, name)):
                problems.append(f"missing rd/night/{name}")
        if problems:
            raise Refused("; ".join(problems))

    # ------------------------------------------------------------ setup
    def setup(self):
        os.makedirs(self.dir, exist_ok=False)
        fd = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        os.write(fd, f"{os.getpid()} {self.stamp}".encode())
        os.close(fd)
        repo = os.path.join(self.night_root, "repo")
        if not os.path.isdir(repo):
            raise Refused(
                f"night clone {repo} is missing; create it once by hand (rd/night/README.md)"
            )
        self.worktree = os.path.join(self.night_root, "nights", self.stamp)
        branch = f"rd/night-{self.stamp}"
        base = self.charter["air"]["base_ref"]
        if not self.fake:
            self.git(repo, "fetch", "-q", "origin")  # From the owner's local clone; read-only
        self.git(repo, "worktree", "add", "-q", "-b", branch, self.worktree, base)
        with open(os.path.join(HERE, "air.sb")) as f:
            sb = f.read()
        sb = sb.replace("@HOME@", os.path.expanduser("~")).replace("@NIGHT@", self.night_root)
        self.sandbox = os.path.join(self.dir, "air.sb")
        with open(self.sandbox, "w") as f:
            f.write(sb)
        if not self.fake:
            self.open_tunnel()
        self.log(
            f"night {self.stamp} on {branch} from {base}; deadline {time.ctime(self.deadline)}"
        )

    def git(self, cwd, *args):
        subprocess.run(["git", "-C", cwd] + list(args), check=True, capture_output=True, text=True)

    def head(self):
        """The worktree's HEAD, or None outside a repository."""
        done = subprocess.run(
            ["git", "-C", self.worktree or ".", "rev-parse", "HEAD"], capture_output=True, text=True
        )
        return done.stdout.strip() if done.returncode == 0 else None

    def commits_since(self, base):
        if not base:
            return 0
        done = subprocess.run(
            ["git", "-C", self.worktree, "rev-list", "--count", base + "..HEAD"],
            capture_output=True,
            text=True,
        )
        return int(done.stdout.strip() or 0) if done.returncode == 0 else 0

    def open_tunnel(self):
        local = load_json(os.path.join(self.state, "local.json"))
        key = os.path.expanduser(local["night_key"])
        port = self.charter["mini"]["mcp_port"]
        self.tunnel = subprocess.Popen(
            [
                "ssh",
                "-N",
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "ExitOnForwardFailure=yes",
                "-i",
                key,
                "-L",
                f"127.0.0.1:{local['mcp_local_port']}:127.0.0.1:{port}",
                f"{local['mini_user']}@{local['mini_host']}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def log(self, text):
        line = time.strftime("%H:%M:%S ") + text
        with open(os.path.join(self.dir, "night.log"), "a") as f:
            f.write(line + "\n")
        if not self.args.quiet:
            print(line)

    # ------------------------------------------------------------ watcher
    def mini_status(self, cycle_index):
        if self.fake:
            outcome = self.fake[min(cycle_index, len(self.fake) - 1)]
            if outcome.get("mini_unreachable"):
                return None
            return {
                "memory": {"free_pct": outcome.get("free_pct", 70)},
                "foreign_unreal": [],
                "owner_idle_s": outcome.get("owner_idle_s", 99999),
            }
        out = subprocess.run(
            [os.path.join(HERE, "mini.sh"), "status"], capture_output=True, text=True, timeout=60
        )
        return json.loads(out.stdout) if out.returncode == 0 else None

    def watch(self, cycle_index, done):
        interval = self.limits["watcher_interval_s"] if not self.fake else self.args.fake_interval
        while not done.wait(interval):
            reason = self.check_limits(cycle_index)
            if reason:
                self.stop_reason = self.stop_reason or reason
                self.kill_child()
                return

    def check_limits(self, cycle_index):
        if os.path.exists(self.stop_file):
            return "STOP file"
        if time.time() >= self.deadline:
            return f"time cap {self.limits['max_minutes']} min"
        status = self.mini_status(cycle_index)
        now = time.time()
        if status is None:
            self.unreachable_since = self.unreachable_since or now
            if now - self.unreachable_since >= self.limits["mini_unreachable_stop_s"]:
                return f"Mac mini unreachable for {now - self.unreachable_since:.0f} s"
            return None
        self.unreachable_since = None
        idle = status.get("owner_idle_s")
        if idle is not None and idle < self.charter["mini"]["owner_idle_min_s"]:
            self.busy_since = self.busy_since or now
            if now - self.busy_since >= self.limits["owner_busy_stop_s"]:
                return f"owner input on the Mac mini for {now - self.busy_since:.0f} s"
        else:
            self.busy_since = None
        free = status.get("memory", {}).get("free_pct")
        if free is not None and free < self.charter["mini"]["min_free_memory_pct"]:
            return f"memory: Mac mini free {free}%"
        return None

    def kill_child(self):
        if self.child and self.child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.child.pid, signal.SIGTERM)

    # ------------------------------------------------------------ cycles
    def cycle_command(self, index):
        if self.fake:
            outcome = self.fake[index]
            env_probe = "ANTHROPIC_API_KEY" in os.environ
            payload = {
                "structured_output": outcome.get("output"),
                "total_cost_usd": outcome.get("cost", 0.0),
                "is_error": outcome.get("is_error", False),
                "env_has_api_key": env_probe,
            }
            sleep = float(outcome.get("sleep", 0.1))
            exit_code = int(outcome.get("exit", 0))
            code = (
                f"import json,os,sys,time; time.sleep({sleep!r}); p=json.loads(sys.argv[1]); "
                "p['env_has_api_key']='ANTHROPIC_API_KEY' in os.environ; "
                f"print(json.dumps(p)); sys.exit({exit_code})"
            )
            return [sys.executable, "-c", code, json.dumps(payload)]
        with open(os.path.join(HERE, "cycle-prompt.md")) as f:
            template = f.read()
        prompt = template.format(
            cycle=index + 1,
            max_cycles=self.limits["max_cycles"],
            night=self.stamp,
            mini=os.path.join(HERE, "mini.sh"),
            minutes_left=int((self.deadline - time.time()) / 60),
            priorities=", ".join(self.charter["priorities"]["night_domains"])
            + (
                "; this night: " + self.charter["priorities"]["first_night"]
                if self.charter["priorities"].get("first_night")
                else ""
            ),
            history="\n".join(
                f"- c{i + 1}: {c.get('domain')} {c.get('task')}: {c.get('result')}"
                for i, c in enumerate(self.cycles)
            )
            or "- none",
        )
        return [
            "/usr/bin/sandbox-exec",
            "-f",
            self.sandbox,
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--settings",
            os.path.join(HERE, "settings.json"),
            "--agents",
            os.path.join(HERE, "agents.json"),
            "--mcp-config",
            os.path.join(HERE, "mcp-night.json"),
            "--strict-mcp-config",
            "--json-schema",
            open(os.path.join(HERE, "cycle.schema.json")).read(),
            "--max-budget-usd",
            str(self.limits["usd_per_cycle"]),
        ]

    def run_cycle(self, index):
        env = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"
        }  # Never switch billing to an API key
        env.update(
            RD_WORKTREE=self.worktree,
            RD_CHARTER=self.charter_path,
            # The owner's clone, which the Air sandbox keeps read-only: the night cannot edit these.
            RD_HOOK=os.path.join(HERE, "hook.py"),
            RD_MINI=os.path.join(HERE, "mini.sh"),
        )
        out_path = os.path.join(self.dir, f"c{index + 1}.json")
        done = threading.Event()
        watcher = threading.Thread(target=self.watch, args=(index, done), daemon=True)
        with (
            open(out_path, "w") as out,
            open(os.path.join(self.dir, f"c{index + 1}.stderr"), "w") as err,
        ):
            self.child = subprocess.Popen(
                self.cycle_command(index),
                cwd=self.worktree,
                env=env,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            watcher.start()
            timeout = max(1.0, self.deadline - time.time())
            try:
                code = self.child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.stop_reason = self.stop_reason or f"time cap {self.limits['max_minutes']} min"
                self.kill_child()
                code = self.child.wait()
            done.set()
            watcher.join()
        return code, out_path

    def judge(self, code, out_path):
        """Return the cycle's record, or raise Refused to end the night."""
        try:
            envelope = load_json(out_path)
        except (OSError, ValueError):
            envelope = {}
        cycle_cost = float(envelope.get("total_cost_usd") or 0.0)
        self.cost += cycle_cost
        record = envelope.get("structured_output")
        if record is None and isinstance(envelope.get("result"), str):
            try:
                record = json.loads(envelope["result"])
            except ValueError:
                record = None
        required = load_json(os.path.join(HERE, "cycle.schema.json"))["required"]
        if (
            code != 0
            or envelope.get("is_error")
            or not isinstance(record, dict)
            or any(k not in record for k in required)
        ):
            record = {
                "domain": "?",
                "task": "?",
                "result": "failed",
                "builds": 0,
                "unreal_launches": 0,
                "failure_signature": f"cycle: exit {code}, no valid structured output",
            }
        record["env_has_api_key"] = envelope.get("env_has_api_key")
        record["cost_usd"] = round(cycle_cost, 4)
        return record

    def account(self, record):
        self.cycles.append(record)
        self.builds += int(record.get("builds") or 0)
        self.launches += int(record.get("unreal_launches") or 0)
        if record.get("result") == "skipped":
            self.owner_skips += 1
        sig = record.get("failure_signature")
        if record.get("result") == "failed" and sig:
            self.failures[sig] = self.failures.get(sig, 0) + 1
            if self.failures[sig] >= self.limits["same_failure_limit"]:
                return f"same failure {self.failures[sig]} times: {sig}"
        if (
            self.builds > self.limits["max_builds"]
            or self.launches > self.limits["max_unreal_launches"]
        ):
            return "build or Unreal launch cap"
        if self.owner_skips >= self.limits["owner_skips_before_stop"]:
            return "owner present too often"
        cap = self.limits.get("usd_per_night")
        if cap is not None and self.cost >= cap:
            return f"estimated spending {self.cost:.2f} USD reached the night cap"
        return None

    def run(self):
        for index in range(self.limits["max_cycles"]):
            if self.fake and index >= len(self.fake):
                break
            reason = self.stop_reason or self.check_limits(index)
            if reason:
                self.stop_reason = reason
                break
            self.log(f"cycle {index + 1} starts")
            started, base = time.time(), self.head()
            code, out_path = self.run_cycle(index)
            record = self.judge(code, out_path)
            record["minutes"] = round((time.time() - started) / 60, 1)
            record["commits"] = self.commits_since(base)
            self.log(
                f"cycle {index + 1}: {record.get('domain')} {record.get('result')} "
                f"{record.get('failure_signature') or ''}".rstrip()
            )
            reason = self.account(record) or self.stop_reason
            if reason:
                self.stop_reason = reason
                break
        else:
            self.stop_reason = self.stop_reason or f"cycle cap {self.limits['max_cycles']}"
        self.stop_reason = self.stop_reason or "planned cycles done"

    # ------------------------------------------------------------ finish
    def finish(self):
        lines = [
            f"# Night {self.stamp}",
            "",
            f"Stopped by: **{self.stop_reason}**.",
            f"Cycles: {len(self.cycles)}; builds {self.builds}; Unreal launches {self.launches}; "
            f"estimated spending {self.cost:.2f} USD (list-price estimate, not billing).",
            "",
            "| Cycle | Domain | Task | Result | Checks | Evidence | Commits | Minutes | Est. USD "
            "| Failure |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for i, c in enumerate(self.cycles):
            lines.append(
                f"| {i + 1} | {c.get('domain')} | {c.get('task')} | {c.get('result')} "
                f"| {len(c.get('registered_checks') or [])} | {len(c.get('evidence') or [])} "
                f"| {c.get('commits', 0)} | {c.get('minutes', '')} | {c.get('cost_usd', 0):.2f} "
                f"| {c.get('failure_signature') or ''} |"
            )
        lines += [
            "",
            "Raw cycle outputs and the wrapper log are in the night's state folder, outside Git.",
            "Nothing was pushed. Work not verified by a check is not counted as done.",
        ]
        report = "\n".join(lines) + "\n"
        with open(os.path.join(self.dir, "report.md"), "w") as f:
            f.write(report)
        if self.worktree and os.path.isdir(self.worktree):
            target = os.path.join(self.worktree, "rd", "sessions", f"{self.stamp}.md")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as f:
                f.write(report)
            try:
                self.git(self.worktree, "add", target)
                self.git(
                    self.worktree,
                    "commit",
                    "-q",
                    "-m",
                    f"Night {self.stamp} report: {self.stop_reason}",
                )
            except subprocess.CalledProcessError as e:
                self.log(f"report commit failed: {e.stderr.strip()}")
        if self.tunnel and self.tunnel.poll() is None:
            os.killpg(self.tunnel.pid, signal.SIGTERM)
        if os.path.exists(self.lock):
            os.remove(self.lock)
        self.log(f"night ends: {self.stop_reason}")
        return report


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--fake")
    p.add_argument("--fake-interval", type=float, default=0.2)
    p.add_argument(
        "--test-charter", help="fake nights and --check only: a charter copy with test limits"
    )
    p.add_argument("--state-dir")
    p.add_argument("--night-root")
    p.add_argument("--stamp")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    night = Night(args)
    try:
        night.preflight()
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if args.check:
        print("preflight ok")
        return 0
    try:
        night.setup()
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        if os.path.exists(night.lock):
            os.remove(night.lock)
        return 2
    try:
        night.run()
    except Exception as e:  # Any error ends the night; the report is still written.
        night.stop_reason = f"wrapper error: {e!r}"
    finally:
        night.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
