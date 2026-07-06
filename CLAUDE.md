## Parallel workflow rules
- Specs are generated via OpenSpec before any implementation.
- Before proposing parallel execution, list every file/directory each task will touch.
- Tasks with overlapping files, or that depend on an undefined contract, must run sequentially or wait for the contract to land in main.
- Shared types/interfaces/API schemas are committed to main before fan-out.
- No task may modify lockfiles, migrations, or root config unless explicitly assigned.
- Each task must state its "done" condition and test command.

- Mention Contracts and API structure for each function and endpoint. 

- After making all the proposals revisit the other existing proposals for any potential merge conflicts and surface it. Be open to updating your proposal in order to avoid the conflicts. 