# Exploration Camp private-invite orientation V2 R3

R3 is the controller-safe candidate identity. It pins runtime and evidence to commit `6e4a4d0`, so independent
evaluation cannot accidentally read later uncommitted work from the integration tree.

R1's original hashes were correct for that commit. R2 is retained only to audit the mistaken dirty-worktree
comparison. R3 changes no runtime, browser evidence, fixture, human result, or acceptance criterion.
