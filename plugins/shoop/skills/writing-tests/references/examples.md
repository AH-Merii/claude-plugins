# Worked examples

Python is used for illustration. The ideas carry over to any language.

## Do-nothing stub

Take a function `parse_range("10-12")` that should return `(10, 12)` and should raise on `"12-10"`.

- `assert parse_range("10-12")` would pass against a stub returning any truthy value, so it checks too little. Assert the exact value: `== (10, 12)`.
- A refusal test must assert the specific error. "Doesn't crash" also passes against a stub that does nothing.

## Sibling wrong implementations

The rule under test: "a review is refused when the branch isn't pushed". Write each wrong implementation as its own copy of the correct code, with one change:

| Variant | One bug | Expected |
| --- | --- | --- |
| `wrong_never_refuses` | the check is removed | a refusal test fails |
| `wrong_checks_local_only` | compares against the local ref, not the remote | the "pushed elsewhere" test fails |
| `wrong_refuses_after_posting` | refuses, but only after the request is sent | the "nothing was sent" test fails |

If the suite passes on any variant, the matching rule has a gap. The variant plus the command that runs it is your source for the finding.

Don't stack the variants. If you put all three bugs into one copy, a failure can't tell you which test caught which bug.

## Shared behaviour over every variant

```python
VARIANTS = commands_registered_by_the_cli()   # derived from the code, not hand-listed
POSTS_TEXT = {"reply", "comment", "submit"}
NO_TEXT = {"status", "resolve"}

def test_list_is_real():
    assert {"reply", "status"} <= set(VARIANTS)   # a stub's empty list can't pass

def test_every_variant_is_classified():
    assert set(VARIANTS) == POSTS_TEXT | NO_TEXT  # a new command must be classified

def test_every_text_variant_accepts_attachments():
    for name in POSTS_TEXT:                       # or the runner's parameterisation
        assert_accepts_attachment(name)           # one rule, checked on every variant
```
