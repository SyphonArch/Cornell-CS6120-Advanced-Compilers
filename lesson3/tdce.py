"""
Trivial Dead Code Elimination (DCE).

Global: remove assignments whose result is never used in the function.
Local: within each block, remove assignments that are dead at that point.

Only instructions with a `dest` are considered. Others are left as they are.
"""

import sys
import json

from lesson2.build_cfg_lesson3 import build_cfg_for_function
from helpers import instr_uses, instr_def, linearize_cfg, reachable_block_names

def remove_globally_unused_instructions(cfg):
    reachable = reachable_block_names(cfg)
    name_to_block = {b["name"]: b for b in cfg["blocks"]}

    # Only count uses in reachable blocks
    used = set()
    for name in reachable:
        for instruction in name_to_block[name]["instrs"]:
            used |= set(instr_uses(instruction))

    changed = False
    for name in reachable:
        block = name_to_block[name]
        kept = []
        for instruction in block["instrs"]:
            dest = instr_def(instruction)
            op = instruction.get("op")
            if dest and dest not in used:
                # Do not delete possibly side-effecting calls
                if op == "call":
                    kept.append(instruction)
                    continue
                changed = True
                continue
            kept.append(instruction)
        block["instrs"] = kept

    return changed


def remove_locally_killed_instructions(cfg):
    reachable = reachable_block_names(cfg)
    name_to_block = {b["name"]: b for b in cfg["blocks"]}

    changed = False
    for name in reachable:
        block = name_to_block[name]
        redefined = set()
        used_since_redef = set()
        kept_rev = []

        for instr in reversed(block["instrs"]):
            dest = instr_def(instr)
            uses = instr_uses(instr)

            # Drop trivial self-copy (e.g., "i = id i")
            if dest is not None and instr.get("op") == "id" and len(uses) == 1 and uses[0] == dest:
                changed = True
                continue

            if dest is None:
                kept_rev.append(instr)
                for u in uses:
                    if u in redefined:
                        used_since_redef.add(u)
                continue

            was_redef = dest in redefined
            redefined.add(dest)

            # Record uses (including possible self-use)
            for u in uses:
                if u in redefined:
                    used_since_redef.add(u)

            self_use = dest in uses

            # If a later def overwrote it with no intervening use, drop it…
            if was_redef and dest not in used_since_redef:
                # …but keep if this instruction depends on the previous value (self-use),
                # or if it is a call (side effects).
                if self_use or (instr.get("op") == "call"):
                    pass
                else:
                    changed = True
                    continue

            kept_rev.append(instr)

            if not self_use:
                used_since_redef.discard(dest)

        block["instrs"] = list(reversed(kept_rev))

    return changed


def main():
    prog = json.load(sys.stdin)

    results = []
    for function in prog.get("functions", []):
        cfg = build_cfg_for_function(function)

        # Iteratively apply global and local DCE until no more changes
        while True:
            changed = False
            changed |= remove_globally_unused_instructions(cfg)
            changed |= remove_locally_killed_instructions(cfg)
            if not changed:
                break

        results.append(cfg)

    out_prog = {"functions": []}
    for cfg in results:
        out_prog["functions"].append(linearize_cfg(cfg))

    json.dump(out_prog, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
