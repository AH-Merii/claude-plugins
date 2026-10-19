`test` is a required status check on main. Pull requests that only change docs never get it: they sit at "test — Expected — Waiting for status to be reported" and can't be merged. Fix the CI so docs-only pull requests can be merged. They should still not run the test suite, and pull requests that change code must still run it.

Edit the files in this repo directly. Don't commit, push or open a pull request; I'll review the diff.
