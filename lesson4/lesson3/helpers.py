# Simple helpers for Bril CFGs

TERMINATORS = {"br", "jmp", "ret"}


def instr_uses(instruction):
    """Return list of variable names read by this instruction."""
    return list(instruction.get("args", []))


def instr_def(instruction):
    """Return destination variable name or None."""
    return instruction.get("dest")


def reachable_block_names(cfg):
    """Return set of block names reachable from the entry."""
    entry = cfg["cfg"].get("entry")
    if not entry:
        return set()

    edges = cfg["cfg"].get("edges", {})
    seen = set()
    stack = [entry]
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        for s in edges.get(b, []):
            stack.append(s)
    return seen


def linearize_cfg(cfg):
    """
    Produce a flat instruction list from the CFG, inserting labels for
    jump/branch targets and 'jmp' when the intended fallthrough is not the
    next block in the chosen order. Preserves existing terminators.
    """
    blocks = cfg["blocks"]
    edges = cfg["cfg"]["edges"]
    entry = cfg["cfg"]["entry"]

    block_by_name = {b["name"]: b for b in blocks}
    original_order = [b["name"] for b in blocks]
    orig_index = {name: i for i, name in enumerate(original_order)}

    # Reachable set (keep unreachable blocks in layout after reachable ones)
    reach = reachable_block_names(cfg)
    if not reach:
        # No entry or empty function: just dump labels/instrs in textual order
        instrs = []
        emitted = set()
        # Any block that is a jump target in edges needs a label
        targets = set()
        for src in original_order:
            for dst in edges.get(src, []):
                targets.add(dst)
        for name in original_order:
            if name in targets and name not in emitted:
                instrs.append({"label": name})
                emitted.add(name)
            instrs.extend(block_by_name[name]["instrs"])
        out = {"name": cfg.get("name"), "instrs": instrs}
        if "args" in cfg:
            out["args"] = cfg["args"]
        if "type" in cfg:
            out["type"] = cfg["type"]
        return out

    def has_terminator(name):
        body = block_by_name[name]["instrs"]
        return bool(body) and body[-1].get("op") in TERMINATORS

    def textual_fallthrough(name):
        """Next block in original textual order that is reachable."""
        if has_terminator(name):
            return None
        i = orig_index[name]
        for j in range(i + 1, len(original_order)):
            nxt = original_order[j]
            if nxt in reach:
                return nxt
        return None

    # Build a trace-preserving order:
    placed = set()
    order = []

    def place_chain(start):
        b = start
        while b is not None and b in reach and b not in placed:
            placed.add(b)
            order.append(b)
            if has_terminator(b):
                break
            ft = textual_fallthrough(b)
            if ft is None or ft in placed:
                break
            b = ft

    # Start from entry if reachable
    if entry in reach:
        place_chain(entry)
    # Then place remaining reachable in textual order
    for name in original_order:
        if name in reach and name not in placed:
            place_chain(name)
    # Finally, append unreachable blocks (as isolated chains) in textual order
    for name in original_order:
        if name not in placed:
            order.append(name)

    # Any block that is a jump/branch target needs a label
    target_labels = set()
    for src in order:
        for dst in edges.get(src, []):
            target_labels.add(dst)

    # Emit instructions; avoid duplicate labels
    instrs = []
    emitted_label = set()

    for idx, name in enumerate(order):
        if name in target_labels and name not in emitted_label:
            instrs.append({"label": name})
            emitted_label.add(name)

        instrs.extend(block_by_name[name]["instrs"])

        # If block has no terminator, ensure fallthrough matches intended target
        if not has_terminator(name) and name in reach:
            ft = textual_fallthrough(name)
            next_name = order[idx + 1] if idx + 1 < len(order) else None
            if ft is not None and ft != next_name:
                instrs.append({"op": "jmp", "labels": [ft]})

    out = {"name": cfg.get("name"), "instrs": instrs}
    if "args" in cfg:
        out["args"] = cfg["args"]
    if "type" in cfg:
        out["type"] = cfg["type"]
    return out
