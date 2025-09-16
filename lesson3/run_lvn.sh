#!/bin/sh
# Given a .bril file on stdin, perform dead code elimination and print a .bril file on stdout.
# Disclaimer: This script was written with the assistance of ChatGPT.

if [ $# -ne 1 ]; then
  echo "Usage: $0 <file.bril>" >&2
  exit 1
fi

input="$1"

bril2json < "$input" | python3 lvn.py | bril2txt
