import json
import sys
import argparse
import os
from collections import defaultdict
# Optional visualization deps; make import optional so analysis code works without them.
try:
    import matplotlib.pyplot as plt  # type: ignore
    import networkx as nx  # type: ignore
    _HAS_VIS = True
except Exception:  # pragma: no cover - purely defensive
    plt = None  # type: ignore
    nx = None  # type: ignore
    _HAS_VIS = False

# Add parent directory to path to find lesson2 and lesson3 modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from lesson2.build_cfg_lesson3 import build_cfg_for_function
from lesson3.helpers_lesson5 import (
    all_block_names, entry_name, preds_by_name, reachable_block_names
)


def compute_dominators(cfg):
    """Compute dominator sets for each block.

    Restrict to blocks reachable from entry to avoid unreachable predecessors
    corrupting the intersection and eliminating the entry from dom sets.
    """
    reach = reachable_block_names(cfg)
    names = list(reach) if reach else all_block_names(cfg)
    entry = entry_name(cfg)

    dom = {n: set(names) for n in names}
    if entry is not None:
        dom[entry] = {entry}

    changed = True
    while changed:
        changed = False
        for b in names:
            if b == entry:
                continue
            # Only consider reachable predecessors
            preds = [p for p in preds_by_name(cfg).get(b, []) if p in names]
            if not preds:
                new_set = {b}
            else:
                common = set(names)
                for p in preds:
                    common &= dom[p]
                new_set = {b} | common
            if new_set != dom[b]:
                dom[b] = new_set
                changed = True
    return dom


def compute_imm_dom(dom, entry):
    """From dominator sets, derive the immediate dominator for each block."""
    imm_dom = {}
    for b, s in dom.items():
        if b == entry:
            imm_dom[b] = entry
        else:
            strict = s - {b}
            if not strict:
                imm_dom[b] = None
                continue
            candidates = []
            for d in strict:
                others = strict - {d}
                if all(o in dom[d] for o in others):
                    candidates.append(d)
            assert len(candidates) <= 1, f"Multiple immediate dominators for {b}: {candidates}"
            imm_dom[b] = candidates[0] if candidates else None
    return imm_dom


def build_dom_tree(imm_dom, entry):
    """Invert immediate dominators into a dominance tree (parent → children)."""
    tree = {n: [] for n in imm_dom.keys()}
    for b, p in imm_dom.items():
        if b == entry:
            continue
        if p is not None and p != b:
            tree[p].append(b)
    for k in list(tree.keys()):
        tree[k].sort()
    return tree


def compute_dominance_frontier(cfg, imm_dom):
    """Compute dominance frontier for each block using the standard local+up algorithm.

    DF_local(x) = { y in succ(x) | idom[y] != x }
    DF_up(x)    = union over z in children(x) of { y in DF(z) | x not in dom[y] }
    DF(x)       = DF_local(x) ∪ DF_up(x)
    """
    reach = reachable_block_names(cfg)
    names = list(reach) if reach else all_block_names(cfg)
    # Filter edges to reachable nodes only
    all_edges = cfg["cfg"].get("edges", {})
    edges = {u: [v for v in vs if v in names] for u, vs in all_edges.items() if u in names}

    # Build dominator sets for quick dominance tests
    dom_sets = compute_dominators(cfg)

    # Build children map from immediate dominators
    children = {n: [] for n in names}
    entry = entry_name(cfg)
    for b, p in imm_dom.items():
        if b == entry:
            continue
        if p is not None and p != b:
            children[p].append(b)

    DF = {n: set() for n in names}

    # DF_local
    for x in names:
        for y in edges.get(x, []):
            if imm_dom.get(y) != x:
                DF[x].add(y)

    # DF_up via a post-order traversal of the dom tree
    sys.setrecursionlimit(10000)

    def dfs_df(x):
        for z in children.get(x, []):
            dfs_df(z)
            for y in DF[z]:
                # if x does not strictly dominate y
                if x not in dom_sets.get(y, set()) or x == y:
                    DF[x].add(y)

    if entry is not None and (not names or entry in names):
        dfs_df(entry)
    else:
        # No entry: process all roots
        for n in names:
            if imm_dom.get(n) in (None, n):
                dfs_df(n)

    return DF


def dominates_naive(cfg, a, b, max_paths=10000, max_len=10000):
    """Naive dominance check: a dominates b if all entry→b paths include a."""
    entry = entry_name(cfg)
    if entry is None:
        return a == b
    succs = cfg["cfg"]["edges"]
    paths = []
    stack = [(entry, [entry])]

    while stack and len(paths) < max_paths:
        u, path = stack.pop()
        if len(path) > max_len:
            continue
        if u == b:
            paths.append(path[:])
            continue
        for v in succs.get(u, []):
            if len(path) + 1 <= max_len:
                stack.append((v, path + [v]))
    if not paths:
        # unreachable: only self-dominates
        return a == b
    return all(a in p for p in paths)


def analyze_function(cfg):
    """Run dominance analysis on a function CFG and return structured results."""
    entry = entry_name(cfg)
    dom_sets = compute_dominators(cfg)
    imm_dom = compute_imm_dom(dom_sets, entry)
    dom_tree = build_dom_tree(imm_dom, entry)
    df = compute_dominance_frontier(cfg, imm_dom)

    return {
        "function": cfg.get("name"),
        "entry": entry,
        "blocks": all_block_names(cfg),
        "imm_dom": {n: imm_dom[n] for n in all_block_names(cfg)},
        "dominators": {n: sorted(list(dom_sets[n])) for n in all_block_names(cfg)},
        "dom_tree_children": {n: sorted(dom_tree.get(n, [])) for n in all_block_names(cfg)},
        "dominance_frontier": {n: sorted(list(df[n])) for n in all_block_names(cfg)},
    }


def check_with_naive(cfg, dom_sets):
    """Cross-check fast dominator sets with the naive definition."""
    for b in dom_sets:
        for a in dom_sets[b]:
            if not dominates_naive(cfg, a, b):
                return False
        # also check if we missed any
        for a in all_block_names(cfg):
            if a not in dom_sets[b] and dominates_naive(cfg, a, b):
                return False
    return True


def visualize_all(function_analyses):
    """Draw dominance trees for all functions in one matplotlib figure, scaling layout, nodes, and fonts."""
    if not _HAS_VIS:
        # Visualization not available; silently no-op (caller guards with --vis)
        return

    def build_positions(tree, root, x=0, y=0, level_gap=1.5, x_gap=1.0):
        """Recursively assign positions to nodes based on tree structure."""
        children = tree.get(root, [])
        if not children:
            return {root: (x, y)}, x, x

        pos = {}
        child_positions = []
        cur_x = x
        for c in children:
            child_pos, left, right = build_positions(tree, c, cur_x, y - level_gap, level_gap, x_gap)
            child_positions.append((left, right, c, child_pos))
            cur_x = right + x_gap
            pos.update(child_pos)
        min_x = child_positions[0][0]
        max_x = child_positions[-1][1]
        center_x = (min_x + max_x) / 2.0
        pos[root] = (center_x, y)
        return pos, min_x, max_x

    n = len(function_analyses)
    # compute max depth across all trees
    def depth(tree, root):
        if not tree[root]:
            return 1
        return 1 + max(depth(tree, c) for c in tree[root])

    max_depth = 1
    for analysis in function_analyses:
        tree = analysis["dom_tree_children"]
        root = analysis["entry"]
        max_depth = max(max_depth, depth(tree, root))

    fig_height = max(4, max_depth * 1.5)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, fig_height))  # type: ignore[arg-type]
    if n == 1:
        axes = [axes]

    for ax, analysis in zip(axes, function_analyses):
        tree = analysis["dom_tree_children"]
        root = analysis["entry"]
        pos, _, _ = build_positions(tree, root)

        G = nx.DiGraph()
        for parent, children in tree.items():
            for child in children:
                G.add_edge(parent, child)

        depth_here = depth(tree, root)
        node_size = 2000 / max(1, depth_here / 2)
        font_size = max(8, 16 - depth_here)

        nx.draw(  # type: ignore[attr-defined]
            G,
            pos,
            with_labels=True,
            arrows=True,
            node_size=node_size,
            node_color="#e3848d",
            font_size=font_size,
            ax=ax,
        )
        ax.set_title(f"{analysis['function']} (entry: {root})", fontsize=font_size + 2)

    plt.tight_layout()  # type: ignore[call-arg]
    plt.savefig("dominance_trees.png")  # type: ignore[call-arg]



def main():
    """Main CLI: analyze functions, optionally check with naive and visualize."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--vis", action="store_true", help="Show dominance trees with matplotlib")
    parser.add_argument("--naive_check", action="store_true", help="Cross-check with naive algorithm")
    args = parser.parse_args()

    prog = json.load(sys.stdin)
    out = []
    cfgs = []
    for f in prog.get("functions", []):
        cfg = build_cfg_for_function(f)
        analysis = analyze_function(cfg)
        out.append(analysis)
        cfgs.append(cfg)

    if args.naive_check:
        all_ok = True
        for f, analysis, cfg in zip(prog.get("functions", []), out, cfgs):
            ok = check_with_naive(cfg, {n: set(analysis["dominators"][n]) for n in analysis["blocks"]})
            if not ok:
                print(f"WARNING: mismatches found in {analysis['function']}", file=sys.stderr)
                for n in analysis["blocks"]:
                    dom_set = set(analysis["dominators"][n])
                    for d in dom_set:
                        if not dominates_naive(cfg, d, n):
                            print(f"  {d} does not dominate {n} (claimed)", file=sys.stderr)
                    for d in all_block_names(cfg):
                        if d not in dom_set and dominates_naive(cfg, d, n):
                            print(f"  {d} dominates {n} (missed)", file=sys.stderr)
                all_ok = False
        if all_ok:
            print("All dominance checks passed", file=sys.stderr)

    if args.vis:
        if _HAS_VIS:
            visualize_all(out)
        else:
            print("Visualization requested but matplotlib/networkx not installed; skipping --vis.", file=sys.stderr)

    json.dump(out, sys.stdout, indent=2)
