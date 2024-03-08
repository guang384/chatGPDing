#!/bin/bash

for file in start_GPDing_*\.sh; do
    if [ -x "$file" ]; then
        nohup ./$file > ${file/.sh/.log} 2>&1 &
    fi
done