def instr_uses(instruction):
    return list(instruction.get("args", []))  # not a set


def instr_def(instruction):
    return instruction.get("dest")


def linearize_cfg(cfg):
    blocks = cfg["blocks"]
    edges = cfg["cfg"]["edges"]
    entry = cfg["cfg"]["entry"]

    block_by_name = {b["name"]: b for b in blocks}
    original_order = [b["name"] for b in blocks]
    orig_index = {name: i for i, name in enumerate(original_order)}

    # Reachability (using edges already built from original text/fallthroughs)
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

    # Helpers
    def has_terminator(bname):
        instrs = block_by_name[bname]["instrs"]
        if not instrs:  # empty => no terminator
            return False
        return instrs[-1].get("op") in {"br", "jmp", "ret"}

    def textual_fallthrough(bname):
        """Next reachable block in the original textual order (only if no terminator)."""
        if has_terminator(bname):
            return None
        i = orig_index[bname]
        for j in range(i + 1, len(original_order)):
            nxt = original_order[j]
            if nxt in reachable:
                return nxt
        return None  # no fallthrough (textually last among reachable)

    # Build a trace-preserving layout:
    placed = set()
    order = []

    def place_chain(start):
        b = start
        while b is not None and b in reachable and b not in placed:
            placed.add(b)
            order.append(b)
            # Follow textual fallthrough only while there is no terminator.
            if has_terminator(b):
                break
            ft = textual_fallthrough(b)
            if ft is None or ft in placed:
                break
            b = ft

    # Start from entry
    if entry in reachable:
        place_chain(entry)

    # Then place remaining reachable blocks in original order (each as a new chain)
    for name in original_order:
        if name in reachable and name not in placed:
            place_chain(name)

    # Compute which blocks need labels (any block that is a branch/jump target)
    target_labels = set()
    for src in order:
        for dst in edges.get(src, []):
            if dst in reachable:
                target_labels.add(dst)

    # Emit, inserting a jmp only when layout breaks fallthrough
    instrs = []
    for idx, name in enumerate(order):
        if name in target_labels:
            instrs.append({"label": name})

        b_instrs = list(block_by_name[name]["instrs"])
        instrs.extend(b_instrs)

        # If the block has no terminator and *does* have a textual fallthrough,
        # ensure that the next emitted block matches; otherwise, patch with jmp.
        if not has_terminator(name):
            ft = textual_fallthrough(name)
            next_name = order[idx + 1] if idx + 1 < len(order) else None
            if ft is not None and ft != next_name:
                instrs.append({"op": "jmp", "labels": [ft]})
            # If ft is None (textual exit), we don't add 'ret'; we rely on placing
            # such blocks last so there is no accidental fallthrough.

    out = {"name": cfg.get("name"), "instrs": instrs}
    if "args" in cfg:
        out["args"] = cfg["args"]
    if "type" in cfg:
        out["type"] = cfg["type"]
    return out


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