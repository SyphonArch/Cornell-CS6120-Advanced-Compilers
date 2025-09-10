"""Given a Bril program, fold constant additions recursively."""

import json
import sys

def fold_constants(instructions):
    """Fold constant additions until no more folding is possible."""
    const_values = {}
    changed = True

    while changed:
        changed = False
        new_instructions = []

        # Single pass to both record constants and fold additions
        for instruction in instructions:
            # Register constant values
            if instruction["op"] == "const" and instruction.get("type") == "int":
                const_values[instruction["dest"]] = instruction["value"]
                new_instructions.append(instruction)

            # Fold constant additions
            elif instruction["op"] == "add" and instruction.get("type") == "int":
                a, b = instruction["args"]
                if a in const_values and b in const_values:
                    folded_val = const_values[a] + const_values[b]
                    new_instructions.append({
                        "dest": instruction["dest"],
                        "op": "const",
                        "type": "int",
                        "value": folded_val
                    })
                    const_values[instruction["dest"]] = folded_val
                    changed = True
                else:
                    new_instructions.append(instruction)
            else:
                new_instructions.append(instruction)

        instructions = new_instructions

    return instructions


def eliminate_dead_code(instrs):
    """Eliminate dead code from the instruction list."""
    live = set()
    kept = []
    side_effect_ops = {'br', 'call', 'ret', 'print'}

    for instr in reversed(instrs):
        op = instr.get("op")
        dest = instr.get("dest")
        args = instr.get("args", [])
        has_side_effect = op in side_effect_ops

        if has_side_effect or (dest is not None and dest in live):
            kept.append(instr)
            live.update(args)

    kept.reverse()
    return kept


def optimize_const_adds(bril):
    """Optimize the Bril program by folding constant additions and eliminating dead code"""
    new_bril = {
        **bril,
        "functions": []
    }
    for function in bril["functions"]:
        new_function = {**function}
        instructions = fold_constants(function["instrs"])
        instructions = eliminate_dead_code(instructions)
        new_function["instrs"] = instructions
        new_bril["functions"].append(new_function)
    return new_bril


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    optimized = optimize_const_adds(prog)
    json.dump(optimized, sys.stdout, indent=2)