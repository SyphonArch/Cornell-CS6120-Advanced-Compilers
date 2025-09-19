"""Build a control flow graph from a Bril program."""
import sys
import json
from collections import defaultdict, deque

# Ops that end a basic block
TERMINATORS = {"br", "jmp", "ret"}

def is_label(instr):
    return "label" in instr

def is_terminator(instr):
    return instr.get("op") in TERMINATORS

def collect_leaders_and_labels(instrs):
    """Collect leader instruction indices and a map label -> instr index."""
    leaders = set()
    label_to_index = {}

    # Record label locations
    for i, ins in enumerate(instrs):
        if is_label(ins):
            label_to_index[ins["label"]] = i

    # First instruction is a leader (if any)
    if instrs:
        leaders.add(0)

    # Branch/jump targets and fallthroughs after terminators are leaders
    for i, ins in enumerate(instrs):
        op = ins.get("op")
        if op in ("br", "jmp"):
            for lab in ins.get("labels", []):
                if lab in label_to_index:
                    leaders.add(label_to_index[lab])
        if is_terminator(ins) and i + 1 < len(instrs):
            leaders.add(i + 1)

    # Labeled instructions also start blocks
    for i, ins in enumerate(instrs):
        if is_label(ins):
            leaders.add(i)

    return sorted(leaders), label_to_index

def split_basic_blocks(instrs):
    """Split instructions into basic blocks; keep metadata."""
    leaders, _ = collect_leaders_and_labels(instrs)
    blocks = []
    label_to_block = {}

    for bi, start in enumerate(leaders):
        end = leaders[bi + 1] if bi + 1 < len(leaders) else len(instrs)

        # Collect consecutive labels at block start
        j = start
        labels_here = []
        while j < end and is_label(instrs[j]):
            labels_here.append(instrs[j]["label"])
            j += 1

        # Block name: first label if present, else synthetic
        blk_name = labels_here[0] if labels_here else f"B{bi}"

        # Map every starting label to this block index
        for lab in labels_here:
            label_to_block[lab] = bi

        body = instrs[j:end]  # labels stripped
        terminator = body[-1] if body else None
        blocks.append({
            "name": blk_name,
            "start_labels": labels_here,
            "instrs": body,
            "terminator": terminator,
        })

    return blocks, label_to_block

def block_successors(block, label_to_block, blocks, idx):
    """Determine successor indices for a basic block."""
    # Empty block (label-only): fallthrough to next
    if not block["instrs"]:
        return [idx + 1] if idx + 1 < len(blocks) else []

    term = block["instrs"][-1]
    op = term.get("op")

    if op == "br":
        # conditional branch: exactly the listed labels
        dsts = []
        for lab in term.get("labels", []):
            if lab in label_to_block:
                dsts.append(label_to_block[lab])
        return dsts

    if op == "jmp":
        dsts = []
        for lab in term.get("labels", []):
            if lab in label_to_block:
                dsts.append(label_to_block[lab])
        return dsts

    if op == "ret":
        return []

    # any other terminator (future-proof)
    if is_terminator(term):
        return []

    # Fallthrough to next block
    return [idx + 1] if idx + 1 < len(blocks) else []

def compute_preds(n_blocks, succ_idx_lists):
    preds = [[] for _ in range(n_blocks)]
    for u, succs in enumerate(succ_idx_lists):
        for v in succs:
            preds[v].append(u)
    return preds

def to_names(idx_list, blocks):
    return [blocks[i]["name"] for i in idx_list]

def compute_rpo(entry_idx, succ_idx_lists):
    """Reverse postorder from entry (ignores unreachable blocks)."""
    n = len(succ_idx_lists)
    seen = [False] * n
    order = []

    def dfs(u):
        seen[u] = True
        for v in succ_idx_lists[u]:
            if not seen[v]:
                dfs(v)
        order.append(u)

    if entry_idx is not None and 0 <= entry_idx < n:
        dfs(entry_idx)
        order.reverse()
        return order
    # No entry or empty function
    return list(range(n))

def build_cfg_for_function(func):
    instrs = func.get("instrs", [])
    blocks, label_to_block = split_basic_blocks(instrs)

    # Name/index maps
    name2idx = {b["name"]: i for i, b in enumerate(blocks)}
    idx2name = [b["name"] for b in blocks]

    # Successors by index
    succ_idx = []
    for i, block in enumerate(blocks):
        succ_idx.append(block_successors(block, label_to_block, blocks, i))

    pred_idx = compute_preds(len(blocks), succ_idx)

    # Identify entry and exits
    entry_name = blocks[0]["name"] if blocks else None
    entry_idx = name2idx[entry_name] if entry_name is not None else None
    exit_idxs = [i for i, s in enumerate(succ_idx) if len(s) == 0]
    exit_names = to_names(exit_idxs, blocks)

    # Optional RPO for solvers
    rpo_idx = compute_rpo(entry_idx, succ_idx)
    rpo_names = to_names(rpo_idx, blocks)

    # String-keyed edges (succs/preds by name)
    edges = {idx2name[u]: to_names(succ_idx[u], blocks) for u in range(len(blocks))}
    preds = {idx2name[u]: to_names(pred_idx[u], blocks) for u in range(len(blocks))}

    result = {
        "name": func.get("name"),
        "args": func.get("args", []),
        "blocks": blocks,  # [{name, start_labels, instrs, terminator}]
        "cfg": {
            "entry": entry_name,
            "edges": edges,           # succs by name
            "preds": preds,           # preds by name
            "exits": exit_names,      # exit block names
            "name2idx": name2idx,
            "idx2name": idx2name,
            "succ_idx": succ_idx,     # parallel to blocks
            "pred_idx": pred_idx,     # parallel to blocks
            "rpo_idx": rpo_idx,
            "rpo": rpo_names,
        },
    }
    if "type" in func:
        result["type"] = func.get("type")
    return result

def main():
    """Read Bril program, build CFGs, and output them as JSON."""
    prog = json.load(sys.stdin)
    out = {"functions": []}
    for f in prog.get("functions", []):
        out["functions"].append(build_cfg_for_function(f))
    json.dump(out, sys.stdout, indent=2)

if __name__ == "__main__":
    main()