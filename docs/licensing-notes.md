# Licensing notes for a future open source release

These are engineering notes, not legal advice. Epic's EULA pages could not be read
directly with the automated tools used on 2026-11-02 (HTTP 403), so items below rely
on search excerpts and secondary sources. **Read the primary texts, and get advice
if needed, before going public.**

Primary texts: [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal),
[Epic Content License](https://www.unrealengine.com/eula/content),
[Fab license summary](https://www.fab.com/cla).

## Unreal Engine

- Engine source and binaries must not be in this repository. Public distribution of
  Engine Code is restricted to Epic's channels, such as a fork within Epic's GitHub
  network or Fab, per excerpted terms and
  [a 2024 Epic DMCA notice](https://git.randommeaninglesscharacters.com/github/dmca/src/branch/master/2024/01/2024-01-22-epic.md).
- Your own code can generally be hosted where you choose, but code **copied or derived
  from engine source**, including modified plugins, may count as Engine Code. Keep it
  out of parts that will be publicly licensed. Small excerpts need checking.
- Engine content, including starter and template content, must not be copied into the
  public repository. Verify that any UE template used to start the project does not
  leave Epic content under `Content/` before release.
- A public clone will need contributors to obtain UE from Epic themselves.
- Royalties and fees apply by EULA terms to commercial products. Competition revenue
  would require review.
- A third-party summary states that the EULA restricts use of the engine as input to
  generative AI training. **Roverloom may train agents on simulator output, so check
  this directly before any machine-learning use.**

## Project license

- Separate parts could have different licenses: `python/`, `schemas/`, and
  `scenarios/` have no engine dependency and are the easiest to open-source.
- Excerpted Epic terms prohibit combining licensed material with GPL, LGPL (except
  dynamic linking), or Creative Commons ShareAlike works. Avoid copyleft in `unreal/`
  and its dependencies until reviewed. A permissive license such as Apache-2.0 or MIT
  for original Unreal project code seems likely to be compatible, but confirm first.
- Decide contribution terms before accepting external code. Relicensing later needs
  agreement from contributors.

## Third-party assets

- Fab Standard License and Megascans: forum quotations indicate that assets can ship
  inside packaged products, but source assets cannot be redistributed. A public
  repository containing them would be redistribution. Treat them as non-redistributable
  unless the listing and the [Fab EULA](https://www.fab.com/eula) say otherwise.
- `unreal/Content/Licensed/`, `Fab/`, and `Megascans/` are ignored by Git to prevent
  accidental commits. The public project must also open without them, so prefer
  original or permissively licensed assets for anything required to run.
- A private repository is also not automatically safe: check seat and sharing terms
  before giving other people access.
- Mars data: confirm the terms and credit requirements for each dataset used. Do not
  assume all planetary data is public domain, and do not imply agency endorsement.

## Before public release

- [ ] Choose licenses and add `LICENSE` and `THIRD_PARTY_NOTICES`
- [ ] Audit every asset and dependency for source and license
- [ ] Scan **full Git history including LFS objects** for secrets and restricted
      assets. Removing a file now does not remove it from history; if needed, publish
      from a clean history
- [ ] Check name and trademark use (Roverloom, Unreal Engine, space agencies)
- [ ] Budget for LFS bandwidth. GitHub docs currently list 10 GiB storage and 10 GiB
      monthly bandwidth on Free and Pro, charged to the owner, including downloads by
      others. Check [GitHub LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)
      and keep a $0 budget to prevent charges
