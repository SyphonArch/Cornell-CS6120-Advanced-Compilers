"""
Make an LVN+DCE test suite directory.

- Create <src_dir>.lvn.dce (error if exists unless --force).
- For each <name>.bril.lvn.dce in <src_dir>, write <dst>/<name>.bril:
    * copy contents from the .lvn.dce file
    * if no "# ARGS ..." line exists, copy it from <src_dir>/<name>.bril (if present)
- Copy every *.out from <src_dir> to <dst> unchanged.

Usage:
  python make_lvn_dce_suite.py <src_dir> [--force]
"""

import argparse
import os
import shutil
import sys

def find_args_line(path: str) -> str | None:
    """Return the first '# ARGS ...' line from path (spaces before 'ARGS' allowed)."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.replace(" ", "").startswith("#ARGS"):
                return line
    return None

def file_has_args_line(path: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.replace(" ", "").startswith("#ARGS"):
                return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", help="Source directory containing *.lvn.dce and *.out")
    ap.add_argument("--force", action="store_true", help="Overwrite existing destination dir")
    args = ap.parse_args()

    src = os.path.abspath(args.src_dir)
    if not os.path.isdir(src):
        print(f"error: {src!r} is not a directory", file=sys.stderr)
        sys.exit(1)

    dst = src + ".lvn.dce"
    if os.path.exists(dst):
        if not args.force:
            print(f"error: destination {dst!r} exists (use --force to overwrite)", file=sys.stderr)
            sys.exit(1)
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)

    # 1) Copy transformed programs: *.lvn.dce -> drop suffix into dst
    count_prog = 0
    for name in os.listdir(src):
        if not name.endswith(".lvn.dce"):
            continue
        base = name[:-8]  # strip ".lvn.dce"
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, base)

        # Read transformed content
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.readlines()

        # Ensure ARGS line exists: if missing, take from base file in src (if present)
        if not any(line.replace(" ", "").startswith("#ARGS") for line in content):
            base_src_path = os.path.join(src, base)
            args_line = find_args_line(base_src_path)
            if args_line:
                content.insert(0, args_line)
                print(f"[ARGS] inserted into {base}")
            else:
                print(f"[WARN] no ARGS found for {base} (looked in {base_src_path})")

        # Write to destination (dropping suffix)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "w", encoding="utf-8") as f:
            f.writelines(content)
        count_prog += 1
        print(f"[COPY] {name} -> {os.path.relpath(dst_path, dst)}")

    # 2) Copy all *.out unchanged
    count_out = 0
    for name in os.listdir(src):
        if not name.endswith(".out"):
            continue
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, name)
        shutil.copyfile(src_path, dst_path)
        count_out += 1
        print(f"[COPY] {name} -> {os.path.relpath(dst_path, dst)}")

    print(f"\nDone. Programs: {count_prog}, .out files: {count_out}")
    print(f"Destination: {dst}")

if __name__ == "__main__":
    main()