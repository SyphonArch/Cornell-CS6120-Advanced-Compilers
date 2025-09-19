# reaching_defs.py
from typing import Set, Tuple
from DFA import DataFlowFact, DFA, Direction, Seed
from lesson3 import helpers

def annotate_def_sites(cfg: dict) -> Set[Tuple[str, str]]:
    universe: Set[Tuple[str, str]] = set()
    for b in cfg["blocks"]:
        bname = b["name"]
        for i, ins in enumerate(b["instrs"]):
            d = helpers.instr_def(ins)
            if d is not None:
                def_id = f"{d}@{bname}:{i}"
                ins["_def_id"] = def_id
                universe.add((d, def_id))
    return universe

class ReachingDefs(DataFlowFact):
    UNIVERSE: Set[Tuple[str, str]] = set()

    def __init__(self, defs: Set[Tuple[str, str]] = None):
        self.s = frozenset(defs or set())

    def merge(self, other: "ReachingDefs") -> "ReachingDefs":
        return ReachingDefs(set(self.s) | set(other.s))

    def transfer(self, instr: dict) -> "ReachingDefs":
        cur = set(self.s)
        d = helpers.instr_def(instr)
        if d is not None:
            cur = {pair for pair in cur if pair[0] != d}
            def_id = instr.get("_def_id")
            if def_id is not None:
                cur.add((d, def_id))
        return ReachingDefs(cur)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ReachingDefs) and self.s == other.s

    @classmethod
    def top(cls) -> "ReachingDefs":
        return ReachingDefs(set())

    @classmethod
    def bottom(cls) -> "ReachingDefs":
        return ReachingDefs(set(cls.UNIVERSE))

def run_analysis(cfg: dict) -> DFA:
    ReachingDefs.UNIVERSE = annotate_def_sites(cfg)
    dfa = DFA(cfg, Direction.FORWARD, ReachingDefs, entry=Seed.KEEP)
    dfa.run()
    return dfa

if __name__ == "__main__":
    import sys, json
    from lesson2.build_cfg_lesson3 import build_cfg_for_function

    prog = json.load(sys.stdin)
    for f in prog.get("functions", []):
        cfg = build_cfg_for_function(f)
        dfa = run_analysis(cfg)

        def fmt_defs(fact):
            if not fact.s:
                return "∅"
            by_var = {}
            for var, def_id in fact.s:
                by_var.setdefault(var, []).append(def_id)
            out = []
            for var in sorted(by_var):
                defs = sorted(by_var[var])
                if len(defs) == 1 and defs[0].startswith(var + "@"):
                    out.append(var)
                else:
                    for did in defs:
                        loc = did.split("@", 1)[1] if did.startswith(var + "@") else did
                        out.append(f"{var}@{loc}")
            return ", ".join(out)

        print("================================")
        print("Function", cfg["name"])
        for bi, b in enumerate(cfg["blocks"]):
            print(f"Block {b['name']}")
            print("  IN :", fmt_defs(dfa.in_lattice[bi]))
            print("  OUT:", fmt_defs(dfa.out_lattice[bi]))
