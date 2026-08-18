# Install

```bash
uv tool install citekeep
```

No runtime dependencies — everything is standard library, so there is nothing
to compile and no version conflict to resolve. Requires Python 3.11 or later.

`pipx install citekeep` and `pip install citekeep` work just as well.

## Creating a library

If you do not have a canonical `.bib` yet:

```bash
citekeep init --library ~/bibliography/master.bib
```

!!! warning "If you already have a library, do not initialise a second one"

    Point citekeep at the file you already keep. Two canonical libraries
    defeat the purpose: the whole design rests on there being exactly one
    place where a reference is finally correct.

## Telling citekeep where the library is

The path is resolved in this order, first match winning:

1. `--library PATH` on the command line
2. the `CITEKEEP_LIBRARY` environment variable
3. `library = "~/…/master.bib"` in `~/.config/citekeep/config.toml`

Setting it once in the configuration file is the usual choice:

```toml
library = "~/bibliography/master.bib"
```

Check what citekeep resolved:

```bash
citekeep where
```

See [Configuration](reference/configuration.md) for the rest.

## Emacs

The wheel carries `citekeep.el`, and `citekeep emacs-path` prints where it was
installed. A minimal setup:

```elisp
(let ((file (string-trim (shell-command-to-string "citekeep emacs-path"))))
  (add-to-list 'load-path (file-name-directory file)))
(require 'citekeep)
```

The `citekeep` command must be on Emacs's `exec-path`. The rest — key
bindings, Citar integration, what each command does — is in
[Citing while you write](guides/citing.md).
