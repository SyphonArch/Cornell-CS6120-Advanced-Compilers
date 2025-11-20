"""Run trace-based optimization on Bril programs and report stats.

This is analogous to lesson8/test_licm.py but for lesson12's tracing setup.
"""

import os
import sys
import json
import math
import subprocess
from pathlib import Path
from tqdm import tqdm

# Paths relative to repo root where this script lives.
HERE = Path(__file__).resolve().parent


def bril_txt_to_json_str(path):
    with open(path, "r") as f:
        return subprocess.check_output(["bril2json"], stdin=f, text=True)


def bril_json_to_txt_str(prog_json):
    return subprocess.check_output(["bril2txt"], input=json.dumps(prog_json), text=True)


def run_bril_json(prog_json_str, args=None):
    """Run brili on a JSON-encoded Bril program.

    Returns (stdout, static_instr_cnt, dyn_instr_cnt_or_str).
    dyn_instr_cnt_or_str is an int on success, or "N/A" / "T/O".
    """
    if args is None:
        args = []

    program = json.loads(prog_json_str)
    static_instr_cnt = sum(len(func.get("instrs", [])) for func in program.get("functions", []))

    try:
        result = subprocess.run(
            ["brili", "-p", *args],
            input=prog_json_str,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
    except subprocess.CalledProcessError:
        return "N/A", static_instr_cnt, "N/A"
    except subprocess.TimeoutExpired:
        return "T/O", static_instr_cnt, "T/O"

    # brili -p reports total_dyn_inst on stderr.
    if not result.stderr.startswith("total_dyn_inst: "):
        return result.stdout, static_instr_cnt, "N/A"
    dyn_instr_cnt = int(result.stderr.split()[1])

    return result.stdout, static_instr_cnt, dyn_instr_cnt


def extract_args(bril_file_path):
    try:
        with open(bril_file_path, "r") as f:
            contents = f.readlines()
    except Exception:
        return []
    for line in contents:
        if line.replace(" ", "").startswith("#ARGS:"):
            return line[line.find(":") + 1 :].split()
    return []


def geometric_mean(nums):
    if not nums:
        return float("nan")
    return math.exp(sum(math.log(x) for x in nums) / len(nums))


def collect_targets(input_paths):
    targets = []
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


def train_trace(base_json_str, train_args, tag):
    """Run brili.ts with tracing to produce a traced JSON string.

    Mirrors eval_tracing.sh but works in-memory.
    """
    # Write base JSON to a temporary file because brili expects files.
    # Use the lesson12 tmp directory, and include a tag so each benchmark
    # gets distinct tmp artifacts (similar to lesson8/test_licm.py).
    tmp_dir = HERE / "tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    safe_tag = tag.replace("/", "__")
    base_json_path = tmp_dir / f"{safe_tag}.base.json"
    trace_json_path = tmp_dir / f"{safe_tag}.trace.json"

    with open(base_json_path, "w") as f:
        f.write(base_json_str)

    # brili -p <train_args> --trace-out=<trace_json_path> < base_json_path
    cmd = ["brili", "-p", *train_args, f"--trace-out={trace_json_path}"]
    train_log_path = tmp_dir / f"{safe_tag}.train.log"
    with open(base_json_path, "r") as f_in, open(train_log_path, "w") as f_log:
        # Capture stderr to a per-benchmark log file (for debugging) while
        # keeping stdout quiet. If brili fails, the caller will see the
        # exception and can inspect this .train.log file.
        proc = subprocess.run(
            cmd,
            stdin=f_in,
            stdout=subprocess.DEVNULL,
            stderr=f_log,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"brili training failed for {tag}; see {train_log_path}")

    # Inject trace using trace_inject.py
    traced_json_path = tmp_dir / f"{safe_tag}.traced.json"
    traced_bril_path = tmp_dir / f"{safe_tag}.traced.bril"
    with open(trace_json_path, "r") as f_in, open(traced_json_path, "w") as f_out:
        subprocess.run(["python3", str(HERE / "trace_inject.py")], stdin=f_in, stdout=f_out, check=True)

    # Also emit a human-readable .bril version of the traced program so we
    # can inspect the speculated trace easily.
    with open(traced_json_path, "r") as f_json:
        traced_prog = json.load(f_json)
    traced_bril_txt = bril_json_to_txt_str(traced_prog)
    with open(traced_bril_path, "w") as f_txt:
        f_txt.write(traced_bril_txt)

    return json.dumps(traced_prog)


def eval_results(results):
    total = len(results)
    good = [r for r in results if r["verdict"] == "Good!"]

    print(f"Successful optimizations: {len(good)}/{total}")
    if good:
        static_ratios = [r["static_traced"]/r["static_orig"] for r in good if isinstance(r["static_traced"], int) and isinstance(r["static_orig"], int)]
        dyn_ratios = [r["dyn_traced"]/r["dyn_orig"] for r in good if isinstance(r["dyn_traced"], int) and isinstance(r["dyn_orig"], int)]
        if static_ratios:
            print(f"Static Instr Ratio (GM traced/orig): {geometric_mean(static_ratios):.3f}x")
        if dyn_ratios:
            print(f"Dynamic Instr Ratio (GM traced/orig): {geometric_mean(dyn_ratios):.3f}x")
    else:
        print("No successful cases.")


def plot(results, out_png=None):
    import matplotlib.pyplot as plt  # type: ignore

    good = [r for r in results if r["verdict"] == "Good!"]
    if not good:
        return

    labels = [Path(r["file"]).name for r in good]
    r_traced_orig = [r["dyn_traced"]/r["dyn_orig"] for r in good if isinstance(r["dyn_traced"], int) and isinstance(r["dyn_orig"], int)]

    # Align labels to ratios length
    if len(labels) != len(r_traced_orig):
        labels = labels[: len(r_traced_orig)]

    order = sorted(range(len(labels)), key=lambda i: r_traced_orig[i])
    labels = [labels[i] for i in order]
    r_traced_orig = [r_traced_orig[i] for i in order]

    plt.figure(figsize=(max(8, len(labels) * 0.18), 4))
    xs = list(range(len(labels)))
    plt.bar(xs, r_traced_orig)
    plt.ylabel("Dynamic ratio (traced/orig)")
    plt.title("Tracing dynamic instruction ratios")
    plt.axhline(1.0, color="red", linestyle="--", linewidth=1)
    plt.xticks(xs, labels, rotation=90, fontsize=7)
    plt.tight_layout()
    if out_png:
        plt.savefig(out_png)
        print(f"Saved plot to {out_png}")
    else:
        plt.show()


def main(argv):
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["./benchmarks/core", "./benchmarks/float", "./benchmarks/long", "./benchmarks/mixed"], help=".bril files or directories")
    ap.add_argument("--plot", action="store_true", help="Show/save matplotlib plot of dynamic ratios")
    ap.add_argument("--png", type=str, default=None, help="Save plot to PNG instead of showing")
    ap.add_argument("--out", type=str, default="lesson12_results.json", help="Write detailed JSON results here")
    ap.add_argument("--train", nargs="*", default=None, help="Override training args (defaults to #ARGS from file)")
    args = ap.parse_args(argv)

    targets = collect_targets(args.paths)
    if not targets:
        print("No .bril files found.")
        return 0

    # Only print a compact summary, not per-program outputs.
    print(f"Target programs: {len(targets)}")
    os.makedirs(HERE / "tmp", exist_ok=True)

    results: List[Dict[str, Any]] = []

    for t in tqdm(targets):
        prog_args = extract_args(t)

        # Build base JSON from .bril text.
        base_json_str = bril_txt_to_json_str(str(t))

        out_orig, static_orig, dyn_orig = run_bril_json(base_json_str, prog_args)

        # Train trace and build traced program.
        try:
            train_args = args.train if args.train is not None else prog_args
            traced_json_str = train_trace(base_json_str, train_args, str(t))
        except Exception as e:  # noqa: BLE001
            verdict = f"BAD: trace training failed ({e})"
            rec = {
                "file": str(t),
                "verdict": verdict,
                "output_orig": out_orig,
                "static_orig": static_orig,
                "dyn_orig": dyn_orig,
                "output_traced": "N/A",
                "static_traced": "N/A",
                "dyn_traced": "N/A",
            }
            results.append(rec)
            continue

        out_traced, static_traced, dyn_traced = run_bril_json(traced_json_str, prog_args)

        # Verdict categories similar to LICM harness.
        if out_orig == "N/A":
            verdict = "BAD: original program fails"
        elif out_orig == "T/O":
            verdict = "BAD: original program times out"
        elif out_traced == "N/A":
            verdict = "BAD: traced program fails"
        elif out_traced == "T/O":
            verdict = "BAD: traced program times out"
        elif out_orig != out_traced:
            verdict = "BAD: output mismatch"
        else:
            verdict = "Good!"

        rec = {
            "file": str(t),
            "verdict": verdict,
            "output_orig": out_orig,
            "output_traced": out_traced,
            "static_orig": static_orig,
            "static_traced": static_traced,
            "dyn_orig": dyn_orig,
            "dyn_traced": dyn_traced,
        }
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
