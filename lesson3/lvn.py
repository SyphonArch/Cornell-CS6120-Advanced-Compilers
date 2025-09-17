"""
Local Value Numbering (LVN).

Performs:
- common subexpression elimination (CSE),
- copy propagation (argument canonicalization),
- constant folding,
- simple algebraic identities.
"""

import sys
import json

from lesson2.build_cfg_lesson3 import build_cfg_for_function
from helpers import instr_uses, instr_def, linearize_cfg

# Core operator groups
BINARY_OPS = {
    "add", "sub", "mul", "div",
    "eq", "lt", "le", "gt", "ge",
    "and", "or",
}
UNARY_OPS = {"not"}
COMMUTATIVE_OPS = {"add", "mul", "eq", "and", "or"}


def try_const_fold(op, consts):
    """
    Try folding a core op whose arguments are all constants.

    Returns (ok, value):
      - ok=True  -> folding succeeded; `value` is the folded constant (int 0/1 for bools).
      - ok=False -> folding not performed (e.g., div-by-zero). `value` is None.
    """
    try:
        if op in BINARY_OPS:
            a, b = consts
            if op == "add": return True, a + b
            if op == "sub": return True, a - b
            if op == "mul": return True, a * b
            if op == "div": return True, a // b
            if op == "eq": return True, a == b
            if op == "lt": return True, a < b
            if op == "le": return True, a <= b
            if op == "gt": return True, a > b
            if op == "ge": return True, a >= b
            if op == "and": return True, a and b
            if op == "or":  return True, a or b
        if op in UNARY_OPS:
            (a,) = consts
            if op == "not": return True, not a
    except Exception:
        pass
    return False, None


def normalize_commutative(op, arg_value_numbers):
    """
    If `op` is commutative, return (op, tuple(sorted(arg_value_numbers))).
    Otherwise return (op, tuple(arg_value_numbers)).
    """
    if op in COMMUTATIVE_OPS:
        return op, tuple(sorted(arg_value_numbers))
    return op, tuple(arg_value_numbers)


def apply_identities(op, arg_nums, arg_consts):
    """
    Apply simple algebraic identities. Assumes `arg_nums` have already been
    normalized for commutative ops via `normalize_commutative`.

    Returns one of:
      ("const", c)      -> expression is the constant c
      ("num",  n)       -> expression equals the value numbered n (i.e., a copy)
      ("key", op, nums) -> keep as is; use this key for CSE
    """
    if op == "add":
        if arg_consts[1] == 0: return ("num", arg_nums[0])  # x + 0 = x
        if arg_consts[0] == 0: return ("num", arg_nums[1])  # 0 + x = x
    elif op == "sub":
        if arg_consts[1] == 0: return ("num", arg_nums[0])  # x - 0 = x
    elif op == "mul":
        if arg_consts[0] == 0 or arg_consts[1] == 0: return ("const", 0)  # 0 * x = 0
        if arg_consts[0] == 1: return ("num", arg_nums[1])  # 1 * x = x
        if arg_consts[1] == 1: return ("num", arg_nums[0])  # x * 1 = x
    elif op == "and":
        if arg_consts[0] == 0 or arg_consts[1] == 0: return ("const", 0)  # 0 and x = 0
        if arg_consts[0] == 1: return ("num", arg_nums[1])  # 1 and x = x
        if arg_consts[1] == 1: return ("num", arg_nums[0])  # x and 1 = x
    elif op == "or":
        if arg_consts[0] == 1 or arg_consts[1] == 1: return ("const", 1)  # 1 or x = 1
        if arg_consts[0] == 0: return ("num", arg_nums[1])  # 0 or x = x
        if arg_consts[1] == 0: return ("num", arg_nums[0])  # x or 0 = x

    return ("key", op, tuple(arg_nums))


def lvn_block(block):
    """
    LVN over one basic block. Rewrites instructions while tracking value numbers.

    Data structures:
      table:    maps (op, arg_value_numbers) and ("const", c) to a value number.
      var2num:  maps variable name -> value number.
      num2var:  maps value number -> a chosen canonical variable name.
      num2const:maps value number -> constant value (when known).

    The canonical variable is the name we prefer to use when substituting
    equivalent values back into instructions.
    """
    new_instrs = []
    table = {}
    var2num = {}
    num2var = {}
    num2const = {}
    next_num = 1

    def fresh_num():
        nonlocal next_num
        n = next_num
        next_num += 1
        return n

    def ensure_var_number(var_name):
        """Give `var_name` a value number if it doesn't have one yet."""
        if var_name not in var2num:
            n = fresh_num()
            var2num[var_name] = n
            table[("var", var_name)] = n
            num2var[n] = var_name
        return var2num[var_name]

    def canonical_var_of_num(valnum, default_name=None):
        """
        Return the canonical variable name for value number `valnum`.
        If none is recorded yet, return `default_name`.
        """
        return num2var.get(valnum, default_name)

    def record_const(c, prefer_name=None):
        """Map constant `c` to a value number; prefer `prefer_name` as its canonical var."""
        key = ("const", c)
        if key in table:
            return table[key]
        n = fresh_num()
        table[key] = n
        if prefer_name is not None:
            num2var[n] = prefer_name
        num2const[n] = c
        return n

    for instr in block["instrs"]:
        if "op" not in instr:
            new_instrs.append(instr)
            continue

        op = instr["op"]
        dest = instr_def(instr)
        args = list(instr_uses(instr))

        # const: record constant value and keep the instruction
        if op == "const" and dest is not None:
            c = instr.get("value")
            n = record_const(c, prefer_name=dest)
            var2num[dest] = n
            new_instrs.append(dict(instr))
            num2var[n] = dest
            continue

        # id: copy; dest gets the source's value number
        if op == "id" and dest is not None and len(args) == 1:
            src = args[0]
            n = ensure_var_number(src)
            var2num[dest] = n
            new_instrs.append(dict(instr))
            if n not in num2var:
                num2var[n] = src
            continue

        # Only transform core unary/binary ops; others pass through
        if op not in BINARY_OPS and op not in UNARY_OPS:
            new_instrs.append(dict(instr))
            continue

        # Map args to value numbers, constants, and canonical names
        arg_nums = []
        arg_consts = []
        canon_args = []
        for a in args:
            n = ensure_var_number(a)
            arg_nums.append(n)
            arg_consts.append(num2const.get(n))
            canon_args.append(canonical_var_of_num(n, a))

        # If all args are constants, try to fold
        if (op in UNARY_OPS and arg_consts[0] is not None) or \
           (op in BINARY_OPS and all(c is not None for c in arg_consts)):
            ok, val = try_const_fold(op, tuple(arg_consts if op in BINARY_OPS else arg_consts[:1]))
            if ok and dest is not None:
                n = record_const(val, prefer_name=dest)
                var2num[dest] = n
                new_instrs.append({"op": "const", "dest": dest, "type": instr.get("type"), "value": val})
                num2var[n] = dest
                continue

        # Normalize commutative ops before identities and CSE
        op_norm, norm_nums = normalize_commutative(op, arg_nums)
        if op in BINARY_OPS:
            # Apply identities on normalized operands
            kind = apply_identities(op_norm, tuple(norm_nums), tuple(arg_consts))
            if kind[0] == "const" and dest is not None:
                n = record_const(kind[1], prefer_name=dest)
                var2num[dest] = n
                new_instrs.append({"op": "const", "dest": dest, "type": instr.get("type"), "value": kind[1]})
                num2var[n] = dest
                continue
            elif kind[0] == "num" and dest is not None:
                # Becomes a copy from an existing value
                n = kind[1]
                var2num[dest] = n
                rep = canonical_var_of_num(n, dest)
                new_instrs.append({"op": "id", "args": [rep], "dest": dest, "type": instr.get("type")})
                num2var.setdefault(n, rep)
                continue
            else:
                # Use normalized numbers for the key and for arg rewriting
                arg_nums = list(norm_nums)
                canon_args = [canonical_var_of_num(n, canon_args[i] if i < len(canon_args) else None)
                              for i, n in enumerate(arg_nums)]
                op = op_norm

        # Common subexpression elimination via the value key
        if dest is not None:
            if op in UNARY_OPS:
                value_key = (op, arg_nums[0])
            else:  # binary
                value_key = (op, tuple(arg_nums))

            if value_key in table:
                n = table[value_key]
                var2num[dest] = n
                rep = canonical_var_of_num(n, dest)
                new_instrs.append({"op": "id", "args": [rep], "dest": dest, "type": instr.get("type")})
                num2var.setdefault(n, rep)
            else:
                n = fresh_num()
                table[value_key] = n
                var2num[dest] = n
                new_i = dict(instr)
                if canon_args:
                    new_i["args"] = canon_args
                new_instrs.append(new_i)
                num2var[n] = dest
        else:
            # No dest: just rewrite args to canonical names
            new_i = dict(instr)
            if canon_args:
                new_i["args"] = canon_args
            new_instrs.append(new_i)

    return new_instrs


def main():
    prog = json.load(sys.stdin)
    out_prog = {"functions": []}

    for func in prog.get("functions", []):
        cfg = build_cfg_for_function(func)
        for block in cfg["blocks"]:
            block["instrs"] = lvn_block(block)
        out_prog["functions"].append(linearize_cfg(cfg))

    json.dump(out_prog, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
