#!/bin/bash

set -- *.jsonl
ok=true
for file do
  echo "$file"
  sort -o "$file" -u --radixsort -- "$file" || ok=false
done
