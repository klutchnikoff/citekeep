Output "docs/assets/citekeep-demo.gif"

Require emacs
Require python3

Set Shell "zsh"
Set Width 1400
Set Height 800
Set FontSize 22
Set Padding 18
Set Framerate 15
Set TypingSpeed 70ms
Set CursorBlink false

Env CITEKEEP_LIBRARY "/tmp/citekeep-vhs-demo/master.bib"
Env CITEKEEP_DEMO_BIB "/tmp/citekeep-vhs-demo/project/refs.bib"

Hide
Type "mkdir -p /tmp/citekeep-vhs-demo/project"
Enter
Type "cp demo/fixtures/master.bib /tmp/citekeep-vhs-demo/master.bib"
Enter
Type "cp demo/fixtures/refs.bib /tmp/citekeep-vhs-demo/project/refs.bib"
Enter
Type "cp demo/fixtures/paper.tex /tmp/citekeep-vhs-demo/project/paper.tex"
Enter
Type "emacs -Q -nw -l demo/side-by-side-init.el /tmp/citekeep-vhs-demo/project/paper.tex"
Enter
Wait+Screen /Project or personal library:/
Wait+Screen /godel_uber_1931/
Show
Sleep 100ms
Space

Escape
Type "x"
Type "citekeep-insert"
Sleep 1200ms
Enter
Sleep 1200ms
Type "godel"
Sleep 1400ms
Down
Sleep 1800ms
Enter
Wait+Screen /godel_consistency_1938/
Sleep 2200ms

Ctrl+S
Type "Found online:"
Enter
Ctrl+E
Space
Escape
Type "x"
Type "citekeep-fetch"
Sleep 1200ms
Enter
Type "10.2307/2118559"
Sleep 1200ms
Enter
Wait+Screen /zbmath, 1 result/
Sleep 3s
Enter
Wait+Screen /wiles_modular_1995/
Sleep 3500ms
