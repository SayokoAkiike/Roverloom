# Graphics strategy

**The owner has since chosen an Apple M4 Mac ([ADR 0012](decisions/0012-m4-mac-for-unreal.md)).** This comparison of Windows options is kept as a record,
and for the case in which a separate machine is needed.

Reviewed 2026-11-02. **No option has been benchmarked**; Unreal Engine is not installed.
Prices are snapshots from the cited sources, exclude tax unless stated, and need a live
quote. Machine details are in [development-environment.md](development-environment.md).

Epic's [UE 5.8 recommendation](https://dev.epicgames.com/documentation/unreal-engine/hardware-and-software-specifications-for-unreal-engine?lang=en-US)
is 32 GB RAM and 8 GB+ VRAM on a DirectX 12 GPU. Its Lumen GPU list names AMD RX-6000,
Intel Arc A-series, or NVIDIA RTX 2000 or newer.

## Options

| | A. Current laptop, low settings | B. Laptop plus high-performance PC | C. Cloud GPU desktop |
| --- | --- | --- | --- |
| **Spec** | Radeon 840M, 13.8 GB RAM, 120 GB free | Suggested: RTX 5070 12 GB or better, 32 GB+ RAM, 2 TB NVMe, wired LAN | Suggested: 8 vCPU, 32 GB RAM, 24 GB GPU, 500 GB+ disk |
| **Upfront** | JPY 0 (optional external SSD) | About JPY 300,000–625,000; see notes | Nearly JPY 0 |
| **Monthly** | Electricity only | Electricity only | About USD 80–280; see notes |
| **MCP** | Local; simplest; untested | Yes: Claude Code on the PC, or SSH tunnel; untested | Same as B; untested |
| **High-quality look-dev** | No | Yes, expected | Yes, depends on stream |
| **Physics, C++, logic** | Yes, slowly | Yes | Yes |
| **Main problems** | Heat, memory, disk; results do not predict quality | Cost; two machines; asset sync through LFS | Latency, color, usage bills, data egress, availability |

### Cost notes

- **B:** The evidence is weak. A search result reported an RTX 5070 and 32 GB creator
  PC at JPY 309,800 in March 2025 (source page not verified, and out of date), one
  [import listing was JPY 625,821 in May 2026](https://www.desertcart.jp/products/711507679-codex-z2-gaming-desktop-amd-r7-8700f-geforce-rtx-5070.md),
  and [GPU trackers showed about JPY 100,000–140,000 for the card alone](https://gpuprix.com/jp/gpus/geforce-rtx-5070).
  Recent reports say memory shortages are raising prices. Get a current quote.
- **B, cheaper:** If a lab or university GPU workstation is available, cost may be zero.
  Check its rules, and the EULA seat conditions for that use.
- **C, AWS:** [g6.2xlarge](https://instances.vantage.sh/aws/ec2/g6.2xlarge) lists 8 vCPU,
  32 GiB, an NVIDIA L4 with 24 GiB, at about USD 0.98/hour with region and OS unspecified.
  A [rule of thumb](https://go-cloud.io/amazon-ec2-pricing/) adds about 30% for Windows,
  giving roughly USD 1.27/hour. That is an estimate, not a Tokyo price. With about USD 40
  for 500 GB at an assumed USD 0.08/GB, a total for 30 hours is about USD 80, and for
  190 hours about USD 280. Egress is extra. Stopped instances still bill for disk.
- **C, Shadow:** [Reported](https://tech-insider.org/shadow-pc-lite-vs-neo-power-steam-deck-linux-2026/)
  Power plan USD 54.99/month with an RTX A4500-class GPU and 28 GB RAM. Neo is cheaper with
  16 GB RAM. Sources conflict. **Availability in Japan was not confirmed**, and consumer
  terms for this use need checking.
- **C, GPU marketplaces:** Cheap hourly rates exist, mainly for Linux and AI workloads
  and can be interrupted. Not suitable for an interactive editor.

## MCP connection details

Epic's server has no authentication and binds to loopback. Do not change this to a LAN
address or expose it to a network.

- **A:** Claude Code runs on the same machine.
- **B and C, recommended:** Run Claude Code on the machine running the editor, through
  a remote session. This matches Epic's documented setup.
- **B and C, alternative:** An SSH local port forward to `127.0.0.1:8000`. The port stays
  bound to loopback. Compatibility with the server's Origin check is unverified.
- Any commit made on a remote machine must use the noreply address and scoped credentials.
  Avoid storing long-lived personal tokens on rented machines.

## Graphics settings plan

| Setting | A: current laptop (start) | B or C: quality target |
| --- | --- | --- |
| Target | 720p internal, stable interaction | 1440p, 60 FPS as a goal |
| Scalability | Low to Medium | High to Epic for captures |
| Global illumination | Lumen Lite, or off in test levels | Lumen, higher quality for captures |
| Shadows | Regular shadow maps | Virtual Shadow Maps |
| Geometry | Nanite if verified | Nanite rocks and terrain detail |
| Upscaling | TSR, 50–67% | TSR, 70–100% |

Keep these as named scalability profiles, so a laptop run never changes the quality
profile and vice versa.

## Recommendation

1. **Now: A, as a bounded test.** It costs nothing and answers the unknowns: can it run
   UE 5.8, can it verify MCP, and how slow are C++ builds? Physics and logic do not depend
   on rendering quality.
2. **For high-quality graphics: B.** With long-term regular use it should cost less than
   renting, keeps latency low, and has no hourly bills. Look for an existing lab machine
   before buying.
3. **C only as a short trial** with a hard budget, if you want to test quality before
   buying, or for occasional captures. Requires a separate owner decision.

### Decision gate after option A testing

Move to B when any of these is true:

- The editor is below about 15 FPS in the test level at the lowest usable settings.
- Memory exhaustion or thermal throttling repeatedly interrupts work.
- A C++ rebuild is too slow to keep working, or the disk cannot hold the engine and project.
- Work has reached lighting and materials, which cannot be judged on this GPU.

Thresholds are initial judgment calls, and can be changed after measurement.
