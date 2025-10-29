"""LICM for Bril: find loops, add preheaders, hoist safe invariants."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional
import sys
import json
import os
import types

# Import CFG, dominance, helpers
from lesson2.build_cfg_lesson3 import build_cfg_for_function
from lesson3 import helpers_lesson5 as helpers
from lesson5 import dominance_lesson6 as dom


# Make lesson4 importable and alias lesson3.helpers for reaching_defs
_HERE = os.path.dirname(__file__)
_LESSON4_DIR = os.path.join(_HERE, "lesson4")
if _LESSON4_DIR not in sys.path:
    sys.path.insert(0, _LESSON4_DIR)

# Provide a shim so reaching_defs can import lesson3.helpers
if "lesson3" not in sys.modules:
    sys.modules["lesson3"] = types.ModuleType("lesson3")
setattr(sys.modules["lesson3"], "helpers", helpers)

# Import reaching defs
from reaching_defs import run_analysis as run_reaching_defs
from lesson6.to_ssa import main as to_ssa_main
from lesson6.from_ssa import main as from_ssa_main


# Pure ops considered safe to hoist (no effects). Div is excluded.
PURE_OPS: Set[str] = {
    "const", "id",
    "add", "sub", "mul",
    "and", "or", "xor", "not",
    "eq", "lt", "le", "gt", "ge",
}

TERMINATORS = {"br", "jmp", "ret"}


@dataclass(frozen=True)
class InstrLoc:
    block: str
    index: int

    @property
    def def_id(self) -> str:
        return f"{self.block}:{self.index}"


def compute_dom_sets(cfg: dict) -> Dict[str, Set[str]]:
    return dom.compute_dominators(cfg)


def preds_by_name(cfg: dict) -> Dict[str, List[str]]:
    return cfg["cfg"].get("preds", {})


def succs_by_name(cfg: dict) -> Dict[str, List[str]]:
    return cfg["cfg"].get("edges", {})


def block_map(cfg: dict) -> Dict[str, dict]:
    return {b["name"]: b for b in cfg["blocks"]}


def find_back_edges(cfg: dict, dom_sets: Dict[str, Set[str]]) -> List[Tuple[str, str]]:
    """Return list of back edges (tail, head) where head dominates tail."""
    backs: List[Tuple[str, str]] = []
    edges = succs_by_name(cfg)
    for u, vs in edges.items():
        for v in vs:
            if v in dom_sets.get(u, set()):
                backs.append((u, v))
    return backs


def natural_loop(cfg: dict, tail: str, head: str, dom_sets: Dict[str, Set[str]]) -> Set[str]:
    """Natural loop of back-edge tail -> head (only nodes dom'ed by head)."""
    loop: Set[str] = {head}
    work: List[str] = [tail]
    preds = preds_by_name(cfg)
    while work:
        x = work.pop()
        if x not in loop:
            # Only include nodes dominated by the header
            if head not in dom_sets.get(x, set()):
                continue
            loop.add(x)
            for p in preds.get(x, []):
                if p != head:
                    work.append(p)
    return loop


def loop_exits(cfg: dict, loop_nodes: Set[str]) -> Set[str]:
    """Blocks in the loop that jump outside."""
    exits: Set[str] = set()
    edges = succs_by_name(cfg)
    for n in loop_nodes:
        for s in edges.get(n, []):
            if s not in loop_nodes:
                exits.add(n)
    return exits


def ensure_preheader(cfg: dict, loop_nodes: Set[str], header: str) -> str:
    """Create a fresh preheader and retarget outside preds to it."""
    bmap = block_map(cfg)
    preds = preds_by_name(cfg)
    edges = succs_by_name(cfg)

    non_loop_preds = [p for p in preds.get(header, []) if p not in loop_nodes]

    # Create a fresh preheader block before header
    idx = 0
    base = f"{header}.preheader"
    pre = base
    existing = set(bmap.keys())
    while pre in existing:
        idx += 1
        pre = f"{base}.{idx}"

    pre_block = {"name": pre, "instrs": [{"op": "jmp", "labels": [header]}]}
    cfg["blocks"].insert(0, pre_block)
    bmap[pre] = pre_block

    # Update CFG maps
    cfg["cfg"].setdefault("edges", {}).setdefault(pre, [])
    cfg["cfg"]["edges"][pre] = [header]
    cfg["cfg"].setdefault("preds", {}).setdefault(pre, [])
    cfg["cfg"]["preds"].setdefault(header, [])
    if pre not in cfg["cfg"]["preds"][header]:
        cfg["cfg"]["preds"][header].insert(0, pre)

    # Rewire all non-loop predecessors from header -> pre
    for p in list(non_loop_preds):
        # Update terminator labels if present
        body = bmap[p]["instrs"]
        if body and body[-1].get("op") in {"br", "jmp"}:
            term = body[-1]
            labels = term.get("labels", [])
            new_labels = [pre if lab == header else lab for lab in labels]
            term["labels"] = new_labels
        else:
            # Add an explicit jump if it relied on fallthrough to header
            # We conservatively add a jmp to pre; linearize_cfg will tidy layout
            body.append({"op": "jmp", "labels": [pre]})

        # Update edges map
        if p in edges:
            cfg["cfg"]["edges"][p] = [pre if d == header else d for d in cfg["cfg"]["edges"][p]]
        else:
            cfg["cfg"]["edges"][p] = [pre]

        # Update preds map
        if header in cfg["cfg"]["preds"]:
            cfg["cfg"]["preds"][header] = [x for x in cfg["cfg"]["preds"][header] if x != p]
        cfg["cfg"]["preds"].setdefault(pre, [])
        if p not in cfg["cfg"]["preds"][pre]:
            cfg["cfg"]["preds"][pre].append(p)

    return pre


def annotate_def_map(cfg: dict) -> Dict[str, InstrLoc]:
    """Map reaching-def ids to instruction locations."""
    m: Dict[str, InstrLoc] = {}
    for b in cfg["blocks"]:
        bname = b["name"]
        for i, ins in enumerate(b["instrs"]):
            did = ins.get("_def_id")
            if did:
                # keep full key (e.g., "x@B3:5")
                m[did] = InstrLoc(bname, i)
    return m


def defs_of_var_at(fact, var: str) -> Set[str]:
    """Get reaching def ids for a variable at a program point."""
    # The ReachingDefs fact stores a frozenset of (var, def_id) pairs in `.s`.
    pairs = getattr(fact, "s", frozenset())
    return {did for v, did in pairs if v == var}


def instr_is_pure(instr: dict) -> bool:
    op = instr.get("op")
    if op is None:
        return False
    if op in PURE_OPS:
        # Avoid speculative divide for safety (excluded from PURE_OPS already)
        return True
    return False


def no_other_defs_in_loop(cfg: dict, loop_nodes: Set[str], var: str) -> bool:
    count = 0
    for b in cfg["blocks"]:
        if b["name"] not in loop_nodes:
            continue
        for ins in b["instrs"]:
            if ins.get("dest") == var:
                count += 1
                if count > 1:
                    return False
    return True


def block_dominates_all(dom_sets: Dict[str, Set[str]], blk: str, targets: Set[str]) -> bool:
    return all(blk in dom_sets.get(t, set()) for t in targets)


def hoist_instructions(cfg: dict, preheader: str, items: List[InstrLoc]):
    """Move given instructions into the preheader."""
    bmap = block_map(cfg)
    pre_b = bmap[preheader]
    # Find insertion point: before any final terminator
    insert_at = len(pre_b["instrs"])
    if insert_at > 0 and pre_b["instrs"][-1].get("op") in TERMINATORS:
        insert_at -= 1

    # Sort by original order for determinism
    items_sorted = sorted(items, key=lambda loc: (loc.block, loc.index))

    # Extract and append
    moved = []
    for loc in items_sorted:
        src_b = bmap[loc.block]
        if loc.index < 0 or loc.index >= len(src_b["instrs"]):
            continue
        ins = src_b["instrs"][loc.index]
        # Remove from source
        src_b["instrs"].pop(loc.index)
        # Adjust any later indices in same block
        for i, other in enumerate(items_sorted):
            if other.block == loc.block and other.index > loc.index:
                items_sorted[i] = InstrLoc(other.block, other.index - 1)
        moved.append(ins)

    # Insert into preheader in computed order
    pre_b["instrs"][insert_at:insert_at] = moved


def licm_function(func: dict) -> dict:
    cfg = build_cfg_for_function(func)
    if not cfg["blocks"]:
        return helpers.linearize_cfg(cfg)

    dom_sets = compute_dom_sets(cfg)
    backs = find_back_edges(cfg, dom_sets)
    if not backs:
        return helpers.linearize_cfg(cfg)

    for tail, head in backs:
        loop_nodes = natural_loop(cfg, tail, head, dom_sets)
        exits = loop_exits(cfg, loop_nodes)
        
        # Prepare reaching definitions analysis on current CFG state
        dfa = run_reaching_defs(cfg)
        def_map = annotate_def_map(cfg)
        name2idx = getattr(dfa, "name2idx", {b["name"]: i for i, b in enumerate(cfg["blocks"])})

        # Fixed-point to collect HOISTABLE invariants: operands are either
        # defined outside the loop or by already-hoistable instructions; and
        # the instruction passes safety checks.
        hoistable: Set[InstrLoc] = set()
        changed = True
        while changed:
            changed = False
            for bname in loop_nodes:
                if bname not in name2idx:
                    continue
                bi = name2idx[bname]
                b = cfg["blocks"][bi]
                for i, ins in enumerate(b["instrs"]):
                    if ins.get("op") in TERMINATORS:
                        continue
                    dest = ins.get("dest")
                    if dest is None:
                        continue
                    if not instr_is_pure(ins):
                        continue

                    # Operand readiness: either defined outside loop or by hoistable def inside loop
                    inst_facts = dfa.inst_in_lattice.get(name2idx[bname], [])
                    if i >= len(inst_facts):
                        continue
                    fact = inst_facts[i]
                    ready = True
                    for x in ins.get("args", []):
                        defs = defs_of_var_at(fact, x)
                        if not defs:
                            continue
                        # All reaching defs outside loop?
                        all_outside = True
                        def_inside: Optional[InstrLoc] = None
                        for did in defs:
                            try:
                                _, locs = did.split("@", 1)
                                blk, _ = locs.split(":", 1)
                            except ValueError:
                                blk = ""
                            if blk in loop_nodes:
                                all_outside = False
                                def_inside = def_map.get(did)
                                # don't break; still scan to ensure no other inside defs
                        if all_outside:
                            continue
                        # If exactly one inside def, it must already be hoistable
                        if len([1 for did in defs if def_map.get(did) and def_map.get(did).block in loop_nodes]) == 1:
                            if def_inside and def_inside in hoistable:
                                continue
                        ready = False
                        break

                    if not ready:
                        continue

                    # Safety: unique def of dest in loop and dominates exits
                    if not no_other_defs_in_loop(cfg, loop_nodes, dest):
                        continue
                    if not block_dominates_all(dom_sets, bname, exits):
                        continue

                    loc = InstrLoc(bname, i)
                    if loc not in hoistable:
                        hoistable.add(loc)
                        changed = True

        if hoistable:
            # Only hoist if there exists at least one incoming edge from outside the loop
            # (otherwise a preheader would be unreachable and hoisted defs would be undefined)
            non_loop_preds = [p for p in preds_by_name(cfg).get(head, []) if p not in loop_nodes]
            if not non_loop_preds:
                # Skip hoisting for loops entered only from inside (e.g., header is function entry)
                continue
            pre = ensure_preheader(cfg, loop_nodes, head)
            hoist_instructions(cfg, pre, sorted(list(hoistable), key=lambda l: (l.block, l.index)))

    # Re-linearize to produce a standard Bril function body
    return helpers.linearize_cfg(cfg)


def main(program: dict, use_ssa: bool = False) -> dict:
    """Apply LICM to a program. If use_ssa, run in SSA and convert back."""
    work_prog = program
    if use_ssa:
        work_prog = to_ssa_main(work_prog)

    out_funcs = []
    for f in work_prog.get("functions", []):
        out_funcs.append(licm_function(f))
    out_prog = {"functions": out_funcs}

    if use_ssa:
        out_prog = from_ssa_main(out_prog)
    return out_prog


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssa", action="store_true", help="Run LICM in SSA and convert back")
    args = parser.parse_args()
    prog = json.load(sys.stdin)
    json.dump(main(prog, use_ssa=args.ssa), sys.stdout)
