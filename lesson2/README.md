# Lesson 2 – Bril Transformation and Control-Flow Analysis

## Files

### Constant Addition Folding

- **`complex_add.bril`**  
  Example Bril program with several constant additions.
- **`complex_add.json`**  
  JSON form of the above program.
- **`const_add_fold.py`**  
  Python script that performs constant folding of addition operations:
  - Replaces chains of `add` instructions with equivalent `const` instructions.
  - Runs simple dead code elimination to remove unused values.
- **`complex_add_folded.json`**  
  Output of running `const_add_fold.py` on `complex_add.json`.

### Control Flow Graph Construction

- **`build_cfg.py`**  
  Python script to split a Bril function into basic blocks and build a control-flow graph.
- **`complex_add_cfg.json`**  
  CFG for `complex_add.json`.
- **`graycode.bril`**  
  Bril benchmark that generates a sequence of Gray codes, using as a test input for CFG construction.
- **`graycode.json`**  
  JSON form of the Gray code program.
- **`graycode_cfg.json`**  
  CFG for `graycode.json`.
