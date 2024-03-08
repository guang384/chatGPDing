#!/bin/bash

# Get the list of processes matching a specific pattern
process_list=$(ps -ef | grep "python main.py" | grep -v grep | awk '{print $2}')

# Iterate over the process list and kill each process
for pid in $process_list
do
    kill -9 $pid
    echo "Killed process with ID: $pid"
done
