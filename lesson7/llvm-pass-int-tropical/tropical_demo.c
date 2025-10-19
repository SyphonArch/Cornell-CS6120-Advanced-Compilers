#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

static int tropical_poly(int x) {
  // 3*x*x + 5*x + 2
  return 3u * x * x + 5u * x + 2u;
}

static void tropical_matmul2x2(int C[2][2], const int A[2][2], const int B[2][2]) {
  // C = A * B
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 2; j++) {
      int acc = 0;
      for (int k = 0; k < 2; k++) {
        acc = acc + A[i][k] * B[k][j];
      }
      C[i][j] = acc;
    }
  }
}

int main(int argc, char **argv) {
  int x = (argc > 1) ? (int)strtoul(argv[1], 0, 10) : 4;

  int p = tropical_poly(x);
  printf("poly(x) = 3*x*x + 5*x + 2\n");
  printf("poly(%u) = %u\n", x, p);

  int A[2][2] = { {1, 9}, {2, 0} };
  int B[2][2] = { {3, 4}, {5, 6} };
  int C[2][2];
  printf("A = [[%d, %d], [%d, %d]]\n", A[0][0], A[0][1], A[1][0], A[1][1]);
  printf("B = [[%d, %d], [%d, %d]]\n", B[0][0], B[0][1], B[1][0], B[1][1]);
  tropical_matmul2x2(C, A, B);
  printf("C = A x B = [[%d, %d], [%d, %d]]\n", C[0][0], C[0][1], C[1][0], C[1][1]);
  return 0;
}
