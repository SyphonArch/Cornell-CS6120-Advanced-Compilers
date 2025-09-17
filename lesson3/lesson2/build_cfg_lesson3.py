"""Build a control flow graph from a Bril program."""
import sys
import json

# Ops that end a basic block
TERMINATORS = {"br", "jmp", "ret"}

def is_label(instr):
    """Check if an instruction is a label."""
    return "label" in instr


def is_terminator(instr):
    """Check if an instruction is a terminator."""
    return instr.get("op") in TERMINATORS


def collect_leaders_and_labels(instrs):
    """Collect leader instructions and their corresponding labels."""
    # Leaders = starts of basic blocks
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
    """Split instructions into basic blocks."""
    leaders, _ = collect_leaders_and_labels(instrs)
    blocks = []
    label_to_block = {}

    # Build blocks from leader indices
    for bi, start in enumerate(leaders):
        end = leaders[bi + 1] if bi + 1 < len(leaders) else len(instrs)

        # Collect all consecutive labels at block start
        j = start
        labels_here = []
        while j < end and is_label(instrs[j]):
            labels_here.append(instrs[j]["label"])
            j += 1

        # Block name: first label if present, else synthetic
        blk_name = labels_here[0] if labels_here else f"B{bi}"

        # Map every starting label to this block
        for lab in labels_here:
            label_to_block[lab] = bi

        # Body = instructions in [j:end] (labels stripped)
        body = instrs[j:end]
        blocks.append({"name": blk_name, "instrs": body})

    return blocks, label_to_block


def block_successors(block, label_to_block, blocks, idx):
    """Determine the successors of a basic block."""
    # Determine successors from the block's terminator (or fallthrough)
    if not block["instrs"]:
        return [idx + 1] if idx + 1 < len(blocks) else []

    term = block["instrs"][-1]
    op = term.get("op")

    if op == "br":
        return [label_to_block[lab] for lab in term.get("labels", []) if lab in label_to_block]
    if op == "jmp":
        return [label_to_block[lab] for lab in term.get("labels", []) if lab in label_to_block]
    if op == "ret":
        return []
    if is_terminator(term):
        return []

    # Fallthrough to next block
    return [idx + 1] if idx + 1 < len(blocks) else []


def build_cfg_for_function(func):
    instrs = func.get("instrs", [])
    blocks, label_to_block = split_basic_blocks(instrs)

    edges = {}
    for i, block in enumerate(blocks):
        succ_idx = block_successors(block, label_to_block, blocks, i)
        edges[block["name"]] = [blocks[j]["name"] for j in succ_idx]

    result = {
        "name": func.get("name"),
        "args": func.get("args", []),     # <— preserve arguments
        "blocks": blocks,
        "cfg": {
            "entry": blocks[0]["name"] if blocks else None,
            "edges": edges,
        },
    }
    if "type" in func:
        result["type"] = func.get("type")     # <— preserve type if present
    return result

def main():
    """Main function to read Bril program, build CFGs, and output them."""
    prog = json.load(sys.stdin)
    out = {"functions": []}
    for f in prog.get("functions", []):
        out["functions"].append(build_cfg_for_function(f))
    json.dump(out, sys.stdout, indent=2)

if __name__ == "__main__":
    main()