# int-tropical-semiring (LLVM 17)

## What I did

* Implemented an LLVM Function pass that redefines integer arithmetic to the signed tropical semiring (max, +):

  * integer add becomes signed max via `llvm.smax.*(a, b)`
  * integer multiply becomes integer add
  * only affects integers; floats/div/rem/shifts are unchanged

* Wrote a small C demo (`tropical_demo.c`) with:

  * a polynomial: `3*x*x + 5*x + 2`, which tropicalizes to `max{3+2x, 5+x, 2}` (e.g., x=4 -> 11)
  * a 2×2 matrix multiply, which tropicalizes to max-plus product: `C[i][j] = max_k(A[i][k] + B[k][j])`

* Observed outputs:

  * Original build: `poly(4) = 70`, `C = [[48, 58], [6, 8]]`
  * With pass (-O1): `poly(4) = 11`, `C = [[14, 15], [5, 6]]`

## Build

```
$ mkdir build
$ cd build
$ cmake ..
$ make
$ cd ..
```

## Run

Baseline (O0, no pass):

```
clang -O0 tropical_demo.c -o original
./original
# poly(x) = 3*x*x + 5*x + 2
# poly(4) = 70
# A = [[1, 9], [2, 0]]
# B = [[3, 4], [5, 6]]
# C = A x B = [[48, 58], [6, 8]]
```

With tropical pass (O1):

```
clang -O1 -fpass-plugin=`echo build/int_tropical/IntTropicalSemiring.*` tropical_demo.c -o modified
./modified
# poly(x) = 3*x*x + 5*x + 2
# poly(4) = 11
# A = [[1, 9], [2, 0]]
# B = [[3, 4], [5, 6]]
# C = A x B = [[14, 15], [5, 6]]
```

The resulting binaries accept an optional integer argument at runtime (e.g., 4).

## Mathematical meaning

In the tropical (max, +) semiring, matrix multiplication is defined algebraically as (A⊗B)[i][j] = max_k (A[i][k] + B[k][j]). This is the tropical analog of the usual matrix product where addition is replaced by max and multiplication by addition. Under this scheme, matrix composition corresponds to composition of paths in a weighted directed graph: the entry (A⊗B)[i][j] represents the maximum-weight path from node i to node j passing through an intermediate node k. Repeated tropical multiplication corresponds to computing the maximum-weight paths of increasing lengths, analogous to how repeated classical multiplication accumulates path costs multiplicatively. (why these outputs)

* Tropical semiring used here: (max, +) on integers.

* Polynomial 3*x*x + 5*x + 2 tropicalizes to max{3 + 2x, 5 + x, 2}.

  * At x=4: max{11, 9, 2} = 11.

* Matrix multiply becomes max-plus product:

  * Classical: C[i][j] = Σ_k A[i][k] * B[k][j]
  * Tropical:  C[i][j] = max_k (A[i][k] + B[k][j])
  * With A = [[1, 9], [2, 0]] and B = [[3, 4], [5, 6]]:

    * C[0][0] = max(1+3, 9+5) = max(4, 14) = 14
    * C[0][1] = max(1+4, 9+6) = max(5, 15) = 15
    * C[1][0] = max(2+3, 0+5) = max(5, 5) = 5
    * C[1][1] = max(2+4, 0+6) = max(6, 6) = 6

## Note on Implementation

* Because we shouldn't touch control flow, I added the following heuristic guard to prevent transforming arithmetic on the loop induction variable:

  ```cpp
  // Heuristic: don't rewrite loop-induction updates like `i = i + 1`.
  // We identify these by checking for constant integer operands equal to 1.
  if (auto *constInt = dyn_cast<ConstantInt>(rightOperand)) {
      if (constInt->isOne()) {
          continue; // Skip rewriting this addition
      }
  } else if (auto *constInt = dyn_cast<ConstantInt>(leftOperand)) {
      if (constInt->isOne()) {
          continue; // Skip rewriting this addition
      }
  }
  ```

  It's not perfect but works for this demo.

## Reflection

I found this pass interesting because it bridges compiler IR transformation with abstract algebra, revealing how purely syntactic instruction rewrites can yield mathematically meaningful but visibly different program behavior. It shows that compilers can explore alternative computational semantics --- here, transforming ordinary arithmetic into a tropical semiring --- without changing the syntax or structure of the source program.

## Generative AI

I used ChatGPT to quickly identify which LLVM headers and new pass manager APIs to include and how to register the pass correctly.
