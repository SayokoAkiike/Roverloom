# ADR 0011: A tripwire for local evaluation, not a sandbox

Status: Accepted, 2026-11-02.

## Context

The mock evaluator ran agents with normal access to the machine. A real sandbox needs containers or
virtual machines, and this project runs no public service. The evaluator is still useful for testing the
submission format, and for catching accidents and casual cheating.

## Decision

Add a Python audit hook and operating system limits in the agent process, and test them. State plainly that
this is not isolation, and keep a test showing a bypass, so that the claim stays true and visible.

## Consequences

- Refusals and limits can be tested locally on Windows and Linux.
- Someone could still mistake it for protection. The module docstring, CLI output, documents, and the
  bypass test all say otherwise.
- A public competition still needs the design in [evaluator safety](../evaluator-safety.md).
