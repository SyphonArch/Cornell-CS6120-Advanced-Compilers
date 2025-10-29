import sys
import json
from collections import defaultdict

from lesson2.build_cfg_lesson3 import build_cfg_for_function
from lesson3 import helpers_lesson5
from lesson5 import dominance_lesson6


def collect_variables(cfg):
    """Collect all variables used in the function."""
    variables = set()
    for block in cfg["blocks"]:
        for instr in block["instrs"]:
            if "dest" in instr:
                variables.add(instr["dest"])
            for arg in instr.get("args", []):
                variables.add(arg)
    return variables


def find_definitions(cfg):
    """Map var -> set of blocks where it's defined."""
    defs = defaultdict(set)
    
    for block in cfg["blocks"]:
        for instr in block["instrs"]:
            if "dest" in instr:
                defs[instr["dest"]].add(block["name"])
    
    return defs


def compute_dominance_frontier(cfg):
    """Compute dominance frontiers using dominance analysis."""
    dominators = dominance_lesson6.compute_dominators(cfg)
    entry = helpers_lesson5.entry_name(cfg)
    imm_dom = dominance_lesson6.compute_imm_dom(dominators, entry)
    df = dominance_lesson6.compute_dominance_frontier(cfg, imm_dom)
    return defaultdict(set, df)


def insert_phi_nodes(cfg, variables, func_args=None):
    """Insert phi nodes (as get dests) at DF blocks where the var is live-in."""
    defs = find_definitions(cfg)
    df = compute_dominance_frontier(cfg)
    phi_nodes = defaultdict(set)
    
    edges = cfg["cfg"].get("edges", {})
    live_in = defaultdict(set)

    # Backward dataflow liveness
    changed = True
    while changed:
        changed = False
        for block in cfg["blocks"]:
            name = block["name"]
            old_live = set(live_in[name])
            live_out = set()
            for succ in edges.get(name, []):
                live_out |= live_in[succ]
            used = set()
            defined = set()
            for instr in block["instrs"]:
                for arg in instr.get("args", []):
                    if arg not in defined:
                        used.add(arg)
                if "dest" in instr:
                    defined.add(instr["dest"])
            live_in[name] = used | (live_out - defined)
            if live_in[name] != old_live:
                changed = True

    for var in variables:
        def_blocks = set(defs[var])
        if func_args and var in func_args:
            entry = helpers_lesson5.entry_name(cfg)
            if entry:
                def_blocks.add(entry)
        if len(def_blocks) <= 1:
            continue
        worklist = list(def_blocks)
        phi_inserted = set()
        while worklist:
            block = worklist.pop()
            for df_block in df.get(block, []):
                if var not in phi_nodes[df_block] and df_block not in phi_inserted:
                    if var in live_in[df_block]:
                        phi_nodes[df_block].add(var)
                        phi_inserted.add(df_block)
                        if df_block not in def_blocks:
                            worklist.append(df_block)
    return phi_nodes


def variable_is_live_at_block(cfg, var, block_name):
    """Approximate liveness: used in block or successors (bounded depth)."""
    block_map = {b["name"]: b for b in cfg["blocks"]}
    
    if block_name not in block_map:
        return False
        
    block = block_map[block_name]
    for instr in block["instrs"]:
        if var in instr.get("args", []):
            return True

    edges = cfg["cfg"].get("edges", {})
    visited = set()
    
    def check_successors(curr_block, depth=0):
        if depth > 10 or curr_block in visited:
            return False
        visited.add(curr_block)
        
        for succ in edges.get(curr_block, []):
            if succ in block_map:
                succ_block = block_map[succ]
                for instr in succ_block["instrs"]:
                    if var in instr.get("args", []):
                        return True
                if check_successors(succ, depth + 1):
                    return True
        return False
    
    return check_successors(block_name)


def rename_variables(cfg, phi_nodes, variables, func_args, func):
    """Rename variables using the standard SSA algorithm with dominance tree traversal."""
    stacks = defaultdict(list)
    counters = defaultdict(int)
    processed_blocks = set()
    phi_var_names = {}
    var_types = {}
    
    for arg in func.get("args", []):
        var_types[arg["name"]] = arg["type"]
    
    for block in cfg["blocks"]:
        for instr in block["instrs"]:
            if "dest" in instr and "type" in instr:
                var_types[instr["dest"]] = instr["type"]
    
    for block_name, vars_needing_phi in phi_nodes.items():
        for var in vars_needing_phi:
            counters[var] += 1
            phi_var_names[(block_name, var)] = f"{var}.{counters[var]}"
    
    for arg in func_args:
        stacks[arg].append(arg)
    dominators = dominance_lesson6.compute_dominators(cfg)
    entry = helpers_lesson5.entry_name(cfg)
    imm_dom = dominance_lesson6.compute_imm_dom(dominators, entry)
    dom_tree = dominance_lesson6.build_dom_tree(imm_dom, entry)
    
    block_map = {b["name"]: b for b in cfg["blocks"]}
    
    def rename_block(block_name):
        """Recursively rename variables in dominance tree order."""
        if block_name not in block_map or block_name in processed_blocks:
            return
        
        processed_blocks.add(block_name)
        block = block_map[block_name]
        old_stack_sizes = {}
        
        new_instrs = []
        phi_vars_in_block = set(phi_nodes.get(block_name, []))
        
        # Entry block initialization: only if no predecessors (not a loop header)
        if block_name == entry and phi_vars_in_block:
            edges_all = cfg["cfg"].get("edges", {})
            has_predecessors = any(block_name in succs for succs in edges_all.values())
            if not has_predecessors:
                for var in phi_vars_in_block:
                    phi_var = phi_var_names[(block_name, var)]
                    if var in func_args:
                        init_instr = {
                            "op": "set",
                            "args": [phi_var, var]
                        }
                        new_instrs.append(init_instr)
        
        for var in phi_vars_in_block:
            phi_var = phi_var_names[(block_name, var)]
            
            get_instr = {
                "op": "get",
                "dest": phi_var,
                "type": var_types[var]
            }
            new_instrs.append(get_instr)
            
            if var not in old_stack_sizes:
                old_stack_sizes[var] = len(stacks[var])
            stacks[var].append(phi_var)
        terminators = {"br", "jmp", "ret"}
        
        for instr in block["instrs"]:
            new_instr = instr.copy()
            
            # Check if this is a terminator for set insertion
            is_terminator = instr.get("op") in terminators
            
            if is_terminator:
                # Insert set instructions before terminator
                edges = cfg["cfg"].get("edges", {})
                successors = edges.get(block_name, [])
                
                for succ in successors:
                    for var in phi_nodes.get(succ, []):
                        if stacks[var]:
                            current_version = stacks[var][-1]
                            phi_var = phi_var_names.get((succ, var), var)
                            set_instr = {
                                "op": "set",
                                "args": [phi_var, current_version]
                            }
                            new_instrs.append(set_instr)
                        else:
                            undef_var = f"{var}.undef"
                            phi_var = phi_var_names.get((succ, var), var)
                            undef_instr = {
                                "op": "undef",
                                "dest": undef_var,
                                "type": var_types[var]
                            }
                            set_instr = {
                                "op": "set",
                                "args": [phi_var, undef_var]
                            }
                            new_instrs.extend([undef_instr, set_instr])
            
            if "args" in instr:
                new_args = []
                for arg in instr["args"]:
                    if arg in variables and stacks[arg]:
                        new_args.append(stacks[arg][-1])
                    else:
                        new_args.append(arg)
                new_instr["args"] = new_args
            
            if "dest" in instr and instr["dest"] in variables:
                old_var = instr["dest"]
                counters[old_var] += 1
                new_var = f"{old_var}.{counters[old_var]}"
                new_instr["dest"] = new_var
                
                if old_var not in old_stack_sizes:
                    old_stack_sizes[old_var] = len(stacks[old_var])
                stacks[old_var].append(new_var)
            
            new_instrs.append(new_instr)
        
        # Handle fall-through blocks
        has_terminator = any(instr.get("op") in terminators for instr in block["instrs"])
        if not has_terminator:
            edges = cfg["cfg"].get("edges", {})
            successors = edges.get(block_name, [])
            
            for succ in successors:
                for var in phi_nodes.get(succ, []):
                    if stacks[var]:
                        current_version = stacks[var][-1]
                        phi_var = phi_var_names.get((succ, var), var)
                        set_instr = {
                            "op": "set",
                            "args": [phi_var, current_version]
                        }
                        new_instrs.append(set_instr)
                    else:
                        undef_var = f"{var}.undef"
                        phi_var = phi_var_names.get((succ, var), var)
                        undef_instr = {
                            "op": "undef",
                            "dest": undef_var,
                            "type": var_types[var]
                        }
                        set_instr = {
                            "op": "set",
                            "args": [phi_var, undef_var]
                        }
                        new_instrs.extend([undef_instr, set_instr])
        
        block["instrs"] = new_instrs
        
        for child in dom_tree.get(block_name, []):
            rename_block(child)
        
        for var, old_size in old_stack_sizes.items():
            while len(stacks[var]) > old_size:
                stacks[var].pop()
    
    if entry:
        rename_block(entry)


def to_ssa_function(func):
    """Convert a function to SSA form using set/get semantics and dominance analysis."""
    cfg = build_cfg_for_function(func)
    
    variables = collect_variables(cfg)
    func_args = {arg["name"] for arg in func.get("args", [])}
    
    reassigned_args = set()
    for block in cfg["blocks"]:
        for instr in block["instrs"]:
            if "dest" in instr and instr["dest"] in func_args:
                reassigned_args.add(instr["dest"])
    
    variables = (variables - func_args) | reassigned_args
    
    phi_nodes = insert_phi_nodes(cfg, variables, func_args)
    
    # If entry block has phi nodes for function parameters (loop header case),
    # create a preheader to initialize phi variables once on function entry.
    entry = helpers_lesson5.entry_name(cfg)
    if entry in phi_nodes and any(var in func_args for var in phi_nodes[entry]):
        pre_entry = f"{entry}.entry_init"
        pre_block = {
            "name": pre_entry,
            "instrs": [
                {"op": "jmp", "labels": [entry]}
            ]
        }
        cfg["blocks"].insert(0, pre_block)
        edges = cfg["cfg"].setdefault("edges", {})
        edges[pre_entry] = [entry]
        preds = cfg["cfg"].setdefault("preds", {})
        preds.setdefault(pre_entry, [])
        preds.setdefault(entry, [])
        if pre_entry not in preds[entry]:
            preds[entry].insert(0, pre_entry)
        cfg["cfg"]["entry"] = pre_entry

    rename_variables(cfg, phi_nodes, variables, func_args, func)
    
    return helpers_lesson5.linearize_cfg(cfg)


def main(program):
    """Convert a Bril program to SSA form."""
    out_program = {"functions": []}
    
    for func in program.get("functions", []):
        ssa_func = to_ssa_function(func)
        out_program["functions"].append(ssa_func)
    
    return out_program


if __name__ == '__main__':
    json.dump(main(json.load(sys.stdin)), sys.stdout)
