# Licensing review

Engineering notes, reviewed 2026-11-02. **Not legal advice.**

## How far this review could read the sources

| Source | Access | Reliability here |
| --- | --- | --- |
| [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal) | HTTP 403 to automated tools; **not read directly** | Binding text; must be read by a person |
| [Copy of the UE EULA on Steam](https://store.steampowered.com/eula/3855380_eula_0) | Read through an automated summary | Undated and predates the October 2026 change; section numbers are indicative |
| [Epic: AI training announcement](https://www.unrealengine.com/ue-devs-can-now-choose-to-train-ai-models-on-their-projects) | Search excerpts only (403) | Official, partially seen |
| [Summary of that change](https://www.theclick.gg/unreal-engine-ai-training-eula/) | Read | Third party |
| [Fab EULA](https://www.fab.com/eula), [Fab license summary](https://www.fab.com/cla) | HTTP 403; **not read** | Binding text unknown |
| [Epic: Licenses and Pricing in Fab](https://dev.epicgames.com/documentation/fab/licenses-and-pricing-in-fab) | Read | Official summary |
| [Epic Content License](https://www.unrealengine.com/eula/content) | Search excerpts only | Partial |

Status labels: **Supported** means an official or EULA-copy text says so.
**Unconfirmed** means it must not be relied on until the owner reads the binding text.

## 1. Developing a game or research simulator with Unreal Engine

- **Supported:** The EULA copy lists simulation for training purposes and education
  among example uses.
- **Supported, from the EULA copy:** Royalties are 5% on Royalty Revenue, with the
  first USD 1,000,000 lifetime gross revenue per product excluded. A release form is
  required before distributing a revenue-generating royalty product.
- **Supported, from the EULA copy:** Seat subscription exemptions exist for individuals
  and groups under USD 1,000,000 revenue over 12 months, for educational institutions
  using it only for education, and for use with no commercial benefit. Use by
  commercial entities counts as commercial.
- **Unconfirmed:** Whether Roverloom counts as a game (royalty) or a non-game product
  (seats). Ask Epic before commercial use. Press reports USD 1,850 per seat above the
  threshold for non-game companies; check Epic's current pricing.
- **Unconfirmed:** Terms for competition entry fees or prizes, and any effect if the
  work becomes connected to a company or sponsored research.

## 2. Publishing Roverloom's own C++ and Python as open source

- **Python, schemas, scenarios:** No engine code is included, so these are the simplest
  to open-source. Keep them engine-free.
- **Original Unreal C++:** Forum statements by Epic staff say your own code may be hosted
  as you choose, but they date from 2014–2015. **Unconfirmed against current text.**
- **Supported, from the EULA copy (§5, §6):** Engine Code may go only to parties
  separately licensed for the same engine version. Engine Tools are publicly distributed
  only through Fab or a fork in Epic's UnrealEngine GitHub network. Examples may be
  distributed. A [2024 DMCA notice](https://git.randommeaninglesscharacters.com/github/dmca/src/branch/master/2024/01/2024-01-22-epic.md)
  shows Epic enforcing against a public repository that consisted primarily of engine code.
- **Supported, from the EULA copy (§6(c)):** Licensed Technology must not be combined
  with code or content whose license would apply to it, including GPL, LGPL (unless
  dynamically linked), and CC BY-SA.
- **Project rules until reviewed:**
  - Do not copy or adapt engine source into `unreal/`. Calling public APIs is the goal;
    whether headers-derived code raises issues is **unconfirmed**.
  - Do not use copyleft dependencies in `unreal/`.
  - A permissive license such as Apache-2.0 or MIT looks plausible, but is **unconfirmed**.
  - Contributors would obtain the engine from Epic themselves.

## 3. Redistributing Epic and Fab assets on GitHub

- **Supported, from the EULA copy (§4):** Starter Content may not be distributed in source
  format as part of a non-engine product.
- **Supported:** Fab content is separate from the engine EULA. Its tiers are Personal
  (buyer revenue up to USD 100,000 over 12 months), Professional, and CC BY.
- **Unconfirmed:** Fab Standard source-format redistribution. Forum quotes indicate that
  shipping inside a packaged product is allowed, and redistributing source assets is not.
  **Project rule: treat Epic and Fab Standard assets as non-redistributable, including in
  public Git history.** Paths for them are ignored by Git.
- **Unconfirmed:** Whether a private repository with collaborators is permitted sharing.
  Do not add collaborators to a repository containing such assets before checking.
- **Unconfirmed:** How CC BY from Fab should be credited. Follow each listing, keep an
  attribution record, and never rely on a re-uploader's stated license.
- The public project must open and run without restricted assets.

## 4. Publishing images, video, logs, and simulation data

- **Supported, from the EULA copy (§4(a)(i)):** Rendered video created using Engine Code
  is a Non-Engine Product, and its distribution does not trigger royalties, even when it
  depicts Starter Content.
- **Unconfirmed:** Whether that covers images and data in the same way, and whether Fab
  allows public datasets that contain renderings of Fab assets, especially at scale.
- **Telemetry logs** from `schemas/` hold only our numbers and identifiers. No restriction
  was found, but this is not a confirmation. Do not embed Epic or Fab files in them.
- **Project rule:** Each published dataset lists the assets that appear in it.

### Mars data

- [NASA/USGS HiRISE DTMs on AWS](https://registry.opendata.aws/nasa-usgs-mars-hirise-dtms/)
  are listed as CC0 1.0 and suggest a citation with DOI 10.5066/P9VQTS7V.
- [HiRISE image policy](https://hirise.lpl.arizona.edu/media/usage.php) says images are
  public domain and requests the credit "NASA/JPL/University of Arizona".
- Check each product page. Credit data, and never imply agency endorsement. NASA names,
  logos, and rover designs are separate from data terms; the standard rover is an
  original design.

## 5. Using outputs as AI agent training data

The situation **changed days before this review**.

- **Supported by official excerpts:** Epic's announcement says it deleted two Section 6(e)
  restrictions: using the engine, including source, as generative AI training input; and
  using MetaHuman characters, curves, or replicating output to train or test AI.
- **Supported by a third party, requires checking:** Announced 29 October 2026, logged
  30 October 2026. Existing users accept updated terms through Epic's acceptance page.
- The change does not grant Epic any right to train on your project, according to Epic.
- **Supported, from Fab docs:** The `NoAI` tag means an asset "must not be used for
  generative AI data collection", and it remains available to sellers.
- **Unconfirmed:**
  - The final wording of the current EULA, and which version applies to UE 5.8 downloads.
  - Whether reinforcement learning on observations counts as "generative AI" under NoAI
    and other third-party terms.
  - Whether Standard-license Fab assets without NoAI may appear in training data.
- **Project rules:**
  - Scenes that generate training data contain only original, CC0, or confirmed assets.
  - Exclude NoAI assets from them, and record scene assets in the run manifest.
  - State-vector training on the lightweight simulator has no Unreal dependency.

## Summary

| Activity | Status | Current rule |
| --- | --- | --- |
| Develop with UE | Supported | Accept the EULA; review before commercial use |
| OSS of Python and schemas | No engine dependency found | Simple path; license still to be chosen |
| OSS of original UE C++ | Likely, unconfirmed | No engine source or copyleft; verify first |
| Engine or Fab assets on GitHub | Treated as prohibited | Keep out of Git |
| Publish video | Supported for rendered video | List assets; check Fab for its content |
| Publish logs | No restriction found | Logs contain only our data |
| AI training | Recently relaxed by Epic | Read current EULA; clean scenes only |

## Python dependencies

Declared licenses, listed by `uv run python ../scripts/audit_dependencies.py` on 2026-11-02. This reports
what packages declare, and is not legal advice. `pip-audit` found no known vulnerabilities in the locked
versions on the same day. Nothing runs this continuously.

| Used by | Packages | Declared licenses |
| --- | --- | --- |
| Runtime | `jsonschema`, `jsonschema-specifications`, `referencing`, `rpds-py`, `attrs`, `typing_extensions` | MIT, PSF-2.0 |
| Development only | `pytest`, `pluggy`, `iniconfig`, `Pygments`, `packaging`, `colorama`, `ruff`, `mypy`, `mypy_extensions`, `librt`, `ast_serialize`, `pathspec`, `types-jsonschema`, `playwright`, `pyee`, `greenlet` | MIT, BSD, Apache-2.0, PSF-2.0, MPL-2.0 (`pathspec`) |

Nothing from the development group ships with the runtime package. Roverloom itself declares no license
yet. Playwright drives a browser already on the machine, and no browser is downloaded or redistributed.

## Owner actions before public release or machine-learning use

1. Read the current UE EULA and change history, and accept it knowingly.
2. Read the Fab EULA on redistribution, sharing, and AI.
3. Ask Epic or a lawyer about game versus non-game classification and the license plan.
4. Choose licenses. Add `LICENSE` and `THIRD_PARTY_NOTICES`.
5. Audit assets and dependencies, and scan full history including LFS objects.
   Removing a file today does not remove it from history.
6. Check names and marks. Budget LFS usage: GitHub lists 10 GiB of storage and bandwidth
   on [Free and Pro](https://docs.github.com/en/billing/concepts/product-billing/git-lfs),
   charged to the owner. Keep a USD 0 budget.
