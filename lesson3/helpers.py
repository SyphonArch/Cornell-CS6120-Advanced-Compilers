def instr_uses(instruction):
    return set(instruction.get("args", []))


def instr_def(instruction):
    return instruction.get("dest")


def linearize_cfg(cfg):
    blocks = cfg["blocks"]
    edges = cfg["cfg"]["edges"]
    entry = cfg["cfg"]["entry"]

    block_by_name = {b["name"]: b for b in blocks}

    # Find all blocks reachable from the entry block
    reachable = set()
    if entry and entry in block_by_name:
        stack = [entry]
        while stack:
            name = stack.pop()
            if name in reachable:
                continue
            reachable.add(name)
            for succ in edges.get(name, []):
                if succ in block_by_name:
                    stack.append(succ)

    # Build a DFS order of reachable blocks starting from entry
    order, seen = [], set()
    if entry in reachable:
        stack = [entry]
        while stack:
            name = stack.pop()
            if name in seen or name not in reachable:
                continue
            seen.add(name)
            order.append(name)
            # push successors so they are visited later
            for succ in reversed(edges.get(name, [])):
                if succ in reachable:
                    stack.append(succ)

    # Collect all labels that are actually the target of a branch/jump
    target_labels = set()
    for src in order:
        for dst in edges.get(src, []):
            if dst in reachable:
                target_labels.add(dst)

    # Emit instructions in the computed order
    # Insert a label only if this block is the target of a branch/jump
    instrs = []
    for name in order:
        if name in target_labels:
            instrs.append({"label": name})
        instrs.extend(block_by_name[name]["instrs"])

    return {"name": cfg["name"], "instrs": instrs}


def reachable_block_names(cfg):
    """Return the set of names of blocks reachable from the entry block."""
    entry = cfg["cfg"].get("entry")
    if entry is None:
        return set()
    edges = cfg["cfg"].get("edges", {})
    reachable = set()
    stack = [entry]
    while stack:
        b = stack.pop()
        if b in reachable:
            continue
        reachable.add(b)
        for s in edges.get(b, []):
            stack.append(s)
    return reachable