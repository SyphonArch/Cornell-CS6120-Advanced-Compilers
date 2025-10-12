# Lesson 6 – Static Single Assignment (SSA)

This directory implements bidirectional SSA transformations for Bril programs using the set/get (upsilon/phi) representation rather than traditional phi-nodes.

## Core Implementation

### **`to_ssa.py`**
Converts Bril functions to SSA form using dominance frontier-based phi placement and dominance tree traversal for variable renaming. Uses `set`/`get` instructions and generates `undef` instructions for uninitialized variable paths.

### **`from_ssa.py`**
Converts SSA-form Bril programs back to standard form by replacing `get` instructions with assignments and inserting copy instructions before predecessor blocks for each `set`.

### **`is_ssa.py`**
Validates that Bril programs are in proper SSA form (provided script.)

### **`test_ssa.py`**
Test harness that performs round-trip testing, validates correctness using `brili`, measures instruction count overhead, and generates `results.json` with performance metrics.

## Usage

### Basic Transformations

```bash
# Convert to SSA form
bril2json < program.bril | python to_ssa.py | bril2txt

# Convert from SSA form
bril2json < ssa_program.bril | python from_ssa.py | bril2txt

# Check if program is in SSA form
bril2json < program.bril | python is_ssa.py
```

### Comprehensive Testing

```bash
# Test single benchmark file
python test_ssa.py benchmarks/core/graycode.bril

# Test all core benchmarks
python test_ssa.py benchmarks/core

# Test multiple benchmark suites
python test_ssa.py benchmarks/core benchmarks/float benchmarks/long benchmarks/mem benchmarks/mixed

# Check ./tmp/ for intermediate files and results.json for detailed metrics
```

## Results

```
Target programs: 122
100%|█████████████████████████████| 122/122 [02:15<00:00,  1.11s/it]
Successful round trips: 122/122
Static Instr Increase (Geometric Mean): 1.13x
Dynamic Instr Increase (Geometric Mean): 1.14x
```

Note: `./benchmarks/core/tail-call.bril` was excluded from testing as it is designed to fail on `brili`.

## Implementation Details

- Uses dominance frontier analysis for phi placement with live-in filtering
- Handles loop headers that are also function entry blocks via preheader insertion
- Implements set/get instructions following the upsilon/phi approach
- Generates appropriate `undef` instructions for uninitialized paths

## Dependencies

- **Python 3.x** with standard library
- **Bril toolchain** (`bril2json`, `bril2txt`)
- **Deno runtime** for `brili` interpreter
- **tqdm** for progress bars during testing

## Testing

The test harness validates correctness by executing original, SSA, and round-trip versions with identical arguments and comparing outputs. It also measures static and dynamic instruction count overhead.

**Debugging**: Intermediate files (original, SSA, and round-trip versions) are stored in `./tmp/` for inspection. The `results.json` file contains detailed per-program metrics including verdicts, instruction counts, and outputs.