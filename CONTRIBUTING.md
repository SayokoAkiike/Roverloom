# Contributing to Roverloom

> Draft. The repository is private and not yet accepting external contributions.
> This guide records the rules we intend to apply when it opens.

## Licensing of contributions

No project license has been selected. External contributions will not be
accepted until a license and contribution terms are published.

## Workflow

1. Open or pick an issue describing the change.
2. Branch from `main` using `feature/<topic>`, `fix/<topic>`, or `docs/<topic>`.
3. Keep pull requests focused. Describe what was tested, including engine version
   and hardware for Unreal changes.
4. CI must pass before merging.

Record significant technical choices in [docs/decisions/](docs/decisions/).

## Local checks

```shell
git lfs install --local
cd python
uv sync
uv run pytest
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run mypy
uv run python ../scripts/check_repo.py
```

## Data contracts

`schemas/` is the boundary between simulators, agents, and evaluation. A change
to a schema must update its tests and scenarios in the same pull request, and
must not introduce fields that only one simulation backend can provide unless
they are optional. See [docs/architecture.md](docs/architecture.md).

## Binary assets and Git LFS

- Binary formats are routed to Git LFS by `.gitattributes`. Check with
  `git check-attr filter -- <path>` when adding a new file type.
- `.uasset` and `.umap` files cannot be merged. Lock before editing:
  `git lfs lock <path>`, and unlock after pushing.
- Storage and bandwidth are limited. Do not commit generated data, large
  experiments, or unused source art.

## What must never be committed

- Unreal Engine source or binaries, or engine content copied into this repository
- Assets without a license that allows redistribution here. Every third-party
  asset must be listed with its source and license; see
  [docs/licensing-review.md](docs/licensing-review.md)
- API keys, tokens, credentials, or `.env` files
- `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`, packaged builds

If a secret is committed, treat it as compromised and revoke it first. Removing
it from history is not enough.

## Honest documentation

Documentation describes what works today. Label anything planned, experimental,
or unverified as such.
