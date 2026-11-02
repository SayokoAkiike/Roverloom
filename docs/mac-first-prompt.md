# First prompt for Claude Code on the Mac

Do [sections 1 to 4 of the checklist](macos-checklist.md) up to the clone, then start `claude` in the repository, and paste the text below. No earlier conversation is needed.

```text
You are continuing Roverloom on a new Apple M4 Mac. The repository is SayokoAkiike/Roverloom, which is private.
You have no history from earlier sessions, and you do not need any. Documents on GitHub main are the source of truth.
Please report to me in Japanese.

Read in this order: docs/HANDOFF.md, CLAUDE.md, docs/project-status.md, docs/macos-checklist.md, docs/mac-unreal-plan.md,
docs/unreal-contract.md. Run `git fetch` and confirm that the local main matches origin/main.

Nothing has ever run on macOS, and no Unreal code exists. Do not treat anything as working until you have run it here.

Do this now, and only this:
1. Step 1 of docs/mac-unreal-plan.md. Report the Mac's chip, memory, macOS version, and free disk.
2. Confirm that the repository is private, and that the repository-local Git email is the noreply address in the checklist.
3. Run the Python checks in the checklist. Report passed, failed, and skipped counts, compared with 706 passed on Windows.
   Report failures as they are, and do not change Mission Core code to fix them without asking me, since that alters benchmark pins.
4. Record the results in the table in docs/macos-checklist.md.
5. Read Epic's macOS requirements page again, since it may have changed. Tell me which Xcode and Unreal Engine 5.8 hotfix you
   recommend for this macOS version, the sizes the installers report if you can find them, and any risks.

Then stop, and wait for my approval. Do not install Xcode, Unreal Engine, or any other large tool until I approve it in this conversation.

After I approve, follow docs/mac-unreal-plan.md in order, stopping at each line marked Owner. The goal is an Unreal Engine 3D demo in which a
six-wheeled rover drives across realistic Martian terrain, operated by a person and by a Python agent. High visual quality matters.
Adjust the Dev profile to what this Mac can do, but do not lower the final Capture quality without showing me measurements.

Rules that always apply:
- Keep the repository private. No paid services, force pushes, other organizations, or other repositories, unless I say so explicitly.
- Never print tokens or copy credentials. Do not change global Git settings. Commit only with the noreply address.
- Do not commit engine files, build output, Fab content without confirmed rights, raw terrain data, or evaluation scenarios.
- Do not report Unreal MCP or anything else as working unless you ran it. State the engine version and the exact call.
- Models are unvalidated approximations. Do not claim real-rover accuracy, NASA origin of invented rates, or research novelty.
- Do not run code from untrusted people. The local evaluator is not a sandbox.
```
