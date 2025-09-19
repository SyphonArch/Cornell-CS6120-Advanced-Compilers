from typing import Set, Optional
from DFA import DataFlowFact, DFA, Direction, Seed
from lesson3 import helpers


def compute_var_universe(cfg: dict) -> Set[str]:
    U: Set[str] = set()
    for b in cfg["blocks"]:
        for ins in b["instrs"]:
            d = helpers.instr_def(ins)
            if d:
                U.add(d)
            for u in helpers.instr_uses(ins):
                U.add(u)
    return U


class LiveVars(DataFlowFact):
    UNIVERSE_VARS: Set[str] = set()

    def __init__(self, elems: Optional[Set[str]] = None):
        self.s = frozenset(elems or set())

    def merge(self, other: "LiveVars") -> "LiveVars":
        return LiveVars(set(self.s) | set(other.s))

    def transfer(self, instr: dict) -> "LiveVars":
        cur = set(self.s)
        d = helpers.instr_def(instr)
        if d and d in cur:
            cur.remove(d)
        for u in helpers.instr_uses(instr):
            cur.add(u)
        return LiveVars(cur)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LiveVars) and self.s == other.s

    @classmethod
    def top(cls) -> "LiveVars":
        return LiveVars(set())

    @classmethod
    def bottom(cls) -> "LiveVars":
        return LiveVars(set(cls.UNIVERSE_VARS))


def run_analysis(cfg: dict) -> DFA:
    LiveVars.UNIVERSE_VARS = compute_var_universe(cfg)
    dfa = DFA(cfg, Direction.BACKWARD, LiveVars, exit=Seed.KEEP)
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
            ins = ", ".join(sorted(dfa.in_lattice[bi].s)) or "∅"
            outs = ", ".join(sorted(dfa.out_lattice[bi].s)) or "∅"
            print(f"Block {b['name']}")
            print(f"  IN : {ins}")
            print(f"  OUT: {outs}")
