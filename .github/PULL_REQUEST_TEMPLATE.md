## Summary

<!-- Briefly describe what this PR does and why. Keep it concise and readable: a few sentences, no long walls of text. -->

## Review guidance

<!--
If it's a larger or more complex PR, tell the reviewer how best to approach it: e.g. which files to look at first (with the core logic), 
or whether to review commit-by-commit if you've arranged them so. 
Even consider adding a flow diagram (e.g. https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams).

By default it's assumed that reviewers can provide feedback on any level of detail. If you only want high-level feedback for a first iteration, tell them specifically.

If it's a smaller PR, feel free to remove this section.
-->

## AI Disclaimer

<!-- If an agent helped with the implementation, disclose that here. State which parts it authored and which parts you wrote or reviewed. -->

## Integration tests

<!--
Every PR must run the on-cluster integration suite (Slurm jobs plus the configured LLM) and paste the output below.

Run on the login node:

    bash scripts/test/prod.sh

Paste the full output, including the summary line, for example:

```
collected 72 items / 65 deselected / 7 selected

tests/test_executor/test_slurm_integration.py ..... [ 71%]
tests/test_workflow/test_experiment_on_slurm.py .  [ 85%]
tests/test_workflow/test_proposer_llm.py .  [100%]

7 passed, 65 deselected in 39.36s 
Integration tests passed.
```

If you do not have cluster access, state that explicitly here.
-->
