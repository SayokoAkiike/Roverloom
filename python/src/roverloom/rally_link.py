"""Same-Mac real-time rally link. Not a ranked or validated physics backend."""

import argparse
import time
from pathlib import Path

from roverloom.bridge import MAX_LINE_BYTES
from roverloom.contract import JsonDict, dump_json, parse_json
from roverloom.rally import Ghost, Rally, load_garage
from roverloom.unreal_link import connect


def run(
    out: Path,
    port: int,
    design_path: Path | None,
    difficulty: str,
    seed: int,
    ghost_path: Path | None,
    wait: float,
    linger: float,
) -> JsonDict:
    rally = Rally(load_garage(design_path), difficulty, seed)
    ghost = Ghost(ghost_path, difficulty, seed) if ghost_path else None
    out.mkdir(parents=True, exist_ok=True)
    conn = connect("127.0.0.1", port, wait)
    conn.settimeout(10)
    buffer = b""
    ended = None
    final = rally.state((0.0, 0.0, 0.7))
    try:
        with (out / "states.jsonl").open("w", encoding="utf-8") as states:
            while ended is None or time.monotonic() - ended < linger:
                try:
                    chunk = conn.recv(65536)
                except TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if len(line) > MAX_LINE_BYTES:
                        raise ValueError("rally line too large")
                    message = parse_json(line.decode())
                    if message.get("type") != "telemetry":
                        continue
                    final = rally.step(message["body"])
                    if ghost:
                        final["ghost_position_m"] = ghost.at(final["time_s"])
                    states.write(dump_json(final) + "\n")
                    conn.sendall(
                        (dump_json({"type": "mission_state", "body": final}) + "\n").encode()
                    )
                    if rally.outcome != "running" and ended is None:
                        ended = time.monotonic()
                if len(buffer) > MAX_LINE_BYTES:
                    raise ValueError("rally line too large")
    finally:
        conn.close()
    (out / "final_state.json").write_text(dump_json(final) + "\n", encoding="utf-8")
    (out / "ghost.json").write_text(dump_json(rally.ghost_document()) + "\n", encoding="utf-8")
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--garage", type=Path)
    parser.add_argument("--ghost", type=Path)
    parser.add_argument("--difficulty", choices=("easy", "standard", "hard"), default="easy")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--wait", type=float, default=120)
    parser.add_argument("--linger", type=float, default=8)
    args = parser.parse_args()
    result = run(
        args.out,
        args.port,
        args.garage,
        args.difficulty,
        args.seed,
        args.ghost,
        args.wait,
        args.linger,
    )
    print(dump_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
