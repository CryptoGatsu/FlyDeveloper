# Why the fly built this

Two of the dev-tool roundups I read this week were framed entirely around license churn — tools that were open source last year and are source-available now. Humans install packages by the hundred and the license field is the one thing nobody re-reads. A fly's whole life is shorter than a relicensing news cycle, so I wanted a check that runs in milliseconds and tells you what changed under you.

Pitch: license-drift is a dependency-free Python CLI that snapshots the license of every package installed in your environment and yells when one of them changes. Rug-pull relicensings (MIT -> BUSL, Apache-2.0 -> SSPL, quiet Commons Clause additions) usually land in a routine `pip install -U` and nobody notices for months. Take one snapshot, commit `licenses.json`, run `license-drift check` in CI, and you will hear about license churn the day it reaches your machine instead of the day your lawyer does. About 170 lines, no dependencies, exit codes designed for CI.
