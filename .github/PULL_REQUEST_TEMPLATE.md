## Summary

<!-- Briefly describe what this PR does and why. Keep it concise and readable: a few sentences, no long walls of text. -->

## AI Disclaimer

<!-- If an agent helped with the implementation, disclose that here. State which parts it authored and which parts you wrote or reviewed. -->

## Cluster tests

<!--
Every PR must run the cluster-only tests on a Slurm login node (Slurm job submission, LLM, and the CLI tests that need `sbatch`) and paste the output below.

Run on the login node:

    bash scripts/test/cluster.sh

Paste the full output, including the summary line, for example:

```
collected 191 items / 181 deselected / 10 selected

tests/test_cli.py ...                                [ 30%]
tests/test_executor/test_slurm_integration.py .....  [ 80%]
tests/test_workflow/test_experiment_on_slurm.py .    [ 90%]
tests/test_workflow/test_proposer_llm.py .           [100%]

10 passed, 181 deselected in 41.36s
Cluster tests passed.
```

If you do not have cluster access, state that explicitly here.
-->
