import sys
import json

from lesson2.build_cfg_lesson3 import build_cfg_for_function
from lesson3 import helpers_lesson5


def from_ssa_function(func):
    """Convert a function from SSA form back to regular form using set/get semantics."""
    # Build CFG to analyze control flow
    cfg = build_cfg_for_function(func)
    
    # Step 1: Identify all shadow variables and their set/get instructions
    shadow_vars = {}  # shadow_var -> {"get": get_instr, "sets": [set_instrs]}
    
    # Find all get instructions (these define the shadow variables) 
    for block in cfg["blocks"]:
        for instr in block["instrs"]:
            if instr.get("op") == "get" and "dest" in instr:
                shadow_var = instr["dest"]
                shadow_vars[shadow_var] = {"get": instr, "sets": []}
    
    # Find all set instructions for these shadow variables
    for block_idx, block in enumerate(cfg["blocks"]):
        for instr_idx, instr in enumerate(block["instrs"]):
            if instr.get("op") == "set" and len(instr.get("args", [])) >= 2:
                shadow_var = instr["args"][0]
                source_var = instr["args"][1]
                if shadow_var in shadow_vars:
                    shadow_vars[shadow_var]["sets"].append({
                        "instr": instr,
                        "source": source_var,
                        "block_name": block["name"],
                        "block_idx": block_idx,
                        "instr_idx": instr_idx
                    })
    
    # Step 2: Transform each block by replacing set/get instructions
    new_blocks = []
    
    for block in cfg["blocks"]:
        new_instrs = []
        
        for instr in block["instrs"]:
            if instr.get("op") == "set":
                # Replace set instruction with identity copy
                # set shadow_var source_var becomes shadow_var = id source_var
                if len(instr.get("args", [])) >= 2:
                    shadow_var = instr["args"][0]
                    source_var = instr["args"][1]
                    
                    # Only process if this shadow variable is actually used (has a get)
                    if shadow_var in shadow_vars:
                        copy_instr = {
                            "op": "id",
                            "dest": shadow_var,
                            "args": [source_var],
                            "type": instr.get("type", "int")
                        }
                        new_instrs.append(copy_instr)
                # If malformed set or unused shadow variable, just remove it
                
            elif instr.get("op") == "get":
                # Remove get instructions entirely - the shadow variable should already
                # have the right value from the set instructions that were converted to copies
                pass
                
            else:
                # Regular instruction, keep as-is
                new_instrs.append(instr)
        
        new_block = block.copy()
        new_block["instrs"] = new_instrs
        new_blocks.append(new_block)
    
    # Reconstruct the function with linearized CFG
    cfg["blocks"] = new_blocks
    return helpers_lesson5.linearize_cfg(cfg)


def main(program):
    """Convert a Bril program from SSA form back to regular form."""
    out_program = {"functions": []}
    
    for func in program.get("functions", []):
        converted_func = from_ssa_function(func)
        out_program["functions"].append(converted_func)
    
    return out_program


if __name__ == '__main__':
    json.dump(main(json.load(sys.stdin)), sys.stdout)
