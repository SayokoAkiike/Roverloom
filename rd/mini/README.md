# Night area on the Mac mini

What Stage 0 installed on 2026-11-07, and how to install it again. Settings come from [`../charter.json`](../charter.json).
The design is in [`docs/autonomous-rd-director.md`](../../docs/autonomous-rd-director.md); the test record in
[`docs/results/rd-stage0/README.md`](../../docs/results/rd-stage0/README.md).

## Layout

```text
~/RoverloomNight/
  bin/            dispatch.py, charter.json, night.sb; files 444, directory 555
  repo.git/       bare repository; receives rd/* branches from the Air
  work/           the night clone (its own unreal/Saved, Intermediate, Binaries); LFS not fetched
  evidence/<run>/ build, test, game, and editor logs, shots; never overwritten
  run/            unreal.lock, <name>.pid of processes the night started
  logs/           dispatch.jsonl: every call, allowed or refused
  authorized_keys.before-rdnight   backup taken before the night key was added
```

## Install, with the owner's own key

1. `mkdir -p ~/RoverloomNight/{bin,evidence,run,logs}` and `git init --bare ~/RoverloomNight/repo.git`.
2. From the Air: `git push --no-verify ssh://<mini>/Users/<user>/RoverloomNight/repo.git HEAD:refs/heads/rd/base`.
   `--no-verify` skips the LFS pre-push hook; the night area has no LFS server.
3. `GIT_LFS_SKIP_SMUDGE=1 git clone -b rd/base ~/RoverloomNight/repo.git ~/RoverloomNight/work`.
4. Render `night.sb`: replace `@DENY@` with one `(subpath "...")` per `mini.write_protected` entry of the charter, with
   `~` expanded. Copy `dispatch.py`, `charter.json`, and `night.sb` into `bin/`; `chmod 444` the files and `555` the folder.
5. On the Air: `ssh-keygen -t ed25519 -N "" -C roverloom-rd-night -f ~/.ssh/id_ed25519_rdnight`.
6. Back up `~/.ssh/authorized_keys` on the Mac mini, then append one line:
   `restrict,port-forwarding,permitopen="127.0.0.1:8100",command="/usr/bin/python3 /Users/<user>/RoverloomNight/bin/dispatch.py" <public key>`.

To update `bin/`, the owner makes it writable, copies, and makes it read-only again. The night cannot: its key runs
only the dispatcher, and its Unreal processes are denied writes to `bin/` by the sandbox.

## Remove

Delete the night key's line from `authorized_keys` (or restore the backup), then remove `~/RoverloomNight` and the Air's
`~/.ssh/id_ed25519_rdnight*`. Nothing else was installed.

## Verbs

`status`, `sync <rd/branch>`, `build <run>`, `test <run>`, `game <run> <seconds>`, `editor-start <run>`,
`editor-stop-own`, `fetch-evidence <run>`, and Git transport to `repo.git` only. Run ids match
`^[a-z0-9][a-z0-9-]{0,39}$`. Unreal verbs first check, in order: an Unreal process the night did not start, the owner's
input within `owner_idle_min_s`, and free memory; the check refuses before anything is created.
`RD_OWNER_PRESENT_OK=1` skips only the owner-input check, and only when the owner runs the dispatcher directly; a forced
command never carries it, because sshd accepts only `LANG` and `LC_*` from clients.
