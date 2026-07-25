# Archived rounds 1-2 (tool-enabled experiments)

Earlier experiment rounds ran with tool access (Bash) available to the models
via Claude Code subagents: an easy 8-bug fix, a build-to-spec cache, a web
lookup, and a deliberately hard calendar-recurrence engine (spec + reference +
independent oracle + fuzz validation included here). Their headline lesson is
why the core MERC tasks forbid tools: with execution available, every tier
self-verified its way to perfect scores on even the hardest build task, and
only cost separated configurations.

These runs are NOT part of the core dataset (different conditions). Raw
workflow outputs are included for transparency. The subtle-bugs task (E) and
the six-puzzle set (T5B) from round 2 ARE in the core dataset as records with
sample tag r2, with tool availability flagged in notes where applicable.
