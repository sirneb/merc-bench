#!/bin/bash
P=/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench/candidates/simulation-1/pilot
cd /tmp
python3 $P/pilot.py claude-haiku-4-5 haiku low
python3 $P/pilot.py claude-sonnet-5 sonnet medium
python3 $P/pilot.py claude-opus-5-5 opus55 medium
python3 $P/pilot.py claude-fable-5-1 fable51 medium
echo ALL_DONE
