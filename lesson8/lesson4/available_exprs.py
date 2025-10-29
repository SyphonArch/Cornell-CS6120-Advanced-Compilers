# available_exprs.py
from typing import Set, Tuple
from DFA import DataFlowFact, DFA, Direction, Seed
from lesson3 import helpers

PURE_OPS = {"add", "sub", "mul", "div", "and", "or", "eq", "lt", "gt"}


def is_pure_expr(instr: dict) -> bool:
    return ("dest" in instr) and (instr.get("op") in PURE_OPS) and bool(instr.get("args"))


def expr_key(instr: dict) -> Tuple[str, Tuple[str, ...]]:
    return (instr["op"], tuple(helpers.instr_uses(instr)))


def compute_universe(cfg: dict) -> Set[Tuple[str, Tuple[str, ...]]]:
    U: Set[Tuple[str, Tuple[str, ...]]] = set()
    for b in cfg["blocks"]:
        for ins in b["instrs"]:
            if is_pure_expr(ins):
                U.add(expr_key(ins))
    return U


class AvailableExprs(DataFlowFact):
    UNIVERSE: Set[Tuple[str, Tuple[str, ...]]] = set()

    def __init__(self, elems: Set[Tuple[str, Tuple[str, ...]]] = None):
        if elems is None:
            elems = AvailableExprs.UNIVERSE
        self.s = frozenset(elems)

    def merge(self, other: "AvailableExprs") -> "AvailableExprs":
        return AvailableExprs(set(self.s) & set(other.s))

    def transfer(self, instr: dict) -> "AvailableExprs":
        cur = set(self.s)
        d = helpers.instr_def(instr)
        if d:
            cur = {e for e in cur if d not in e[1]}
        if is_pure_expr(instr):
            cur.add(expr_key(instr))
        return AvailableExprs(cur)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AvailableExprs) and self.s == other.s

    @classmethod
    def top(cls) -> "AvailableExprs":
        return AvailableExprs(set(cls.UNIVERSE))

    @classmethod
    def bottom(cls) -> "AvailableExprs":
        return AvailableExprs(set())


def run_analysis(cfg: dict) -> DFA:
    AvailableExprs.UNIVERSE = compute_universe(cfg)
    dfa = DFA(cfg, Direction.FORWARD, AvailableExprs, entry=Seed.BOTTOM)
    dfa.run()
    return dfa


if __name__ == "__main__":
    import sys, json
    from lesson2.build_cfg_lesson3 import build_cfg_for_function

    prog = json.load(sys.stdin)
    for f in prog.get("functions", []):
        cfg = build_cfg_for_function(f)
        dfa = run_analysis(cfg)
        print("================================")
        print("Function", cfg["name"])
        for bi, b in enumerate(cfg["blocks"]):
            ins = ", ".join(map(str, sorted(dfa.in_lattice[bi].s))) or "∅"
            outs = ", ".join(map(str, sorted(dfa.out_lattice[bi].s))) or "∅"
            print(f"Block {b['name']}")
            print(f"  IN : {ins}")
            print(f"  OUT: {outs}")
