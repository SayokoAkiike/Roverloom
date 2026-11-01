# 0004: Git LFS for binary assets

Status: Accepted (2026-11-02)

## Context

Unreal assets are large and unmergeable. GitHub Free currently lists 10 GiB of LFS
storage and 10 GiB of monthly bandwidth, and a $0 budget blocks usage instead of
charging when exceeded.

## Decision

- Route binary formats to LFS through `.gitattributes`.
- Mark `.uasset` and `.umap` lockable.
- Ignore generated data, and store raw source art and restricted assets outside Git.
- `scripts/check_repo.py` fails CI for large non-LFS files.

## Consequences

- Lockable files are read-only until locked after `git lfs install`, which adds one step
  but prevents lost work.
- LFS history counts against quota even after files are removed from `main`. Check file
  sizes before committing, and look at alternatives if the project nears the quota.
