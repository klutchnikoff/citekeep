# citekeep README demo

`docs/assets/citekeep-demo.gif` is recorded from this directory. The demo runs
against an isolated personal library and LaTeX project in `/tmp`; it never
reads or writes the user's real bibliography.

From the repository root:

```bash
vhs demo/citekeep-side-by-side.tape
```

The cassette uses citekeep's Python and Emacs sources directly from the
checkout. It requires `python3`, `emacs`, VHS and its normal runtime
dependencies on `PATH`, plus Internet access for the recorded zbMATH query.

Regenerating is a manual step, deliberately kept out of CI: it needs Emacs, VHS
and the network all at once, and the result is reviewed by eye.
