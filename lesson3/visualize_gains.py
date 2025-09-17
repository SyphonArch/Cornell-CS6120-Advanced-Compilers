# Visualize the performance gains from LVN + DCE.
# Input: dir_original, dir_optimized
# Program will walk through all .prof files in dir_original,
# find the corresponding file in dir_optimized, and print a table
# comparing the two. Then it will Visualize speedups in a bar chart.
# Disclaimer: this script was written with the assistance of ChatGPT.
import argparse
import os
import sys
import math
import matplotlib.pyplot as plt
import pandas as pd

def load_profile_data(prof_path):
    """Load profiling data from a .prof file."""
    with open(prof_path, 'r', encoding='utf-8') as f:
        return {line.split(':')[0]: int(line.split(':')[1]) for line in f if ':' in line}

def compare_profiles(original_data, optimized_data):
    """Compare two profiling data dictionaries based on total_dyn_inst."""
    orig = original_data.get("total_dyn_inst", 0)
    opt = optimized_data.get("total_dyn_inst", 0)

    if opt == 0 and orig == 0:
        speedup = 1.0
    elif opt == 0:
        speedup = math.inf
    else:
        speedup = orig / opt

    return {
        "original_dyn": orig,
        "optimized_dyn": opt,
        "speedup": speedup,
    }

def main():
    ap = argparse.ArgumentParser(description="Visualize performance gains from LVN + DCE.")
    ap.add_argument("dir_original", help="Directory with original .prof files")
    ap.add_argument("dir_optimized", help="Directory with optimized .prof files")
    args = ap.parse_args()

    if not os.path.isdir(args.dir_original):
        print(f"Error: {args.dir_original} is not a directory.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(args.dir_optimized):
        print(f"Error: {args.dir_optimized} is not a directory.", file=sys.stderr)
        sys.exit(1)

    results = []
    for filename in sorted(os.listdir(args.dir_original)):
        if filename.endswith(".prof"):
            orig_path = os.path.join(args.dir_original, filename)
            opt_path = os.path.join(args.dir_optimized, filename)
            if not os.path.isfile(opt_path):
                print(f"Warning: {opt_path} does not exist. Skipping.", file=sys.stderr)
                continue

            orig_data = load_profile_data(orig_path)
            opt_data = load_profile_data(opt_path)
            comparison = compare_profiles(orig_data, opt_data)
            comparison["program"] = filename[:-5]  # Strip .prof
            results.append(comparison)

    if not results:
        print("No profiling data found to compare.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(results)
    df = df[["program", "original_dyn", "optimized_dyn", "speedup"]]
    df = df.sort_values(by="program")  # alphabetical order

    # Print table
    with pd.option_context("display.max_rows", None, "display.width", 120):
        print(df.to_string(index=False, formatters={
            "original_dyn": "{:,}".format,
            "optimized_dyn": "{:,}".format,
            "speedup": lambda x: "∞" if math.isinf(x) else f"{x:.2f}×"
        }))

    # Print the average speedup (geometric mean)
    finite_speedups = [s for s in df["speedup"] if not math.isinf(s) and s > 0]
    if finite_speedups:
        geo_mean = math.exp(sum(math.log(s) for s in finite_speedups) / len(finite_speedups))
        print(f"\nGeometric mean speedup: {geo_mean:.2f}×")
    else:
        print("\nGeometric mean speedup: N/A (only infinite or invalid values)")

    # Print more stats like max, min, median
    if finite_speedups:
        print(f"Max speedup: {max(finite_speedups):.2f}×")
        print(f"Min speedup: {min(finite_speedups):.2f}×")
        median = sorted(finite_speedups)[len(finite_speedups) // 2]
        print(f"Median speedup: {median:.2f}×")
    else:
        print("No finite speedup values to compute max/min/median.")

    # Print how many programs had speedup > 1, = 1, < 1
    faster = sum(1 for s in df["speedup"] if s > 1)
    same = sum(1 for s in df["speedup"] if s == 1)
    slower = sum(1 for s in df["speedup"] if s < 1)
    infinite = sum(1 for s in df["speedup"] if math.isinf(s))
    print(f"\nPrograms faster: {faster}")
    print(f"Programs same: {same}")
    print(f"Programs slower: {slower}")
    print(f"Programs with infinite speedup: {infinite}")

    # Sort by speedup for visualization
    df = df.sort_values(by="speedup", ascending=False)

    # Plot (vertical bars)
    plt.figure(figsize=(10, 6))

    plt.bar(df["program"], df["speedup"], color="green")
    plt.axhline(y=1.0, color='blue', linestyle='--', label='No Speedup')
    plt.ylabel("Speedup (original / optimized)")
    plt.title("Performance Gains from LVN + DCE")
    plt.xticks(rotation=90)
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()