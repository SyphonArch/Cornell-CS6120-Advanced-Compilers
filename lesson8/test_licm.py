"""Run LICM on Bril programs and report stats."""
from __future__ import annotations

import os
import sys
import json
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

import licm
from lesson6.to_ssa import main as to_ssa_main


def bril_txt_to_json_str(path: str) -> str:
    with open(path, "r") as f:
        return subprocess.check_output(["bril2json"], stdin=f, text=True)


def bril_json_to_txt_str(prog_json: dict) -> str:
    return subprocess.check_output(["bril2txt"], input=json.dumps(prog_json), text=True)


def run_bril(bril_path: str, args: List[str] | None = None):
    if args is None:
        args = []

    with open(bril_path, "r") as f:
        bril_json_str = subprocess.check_output(["bril2json"], stdin=f, text=True)
    program = json.loads(bril_json_str)

    static_instr_cnt = sum(len(func.get("instrs", [])) for func in program.get("functions", []))

    try:
        result = subprocess.run(["brili", "-p", *args], input=bril_json_str, capture_output=True, text=True, check=True, timeout=20)
    except subprocess.CalledProcessError:
        return "N/A", static_instr_cnt, "N/A"
    except subprocess.TimeoutExpired:
        return "T/O", static_instr_cnt, "T/O"

    assert result.stderr.startswith("total_dyn_inst: "), f"Invalid total_dyn_inst string: {result.stderr}"
    dyn_instr_cnt = int(result.stderr.split()[1])

    return result.stdout, static_instr_cnt, dyn_instr_cnt


def extract_args(bril_file_path: Path) -> List[str]:
    try:
        with open(bril_file_path, "r") as f:
            contents = f.readlines()
    except Exception:
        return []
    for line in contents:
        if line.replace(" ", "").startswith("#ARGS:"):
            return line[line.find(":") + 1 :].split()
    return []


def geometric_mean(nums: List[float]) -> float:
    if not nums:
        return float("nan")
    return math.exp(sum(math.log(x) for x in nums) / len(nums))


def licm_wrapper(before_path: Path, after_path: Path, use_ssa: bool):
    bril_json_str = bril_txt_to_json_str(str(before_path))
    program = json.loads(bril_json_str)

    optimized = licm.main(program, use_ssa=use_ssa)
    bril_text = bril_json_to_txt_str(optimized)

    with open(after_path, "w") as out_f:
        out_f.write(bril_text)


def to_ssa_wrapper(before_path: Path, after_path: Path):
    """Convert a Bril program to SSA and write to after_path."""
    bril_json_str = bril_txt_to_json_str(str(before_path))
    program = json.loads(bril_json_str)
    ssa_prog = to_ssa_main(program)
    bril_text = bril_json_to_txt_str(ssa_prog)
    with open(after_path, "w") as out_f:
        out_f.write(bril_text)


def collect_targets(input_paths: List[str]) -> List[Path]:
    targets: List[Path] = []
    for p in input_paths:
        path = Path(p)
        if path.is_file() and path.name.endswith(".bril"):
            targets.append(path)
        elif path.is_dir():
            for child in path.iterdir():
                if child.is_file() and child.name.endswith(".bril"):
                    targets.append(child)
    targets.sort()
    return targets


def eval_results(results: List[Dict[str, Any]]):
    total = len(results)
    good = [r for r in results if r["verdict"] == "Good!"]

    print(f"Successful optimizations: {len(good)}/{total}")
    if good:
        static_ratios = [r["static_after"]/r["static_before"] for r in good]
        dyn_ratios = [r["dyn_after"]/r["dyn_before"] for r in good]
        print(f"Static Instr Ratio (GM): {geometric_mean(static_ratios):.3f}x")
        print(f"Dynamic Instr Ratio (GM): {geometric_mean(dyn_ratios):.3f}x")
        # If SSA baseline was recorded, compare against it too
        good_ssa = [r for r in good if isinstance(r.get("static_ssa"), int) and isinstance(r.get("dyn_ssa"), int)]
        if good_ssa:
            static_vs_ssa = [r["static_after"]/r["static_ssa"] for r in good_ssa]
            dyn_vs_ssa = [r["dyn_after"]/r["dyn_ssa"] for r in good_ssa]
            print(f"Static vs SSA (GM): {geometric_mean(static_vs_ssa):.3f}x")
            print(f"Dynamic vs SSA (GM): {geometric_mean(dyn_vs_ssa):.3f}x")
    else:
        print("No successful cases.")


def plot(results: List[Dict[str, Any]], out_png: str | None = None):
    import matplotlib.pyplot as plt  # type: ignore

    good = [r for r in results if r["verdict"] == "Good!"]
    if not good:
        return

    labels = [Path(r["file"]).name for r in good]
    r_after_before = [r["dyn_after"]/r["dyn_before"] for r in good]
    has_ssa = all(isinstance(r.get("dyn_ssa"), int) for r in good)
    r_after_ssa = [r["dyn_after"]/r["dyn_ssa"] for r in good] if has_ssa else None

    order = sorted(range(len(labels)), key=lambda i: r_after_before[i])
    labels = [labels[i] for i in order]
    r_after_before = [r_after_before[i] for i in order]
    if has_ssa and r_after_ssa is not None:
        r_after_ssa = [r_after_ssa[i] for i in order]

    plt.figure(figsize=(max(8, len(labels)*0.18), 4))
    xs = list(range(len(labels)))
    if has_ssa and r_after_ssa is not None:
        width = 0.45
        plt.bar([x - width/2 for x in xs], r_after_before, width=width, label="after/before")
        plt.bar([x + width/2 for x in xs], r_after_ssa, width=width, label="after/ssa")
        plt.ylabel("Dynamic ratio")
        plt.title("LICM dynamic ratios vs before and SSA")
        plt.legend()
    else:
        plt.bar(xs, r_after_before)
        plt.ylabel("Dynamic ratio (after/before)")
        plt.title("LICM dynamic instruction ratios")
    plt.axhline(1.0, color="red", linestyle="--", linewidth=1)
    plt.xticks(xs, labels, rotation=90, fontsize=7)
    plt.tight_layout()
    if out_png:
        plt.savefig(out_png)
        print(f"Saved plot to {out_png}")
    else:
        plt.show()


def main(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["lesson8/benchmarks/core"], help=".bril files or directories")
    ap.add_argument("--plot", action="store_true", help="Show/save matplotlib plot of dynamic ratios")
    ap.add_argument("--png", type=str, default=None, help="Save plot to PNG instead of showing")
    ap.add_argument("--out", type=str, default="results_licm.json", help="Write detailed JSON results here")
    ap.add_argument("--ssa", action="store_true", help="Run LICM in SSA and convert back; also compare against raw SSA")
    args = ap.parse_args(argv)

    targets = collect_targets(args.paths)
    if not targets:
        print("No .bril files found.")
        return 0

    print(f"Target programs: {len(targets)}")
    os.makedirs("./tmp", exist_ok=True)

    results: List[Dict[str, Any]] = []

    for t in tqdm(targets):
        prog_args = extract_args(t)

        out_before, static_before, dyn_before = run_bril(str(t), prog_args)

        # Optional SSA baseline
        ssa_output = None
        ssa_static = None
        ssa_dyn = None
        if args.ssa:
            ssa_file = Path("./tmp") / (str(t).replace("/", "__") + ".ssaonly")
            to_ssa_wrapper(t, ssa_file)
            ssa_output, ssa_static, ssa_dyn = run_bril(str(ssa_file), prog_args)

        licm_file = Path("./tmp") / (str(t).replace("/", "__") + ".licm")
        licm_wrapper(t, licm_file, use_ssa=args.ssa)

        out_after, static_after, dyn_after = run_bril(str(licm_file), prog_args)

        # Detailed verdict categories similar to lesson6/test_ssa.py
        if out_before == "N/A":
            verdict = "BAD: original program fails"
        elif out_before == "T/O":
            verdict = "BAD: original program times out"
        elif out_after == "N/A":
            verdict = "BAD: optimized program fails"
        elif out_after == "T/O":
            verdict = "BAD: optimized program times out"
        elif out_before != out_after:
            verdict = "BAD: output mismatch"
        else:
            verdict = "Good!"

        rec = {
            "file": str(t),
            "verdict": verdict,
            "output_before": out_before,
            "output_after": out_after,
            "static_before": static_before,
            "static_after": static_after,
            "dyn_before": dyn_before,
            "dyn_after": dyn_after,
        }
        if args.ssa:
            rec.update({
                "output_ssa": ssa_output,
                "static_ssa": ssa_static,
                "dyn_ssa": ssa_dyn,
            })
        results.append(rec)

    eval_results(results)

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
        print(f"Wrote results to {args.out}")

    if args.plot:
        plot(results, out_png=args.png)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
