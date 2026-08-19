;;; citekeep.el --- Keep one BibTeX library, in step with your projects -*- lexical-binding: t; -*-

;; Author: Nicolas Klutchnikoff
;; Version: 0.1.0
;; Package-Requires: ((emacs "28.1"))
;; Keywords: bib, tex, wp
;; URL: https://github.com/klutchnikoff/citekeep

;; SPDX-License-Identifier: MIT

;;; Commentary:

;; A front end to the citekeep command line.  Every decision — what counts as
;; a duplicate, which key an entry takes, whether a merge is safe — is made by
;; citekeep itself and reached through `--json'.  Nothing is reimplemented
;; here, so this file and the command line cannot drift apart.
;;
;;   `citekeep-insert'        search the project, then master, then the web
;;   `citekeep-fetch'         go directly to an online search
;;   `citekeep-verify-entry'  compare the local entry at point with all sources
;;   `citekeep-status'        inspect a complete project sync plan
;;   `citekeep-sync'          apply that master/project plan
;;   `citekeep-open-library'  visit the library itself
;;
;; The library path is resolved by the command line — flag, then
;; $CITEKEEP_LIBRARY, then ~/.config/citekeep/config.toml — unless
;; `citekeep-library' names one.

;;; Code:

(require 'json)
(require 'project)
(require 'subr-x)
(require 'seq)

(declare-function citar-latex-insert-citation "citar-latex"
                  (keys &optional invert-prompt command))

(defgroup citekeep nil
  "Keep one BibTeX library, in step with your projects."
  :group 'tex
  :prefix "citekeep-")

(defcustom citekeep-executable "citekeep"
  "The citekeep command."
  :type 'string)

(defcustom citekeep-library nil
  "Path to the library, or nil to let the command line resolve it.
Leaving this nil is usually right: the resolution order then lives in one
place, and a shell and Emacs cannot disagree about which file they mean."
  :type '(choice (const :tag "Let citekeep decide" nil) file))

(defcustom citekeep-bib-file-function #'citekeep-guess-bib-file
  "Function returning the project .bib to synchronise, or nil to be asked."
  :type 'function)

(defcustom citekeep-search-count 10
  "How many results `citekeep-fetch' asks a service for."
  :type 'integer)

(defcustom citekeep-cite-command "citep"
  "The citation command citekeep writes.
\\citet and \\citep work under natbib and, through biblatex's `natbib'
option, under biblatex as well — which is why a citation written with them
travels between projects that do not share a bibliography package."
  :type 'string)

(defcustom citekeep-insert-citation-function #'citekeep--insert-cite-default
  "Function called with MARKER, COMMAND and KEY to insert a citation.
The default writes a LaTeX command.  Citar, Org Cite or another editor adapter
can be installed here without changing citekeep's data workflow."
  :type 'function)

(defcustom citekeep-cancel-hook nil
  "Hook run in the originating buffer after an editor selection is cancelled.

Point has already been restored.  Editor adapters can use this to restore a
modal editing state; citekeep itself has no dependency on Evil or another
modal package."
  :type 'hook)

(defconst citekeep--cancelled (make-symbol "citekeep-cancelled")
  "Private result returned by a cancelled editor prompt.")


;;; Running the command line

(defconst citekeep--commands-taking-library
  '("where" "search" "fetch" "editor" "sync")
  "Commands that consult the master library.")

(defun citekeep--library-args (command)
  (when (and citekeep-library
             (member command citekeep--commands-taking-library))
    (list "--library" (expand-file-name citekeep-library))))

(defun citekeep--call (args)
  "Run citekeep with ARGS.  Return (CODE STDOUT STDERR)."
  (let ((stderr (make-temp-file "citekeep"))
        code stdout)
    (unwind-protect
        (progn
          (with-temp-buffer
            (setq code (apply #'call-process citekeep-executable nil
                              (list (current-buffer) stderr) nil
                              (append args (citekeep--library-args (car args)))))
            (setq stdout (buffer-string)))
          (list code stdout
                (with-temp-buffer
                  (insert-file-contents stderr)
                  (string-trim (buffer-string)))))
      (delete-file stderr))))

(defconst citekeep-schema-version 1
  "The `schema_version' this file knows how to read.

Every JSON answer carries one.  Refusing an unknown value turns a silent
misreading into a plain message: an Emacs left open across an upgrade, or
a `citekeep.el' loaded from a checkout while the command comes from an
installed wheel, are exactly the situations where the two halves drift.")

(defun citekeep--parse (stdout)
  "Parse STDOUT as citekeep JSON, refusing a schema this file cannot read."
  (let* ((data (json-parse-string stdout
                                  :object-type 'alist
                                  :array-type 'list))
         (version (alist-get 'schema_version data)))
    (unless (equal version citekeep-schema-version)
      (user-error
       "citekeep: this citekeep.el reads schema %d, the command speaks %s — %s"
       citekeep-schema-version (or version "none")
       "reinstall citekeep, or reload citekeep.el from the same tree"))
    data))

(defun citekeep--json (args)
  "Run citekeep with ARGS and --json.  Return (CODE . DATA).

Exit status 2 means the user has something to fix — no library configured,
a missing file — and carries its explanation on stderr rather than as data.
Status 1 is not a failure: the command ran, and what it found needs
attention."
  (pcase-let ((`(,code ,stdout ,stderr)
               (citekeep--call (append args '("--json")))))
    (when (or (= code 2) (string-empty-p (string-trim stdout)))
      (user-error "citekeep: %s"
                  (if (string-empty-p stderr) "no output" stderr)))
    (cons code (citekeep--parse stdout))))

(defun citekeep--call-async (args callback)
  "Run citekeep with ARGS; call CALLBACK with (CODE STDOUT STDERR).

Asynchronous, unlike the rest: this is the one command that reaches the
network, and a service having a slow day must not freeze the editor."
  (let ((out (generate-new-buffer " *citekeep-stdout*"))
        (err (generate-new-buffer " *citekeep-stderr*")))
    (make-process
     :name "citekeep"
     :buffer out
     :stderr err
     :noquery t
     :connection-type 'pipe
     :command (cons citekeep-executable
                    (append args (citekeep--library-args (car args))))
     :sentinel
     (lambda (process _event)
       (unless (process-live-p process)
         (let ((code (process-exit-status process))
               (stdout (with-current-buffer out (buffer-string)))
               (stderr (with-current-buffer err (buffer-string))))
           (when-let ((pipe (get-buffer-process err)))
             (delete-process pipe))
           (when (buffer-live-p out) (kill-buffer out))
           (when (buffer-live-p err) (kill-buffer err))
           (funcall callback code stdout (string-trim stderr))))))))

(defun citekeep--call-with-input (text args)
  "Run citekeep with ARGS, feeding TEXT on standard input.
Return (CODE STDOUT STDERR)."
  (let ((input (make-temp-file "citekeep-in"))
        (stderr (make-temp-file "citekeep-err"))
        code stdout)
    (unwind-protect
        (progn
          (let ((coding-system-for-write 'utf-8))
            (with-temp-file input (insert text)))
          (with-temp-buffer
            (setq code (apply #'call-process citekeep-executable input
                              (list (current-buffer) stderr) nil
                              (append args (citekeep--library-args (car args)))))
            (setq stdout (buffer-string)))
          (list code stdout
                (with-temp-buffer
                  (insert-file-contents stderr)
                  (string-trim (buffer-string)))))
      (delete-file input)
      (delete-file stderr))))

(defun citekeep--get (data &rest keys)
  "Follow KEYS through the parsed DATA."
  (dolist (key keys data)
    (setq data (alist-get key data))))


;;; Locating things

(defun citekeep--region-text ()
  "The active region, trimmed — a plausible query to start from."
  (when (use-region-p)
    (string-trim (buffer-substring-no-properties (region-beginning)
                                                 (region-end)))))

(defun citekeep--root ()
  "The current project's root, or the current directory."
  (if-let ((project (project-current)))
      (project-root project)
    default-directory))

(defun citekeep-guess-bib-file ()
  "Return this buffer's .bib, or the only one below the project root.
Returns nil when the guess would be a coin toss, so that the caller asks."
  (if (and buffer-file-name (string-suffix-p ".bib" buffer-file-name))
      buffer-file-name
    (let ((found (ignore-errors
                   (directory-files-recursively (citekeep--root)
                                                "\\.bib\\'"))))
      (when (= (length found) 1)
        (car found)))))

(defun citekeep--read-bib-file ()
  (or (funcall citekeep-bib-file-function)
      (read-file-name "Synchronise which .bib? " (citekeep--root) nil t)))

(defun citekeep--save-file-buffer (file)
  "Save a modified buffer visiting FILE, or refuse an external write."
  (when-let ((buffer (find-buffer-visiting (expand-file-name file))))
    (with-current-buffer buffer
      (when (buffer-modified-p)
        (unless (y-or-n-p (format "Save %s before citekeep changes it? "
                                  (file-name-nondirectory file)))
          (user-error "citekeep: refusing to overwrite an unsaved buffer"))
        (save-buffer)))))

(defun citekeep--refresh-file-buffer (file)
  "Refresh an unmodified buffer visiting FILE after an external write."
  (when-let ((buffer (find-buffer-visiting (expand-file-name file))))
    (with-current-buffer buffer
      (unless (buffer-modified-p)
        (revert-buffer t t t)))))


;;; Reporting

(defconst citekeep-report-buffer "*citekeep*")

(defun citekeep--report (title lines)
  "Show LINES under TITLE, or say so in the echo area when there are none."
  (if (null lines)
      (message "%s" title)
    (with-current-buffer (get-buffer-create citekeep-report-buffer)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert title "\n\n")
        (dolist (line lines) (insert line "\n"))
        (goto-char (point-min)))
      (special-mode)
      (display-buffer (current-buffer)))))

;;; Commands

(defun citekeep--cancel-selection (marker)
  "Restore MARKER and announce a silent editor-selection cancellation."
  (when-let ((buffer (marker-buffer marker)))
    (when (buffer-live-p buffer)
      (with-current-buffer buffer
        (goto-char marker)
        (run-hooks 'citekeep-cancel-hook))))
  (set-marker marker nil)
  citekeep--cancelled)

(defun citekeep--read-cancellable (marker reader)
  "Call READER; turn `quit' into a silent cancellation at MARKER."
  (condition-case nil
      (funcall reader)
    (quit (citekeep--cancel-selection marker))))

;;;###autoload
(defun citekeep-insert (query &optional command)
  "Select a record fuzzily, materialise it when needed, and cite it.

QUERY is initial completion input, normally the active region.  Filled-circle
records are already in the project; hollow-circle records come from the
master.  Project records appear first and shadow the same work in the master,
because their project key is the one that must be inserted.  Choosing the
Internet action, or accepting raw input with
`citekeep--exit-completion-input', continues with an online search."
  (interactive
   (list (citekeep--region-text)
         (when current-prefix-arg
           (read-string "Citation command: \\" citekeep-cite-command))))
  (let ((file (funcall citekeep-bib-file-function))
        (marker (copy-marker (point) t))
        (command (or command citekeep-cite-command)))
    (unless file
      (user-error "citekeep: no project .bib found — visit one, or set %s"
                  "`citekeep-bib-file-function'"))
    (citekeep--save-file-buffer file)
    (pcase-let* ((`(,_code . ,data)
                  (citekeep--json
                   (list "search" "--local" (expand-file-name file))))
                 (local (citekeep--get data 'local))
                 (master (citekeep--get data 'master))
                 (online "🌐 Search online…")
                 (table
                  (append
                   (mapcar (lambda (item)
                             (cons (citekeep--insert-label item) item))
                           local)
                   (mapcar (lambda (item)
                             (cons (citekeep--insert-label item) item))
                           master)))
                 (choice
                  (citekeep--read-cancellable
                   marker
                   (lambda ()
                     (let* ((sorter
                             (lambda (candidates)
                               (citekeep--insert-sort-candidates
                                candidates table online)))
                            (completion-extra-properties
                             `(:category citekeep-citation
                               :display-sort-function ,sorter
                               :cycle-sort-function ,sorter)))
                       (minibuffer-with-setup-hook
                           #'citekeep--insert-completion-setup
                         (completing-read "Cite (C-RET → Internet): "
                                          (append (mapcar #'car table)
                                                  (list online))
                                          nil nil query)))))))
      (cond
       ((eq choice citekeep--cancelled))
       ((equal choice online)
        (let ((online-query
               (citekeep--read-cancellable
                marker
                (lambda ()
                  (read-string "Search online: " (or query ""))))))
          (unless (eq online-query citekeep--cancelled)
            (set-marker marker nil)
            (citekeep-fetch online-query command))))
       ((cdr (assoc choice table))
        (citekeep--insert-hit (cdr (assoc choice table)) file marker command))
       ((not (string-empty-p choice))
        (set-marker marker nil)
        (citekeep-fetch choice command))
       (t (citekeep--cancel-selection marker))))))

(defun citekeep--exit-completion-input ()
  "Accept raw minibuffer input instead of its selected completion.

With Vertico, delegate to its public command.  The fallback works with the
standard completion UI because citekeep does not require an exact match."
  (interactive)
  (if (fboundp 'vertico-exit-input)
      (vertico-exit-input)
    (exit-minibuffer)))

(defun citekeep--insert-completion-setup ()
  "Install the online-search exit key in the current minibuffer."
  (local-set-key (kbd "C-<return>") #'citekeep--exit-completion-input)
  (local-set-key (kbd "C-RET") #'citekeep--exit-completion-input))

(defun citekeep--insert-sort-candidates (candidates table online)
  "Put local CANDIDATES before master and ONLINE candidates.

TABLE maps displayed candidates to their records.  The partition is stable,
so the relevance order supplied by citekeep is retained inside each group.
This function is completion-UI independent: both standard Emacs completion
and front ends such as Vertico consume it as completion metadata."
  (let (local master other internet)
    (dolist (candidate candidates)
      (let* ((entry (assoc candidate table))
             (origin (and entry (citekeep--get (cdr entry) 'origin))))
        (cond
         ((equal origin "local") (push candidate local))
         ((equal origin "master") (push candidate master))
         ((equal candidate online) (push candidate internet))
         (t (push candidate other)))))
    (append (nreverse local) (nreverse master)
            (nreverse other) (nreverse internet))))

(defun citekeep--insert-label (item)
  "Format ITEM for the citation selector.

A filled circle means that the record is already materialised locally; a
hollow circle means that it is available from the master library."
  (format "%s  %s  %s  %s  [%s]%s%s"
          (if (equal (citekeep--get item 'origin) "local") "●" "○")
          (or (citekeep--get item 'authors_full)
              (citekeep--get item 'authors) "—")
          (or (citekeep--get item 'year) "????")
          (or (citekeep--get item 'title) "")
          (citekeep--get item 'citation_key)
          (if-let ((journal (citekeep--get item 'journal)))
              (if (string-empty-p journal) "" (concat "  " journal))
            "")
          (if-let ((doi (citekeep--get item 'doi)))
              (if (string-empty-p doi) "" (concat "  " doi))
            "")))

(defun citekeep--insert-hit (item file marker command)
  "Materialise ITEM when needed, then cite it at MARKER."
  (let ((origin (citekeep--get item 'origin))
        (key (citekeep--get item 'citation_key)))
    (if (equal origin "local")
        (progn
          (citekeep--insert-cite marker command key)
          (message "citekeep: cited local entry %s" key))
      (pcase-let ((`(,code ,stdout ,stderr)
                   (citekeep--call
                    (list "editor" "materialize"
                          (citekeep--get item 'master_key)
                          "--into" (expand-file-name file) "--json"))))
        (if (or (= code 2) (string-empty-p (string-trim stdout)))
            (message "citekeep: %s"
                     (if (string-empty-p stderr) "no output" stderr))
          (let* ((data (citekeep--parse stdout))
                 (citation-key (citekeep--get data 'citation_key)))
            (citekeep--refresh-file-buffer file)
            (citekeep--insert-cite marker command citation-key)
            (message "citekeep: %s %s in %s"
                     (citekeep--get data 'action) citation-key
                     (file-name-nondirectory file))))))
    (set-marker marker nil)))

;;;###autoload
(defun citekeep-open-library ()
  "Visit the library."
  (interactive)
  (pcase-let ((`(,code ,stdout ,stderr) (citekeep--call '("where"))))
    (when (= code 2) (user-error "citekeep: %s" stderr))
    (let ((path (string-trim stdout)))
      (unless (file-exists-p path)
        (user-error "citekeep: %s does not exist" path))
      (find-file path))))

(defun citekeep--insert-cite (marker command key)
  "Insert KEY at MARKER through `citekeep-insert-citation-function'."
  (funcall citekeep-insert-citation-function marker command key))

(defun citekeep--insert-cite-default (marker command key)
  "Write \\COMMAND{KEY} at MARKER."
  (let ((buffer (marker-buffer marker)))
    (when (buffer-live-p buffer)
      (with-current-buffer buffer
        (goto-char marker)
        (insert (format "\\%s{%s}" command key))))))

(defun citekeep-citar-insert-citation (marker command key)
  "Insert KEY at MARKER through the public Citar LaTeX adapter.

Unlike the default literal insertion, this adds KEY to a citation already at
point and honours the citation parsing provided by Citar and AUCTeX.  In a
non-LaTeX buffer it falls back to citekeep literal insertion.  Configure it
with:

  (setq citekeep-insert-citation-function
        (function citekeep-citar-insert-citation))"
  (let ((buffer (marker-buffer marker)))
    (when (buffer-live-p buffer)
      (with-current-buffer buffer
        (goto-char marker)
        (if (derived-mode-p 'latex-mode 'LaTeX-mode)
            (progn
              (unless (require 'citar-latex nil t)
                (user-error "Citar's LaTeX adapter is not installed"))
              (citar-latex-insert-citation (list key) nil command))
          (citekeep--insert-cite-default marker command key))))))

;;;###autoload
(defun citekeep-status (&optional directory)
  "Show the complete synchronisation plan for the current project."
  (interactive)
  (citekeep--sync-command (or directory (citekeep--root)) nil))

;;;###autoload
(defun citekeep-sync (&optional directory)
  "Apply a complete master/project synchronisation."
  (interactive)
  (citekeep--sync-command (or directory (citekeep--root)) t))

(defun citekeep--sync-command (root apply &optional answers bib-file)
  (let* ((file (expand-file-name (or bib-file (citekeep--read-bib-file))))
         (root (expand-file-name root)))
    (citekeep--save-project-buffers root)
    (citekeep--save-master-buffer)
    (let* ((args (append (list "sync" "--project" root "--bib" file)
                         (when apply '("--apply"))
                         (when answers (list "--resolve" answers))))
           (result (citekeep--json args))
           (data (cdr result))
           (conflicts (citekeep--get data 'conflicts))
           (identity-conflicts
            (seq-filter (lambda (conflict)
                          (citekeep--get conflict 'incoming))
                        conflicts))
           (decisions (and apply (null identity-conflicts)
                           (citekeep--choose-field-resolutions
                            conflicts))))
      (if (and apply identity-conflicts)
          (progn
            (citekeep--open-resolve root file identity-conflicts)
            nil)
        (when decisions
          (setq result (citekeep--json (append args decisions))
                data (cdr result)))
        (when (citekeep--get data 'applied)
          (citekeep--refresh-file-buffer file)
          (when-let ((master (citekeep--get data 'master_file)))
            (citekeep--refresh-file-buffer master)))
        (citekeep--sync-report data (citekeep--get data 'applied))
        (citekeep--get data 'applied)))))

(defun citekeep--choose-field-resolutions (conflicts)
  "Ask how to settle structured field CONFLICTS and return CLI arguments.

Return nil when there is no field conflict, an identity conflict is mixed in,
or the user cancels.  Thus a partial answer can never be applied by accident."
  (when (and conflicts
             (seq-every-p (lambda (conflict)
                            (citekeep--get conflict 'fields))
                          conflicts))
    (catch 'cancel
      (let (arguments)
        (dolist (conflict conflicts)
          (let ((key (citekeep--get conflict 'local_key)))
            (dolist (field (citekeep--get conflict 'fields))
              (let* ((name (citekeep--get field 'name))
                     (master (citekeep--get field 'master))
                     (local (citekeep--get field 'local))
                     (choice
                      (read-char-choice
                       (format "%s/%s: [m] master %S, [l] local %S, [q] cancel: "
                               key name master local)
                       '(?m ?l ?q))))
                (when (= choice ?q)
                  (throw 'cancel nil))
                (setq arguments
                      (append arguments
                              (list (if (= choice ?m)
                                        "--keep-master" "--use-local")
                                    (format "%s:%s" key name))))))))
        arguments))))

(defun citekeep--save-project-buffers (root)
  "Save modified TeX and BibTeX buffers below ROOT after confirmation."
  (dolist (buffer (buffer-list))
    (with-current-buffer buffer
      (when (and buffer-file-name (buffer-modified-p)
                 (file-in-directory-p buffer-file-name root)
                 (member (downcase (or (file-name-extension buffer-file-name) ""))
                         '("tex" "bib")))
        (citekeep--save-file-buffer buffer-file-name)))))

(defun citekeep--save-master-buffer ()
  (pcase-let ((`(,code ,stdout ,_stderr) (citekeep--call '("where"))))
    (when (= code 0)
      (citekeep--save-file-buffer (string-trim stdout)))))

(defun citekeep--sync-report (data applied)
  (let* ((summary (citekeep--get data 'summary))
         (conflicts (citekeep--get data 'conflicts))
         (unknown (citekeep--get data 'unknown))
         (title
          (format "citekeep %s: %d master additions, %d master corrections, %d local updates, %d conflicts"
                  (if applied "sync" "status")
                  (citekeep--get summary 'master_added)
                  (citekeep--get summary 'master_corrected)
                  (+ (citekeep--get summary 'local_added)
                     (citekeep--get summary 'local_updated))
                  (citekeep--get summary 'conflicts))))
    (if (and (null conflicts) (null unknown))
        (message "%s" title)
      (citekeep--report
       title
       (append
        (mapcar (lambda (conflict)
                  (format "! %s — %s"
                          (citekeep--get conflict 'local_key)
                          (citekeep--get conflict 'reason)))
                conflicts)
        (mapcar (lambda (entry)
                  (format "? %s — %s"
                          (citekeep--get entry 'key)
                          (string-join (mapcar #'file-name-nondirectory
                                               (citekeep--get entry 'files))
                                       ", ")))
                unknown))))))

(defun citekeep--library-line (record)
  (format "    library   %s  %s  (%s)"
          (or (citekeep--get record 'year) "????")
          (or (citekeep--get record 'title) "")
          (citekeep--get record 'key)))

;;;###autoload
(defun citekeep-fetch (&optional query command)
  "Search for QUERY, choose among the results, file the choice and cite it.

Each result carries what the library already makes of it, so a reference
you have is visible as such before you pick it — not after you have
imported it a second time.

The chosen record is sent straight to citekeep rather than fetched again:
the service is asked once."
  (interactive
   (list nil
         (when current-prefix-arg
           (read-string "Citation command: \\" citekeep-cite-command))))
  (let* ((marker (copy-marker (point) t))
         (command (or command citekeep-cite-command))
         (query
          (or query
              (citekeep--read-cancellable
               marker
               (lambda ()
                 (read-string "Search: " (citekeep--region-text)))))))
    (unless (eq query citekeep--cancelled)
      (let ((file (funcall citekeep-bib-file-function)))
        (unless file
          (set-marker marker nil)
          (user-error "citekeep: no project .bib found — visit one, or set %s"
                      "`citekeep-bib-file-function'"))
        (message "citekeep: searching for %s…" query)
        (citekeep--call-async
         (list "fetch" query
               "--into" (expand-file-name file)
               "--count" (number-to-string citekeep-search-count)
               "--json")
         (lambda (code stdout stderr)
           (if (or (= code 2) (string-empty-p (string-trim stdout)))
               (progn
                 (set-marker marker nil)
                 (message "citekeep: %s"
                          (if (string-empty-p stderr) "no output" stderr)))
             (citekeep--search-choose (citekeep--parse stdout)
                                      file marker command))))))))

;;;###autoload
(defun citekeep-verify-entry ()
  "Verify the BibTeX entry at point against all configured online sources.

After one network pass, complete missing fields, accept selected fields, or
replace bibliographic metadata while preserving the local key and citekeep
metadata."
  (interactive)
  (unless (and buffer-file-name
               (string-suffix-p ".bib" buffer-file-name))
    (user-error "citekeep: visit a .bib entry first"))
  (citekeep--save-file-buffer buffer-file-name)
  (let ((key (citekeep--bib-key-at-point))
        (file buffer-file-name))
    (message "citekeep: checking %s against online sources…" key)
    (citekeep--call-async
     (list "verify" file "--key" key "--json")
     (lambda (code stdout stderr)
       (if (or (= code 2) (string-empty-p (string-trim stdout)))
           (message "citekeep: %s"
                    (if (string-empty-p stderr) "no output" stderr))
         (citekeep--verify-choose (citekeep--parse stdout) file key))))))

(defun citekeep--bib-key-at-point ()
  "Return the key of the BibTeX entry containing point."
  (save-excursion
    (unless (re-search-backward
             "^@[[:alnum:]_]+[[:space:]]*{[[:space:]]*\\([^,[:space:]]+\\),"
             nil t)
      (user-error "citekeep: point is not in a BibTeX entry"))
    (match-string-no-properties 1)))

(defun citekeep--verify-choose (data file key)
  (let* ((trusted (seq-filter
                   (lambda (candidate)
                     (citekeep--get candidate 'trusted_identity))
                   (citekeep--get data 'candidates))))
    (if (null trusted)
        (citekeep--report
         (format "citekeep verify: no trusted result for %s" key)
         (mapcar (lambda (candidate)
                   (format "? %s — %s"
                           (citekeep--get candidate 'source)
                           (citekeep--get candidate 'reason)))
                 (citekeep--get data 'candidates)))
      (let* ((source-table
              (mapcar (lambda (candidate)
                        (cons (format "%s — %s"
                                      (citekeep--get candidate 'source)
                                      (citekeep--get candidate 'record 'title))
                              candidate))
                      trusted))
             (source-choice
              (completing-read "Use which source? "
                               (mapcar #'car source-table) nil t))
             (candidate (cdr (assoc source-choice source-table)))
             (action (completing-read
                      "Verification action: "
                      '("Complete missing fields"
                        "Choose fields"
                        "Replace bibliographic metadata"
                        "Cancel") nil t)))
        (unless (equal action "Cancel")
          (let* ((mode (pcase action
                         ("Complete missing fields" "complete")
                         ("Choose fields" "selected")
                         (_ "replace")))
                 (source-name (citekeep--get candidate 'source))
                 (available
                  (mapcar
                   (lambda (field) (citekeep--get field 'name))
                   (seq-filter
                    (lambda (field)
                      (seq-some
                       (lambda (value)
                         (equal source-name (citekeep--get value 'source)))
                       (citekeep--get field 'sources)))
                    (citekeep--get data 'fields))))
                 (fields (when (equal mode "selected")
                           (completing-read-multiple
                            "Accept fields: " available nil t))))
            (citekeep--verify-apply candidate file key mode fields)))))))

(defun citekeep--verify-apply (candidate file key mode fields)
  (let ((args (append
               (list "editor" "refresh-record" file "--key" key
                     "--source" (citekeep--get candidate 'source)
                     "--mode" mode "--json")
               (mapcan (lambda (field) (list "--field" field)) fields))))
    (pcase-let ((`(,code ,stdout ,stderr)
                 (citekeep--call-with-input
                  (citekeep--get candidate 'record 'entry) args)))
      (if (or (= code 2) (string-empty-p (string-trim stdout)))
          (message "citekeep: %s"
                   (if (string-empty-p stderr) "no output" stderr))
        (citekeep--refresh-file-buffer file)
        (message "citekeep: refreshed %s from %s (%s)"
                 key (citekeep--get candidate 'source) mode)))))

(defun citekeep--search-label (result)
  "One line describing RESULT, verdict included."
  (let ((match (citekeep--get result 'match)))
    (format "%-22.22s  %-4s  %-54.54s  %s"
            (or (citekeep--get result 'authors) "—")
            (or (citekeep--get result 'year) "????")
            (or (citekeep--get result 'title) "")
            (pcase (citekeep--get match 'kind)
              ("unchanged" (format "have it: %s" (citekeep--get match 'key)))
              ("enrich" (format "have it, incomplete: %s"
                                (citekeep--get match 'key)))
              ("new" "new")
              (_ (format "unclear: %s" (citekeep--get match 'reason)))))))

(defun citekeep--search-choose (data file marker command)
  (let ((results (citekeep--get data 'results)))
    (if (null results)
        (progn
          (set-marker marker nil)
          (message "citekeep: nothing found"))
      (let* ((table (mapcar (lambda (r) (cons (citekeep--search-label r) r))
                            results))
             (completion-extra-properties nil)
             (choice
              (citekeep--read-cancellable
               marker
               (lambda ()
                 (completing-read
                  (format "%s, %d result(s): "
                          (citekeep--get data 'source) (length results))
                  (mapcar #'car table) nil t)))))
        (unless (eq choice citekeep--cancelled)
          (if-let ((chosen (cdr (assoc choice table))))
              (citekeep--search-take chosen file marker command)
            (citekeep--cancel-selection marker)))))))

(defun citekeep--search-take (result file marker command)
  "File RESULT into FILE and cite it at MARKER with COMMAND."
  (let* ((match (citekeep--get result 'match))
         (decision (and (equal (citekeep--get match 'kind) "conflict")
                        (citekeep--online-decision match marker))))
    (unless (eq decision citekeep--cancelled)
      (let ((args (list "editor" "add-record"
                        "--into" (expand-file-name file) "--json")))
        (when decision
          (setq args (append args (list "--decision" (car decision))))
          (when (cdr decision)
            (setq args (append args (list "--target" (cdr decision))))))
        (pcase-let ((`(,code ,stdout ,stderr)
                     (citekeep--call-with-input
                      (citekeep--get result 'entry) args)))
          (if (or (= code 2) (string-empty-p (string-trim stdout)))
              (message "citekeep: %s"
                       (if (string-empty-p stderr) "no output" stderr))
            (let* ((data (citekeep--parse stdout))
                   (resolved (citekeep--get data 'match))
                   (kind (citekeep--get resolved 'kind))
                   (written (citekeep--get data 'written))
                   (key (citekeep--get resolved 'key)))
              (cond
               ((equal kind "conflict")
                (citekeep--show-unclear
                 (citekeep--get resolved 'reason)
                 (citekeep--get result 'year)
                 (citekeep--get result 'title)
                 (citekeep--get resolved 'existing)))
               ((equal kind "skip")
                (message "citekeep: skipped %s" key))
               (written
                (citekeep--refresh-file-buffer file)
                (citekeep--insert-cite marker command key)
                (message "citekeep: %s %s in %s"
                         (citekeep--get written 'action) key
                         (file-name-nondirectory
                          (citekeep--get written 'file))))))))))
    (set-marker marker nil)))

(defun citekeep--online-decision (match marker)
  "Ask how fetched MATCH relates to the library at MARKER.

Return (VERB . TARGET), or `citekeep--cancelled'. The command line remains
the authority for validating the answer and allocating a distinct key."
  (citekeep--read-cancellable
   marker
   (lambda ()
     (let* ((existing (citekeep--get match 'existing))
            (same "Same work")
            (distinct "Distinct work")
            (skip "Skip")
            (choice (completing-read
                     (format "Identity conflict (%s): "
                             (citekeep--get match 'reason))
                     (append (when existing (list same))
                             (list distinct skip))
                     nil t)))
       (cond
        ((equal choice distinct) '("distinct"))
        ((equal choice skip) '("skip"))
        ((equal choice same)
         (let ((keys (mapcar (lambda (record)
                               (citekeep--get record 'key))
                             existing)))
           (cons "same"
                 (when (> (length keys) 1)
                   (completing-read "Same as which entry? " keys nil t))))))))))

(defun citekeep--show-unclear (reason year title existing)
  "Show why a record was not filed, next to what it resembles."
  (citekeep--report
   (format "citekeep: %s — nothing was written" reason)
   (cons (format "    fetched   %s  %s" (or year "????") (or title ""))
         (mapcar #'citekeep--library-line existing)))
  (message "citekeep: %s — decide before citing" reason))

;;; Settling identity conflicts in a synchronisation

;; A conflict is a question with three answers, and answering it is the one
;; place where this package asks for judgement.  The buffer holds the answers
;; itself rather than reading them back out of its own text: what is drawn is
;; a view, and the user cannot corrupt the state by typing in it.

(defvar-local citekeep--conflicts nil "Conflicts under arbitration.")
(defvar-local citekeep--answers nil "Alist of key to (VERB . TARGET).")
(defvar-local citekeep--resolve-root nil "Project root being synchronised.")
(defvar-local citekeep--resolve-file nil "Project .bib being synchronised.")

(defvar citekeep-resolve-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "s") #'citekeep-resolve-same)
    (define-key map (kbd "d") #'citekeep-resolve-distinct)
    (define-key map (kbd "k") #'citekeep-resolve-skip)
    (define-key map (kbd "u") #'citekeep-resolve-unset)
    (define-key map (kbd "n") #'citekeep-resolve-next)
    (define-key map (kbd "p") #'citekeep-resolve-previous)
    ;; `special-mode' points g at `revert-buffer', which here looks for a file
    ;; that does not exist and errors. Give it the meaning the key has in
    ;; every other such buffer instead.
    (define-key map (kbd "g") #'citekeep-resolve-refresh)
    (define-key map (kbd "C-c C-c") #'citekeep-resolve-apply)
    map)
  "Keymap for `citekeep-resolve-mode'.")

(define-derived-mode citekeep-resolve-mode special-mode "Citekeep"
  "Answer identity questions a synchronisation could not settle.")

;; Single letters are evil operators in normal state; this buffer is a menu,
;; not a document, so it opens in Emacs state where they mean what they say.
(with-eval-after-load 'evil
  (when (fboundp 'evil-set-initial-state)
    (evil-set-initial-state 'citekeep-resolve-mode 'emacs)))

(defconst citekeep--resolve-help
  "Point picks the question.  Answer them all, then apply.

  s  same       one work: the library entry is completed from this one
  d  distinct   another work: it enters under a key of its own
  k  skip       an answer too: leave it out of this run, ask again next time
  u  unset      take the answer back; the question counts as unanswered again

  n / p         go to the next / previous question
  g             redraw this list
  C-c C-c       apply every answer, then synchronise; refused while one
                question is still unanswered
  q             quit; nothing is written")

(defun citekeep--answer (key)
  (cdr (assoc key citekeep--answers)))

(defun citekeep--draw-resolve ()
  "Redraw the buffer from `citekeep--conflicts' and `citekeep--answers'."
  (let ((inhibit-read-only t)
        (line (line-number-at-pos)))
    (erase-buffer)
    (insert (format "citekeep: %d question(s) from %s\n"
                    (length citekeep--conflicts)
                    (file-name-nondirectory citekeep--resolve-file))
            citekeep--resolve-help "\n\n")
    (dolist (conflict citekeep--conflicts)
      (let* ((incoming (citekeep--get conflict 'incoming))
             (key (citekeep--get incoming 'key))
             (answer (citekeep--answer key))
             (start (point)))
        (insert (format "%s — %s\n" key (citekeep--get conflict 'reason))
                (format "    incoming  %s  %s\n"
                        (or (citekeep--get incoming 'year) "????")
                        (or (citekeep--get incoming 'title) "")))
        (dolist (record (citekeep--get conflict 'existing))
          (insert (citekeep--library-line record) "\n"))
        (insert (if answer
                    (format "    → %s%s\n\n" (car answer)
                            (if (cdr answer) (concat " " (cdr answer)) ""))
                  "    → unanswered\n\n"))
        (put-text-property start (point) 'citekeep-key key)))
    (goto-char (point-min))
    (forward-line (1- line))
    ;; On the first draw the restored line is the header, which carries no
    ;; question: every advertised key would fail before the user had done
    ;; anything. Land on the first question instead.
    (unless (get-text-property (point) 'citekeep-key)
      (goto-char (or (next-single-property-change (point) 'citekeep-key)
                     (point))))))

(defun citekeep--conflict-key-at-point ()
  (or (get-text-property (point) 'citekeep-key)
      (user-error "citekeep: point is not on a question — n and p move to one")))

(defun citekeep--set-answer (verb &optional target)
  (let ((key (citekeep--conflict-key-at-point)))
    (setf (alist-get key citekeep--answers nil t #'equal)
          (and verb (cons verb target)))
    (citekeep--draw-resolve)))

(defun citekeep-resolve-same ()
  "Say this is the entry the library already holds, and complete it."
  (interactive)
  (let* ((key (citekeep--conflict-key-at-point))
         (conflict (seq-find (lambda (c)
                               (equal key (citekeep--get c 'incoming 'key)))
                             citekeep--conflicts))
         (candidates (mapcar (lambda (r) (citekeep--get r 'key))
                             (citekeep--get conflict 'existing))))
    (citekeep--set-answer
     "same" (when (> (length candidates) 1)
              (completing-read "Same as which entry? " candidates nil t)))))

(defun citekeep-resolve-distinct ()
  "Say this is another work, to enter under a key of its own."
  (interactive)
  (citekeep--set-answer "distinct"))

(defun citekeep-resolve-skip ()
  "Leave this local entry out of the current synchronisation."
  (interactive)
  (citekeep--set-answer "skip"))

(defun citekeep-resolve-unset ()
  "Take the answer back."
  (interactive)
  (citekeep--set-answer nil))

(defun citekeep-resolve-refresh ()
  "Redraw the questions and the answers given so far."
  (interactive)
  (citekeep--draw-resolve))

(defun citekeep-resolve-next ()
  "Move to the next question."
  (interactive)
  (let ((key (get-text-property (point) 'citekeep-key)))
    (while (and (not (eobp))
                (equal key (get-text-property (point) 'citekeep-key)))
      (forward-line 1))))

(defun citekeep-resolve-previous ()
  "Move to the previous question."
  (interactive)
  (let ((key (get-text-property (point) 'citekeep-key)))
    (while (and (not (bobp))
                (equal key (get-text-property (point) 'citekeep-key)))
      (forward-line -1))
    (while (and (not (bobp))
                (equal (get-text-property (point) 'citekeep-key)
                       (get-text-property (max (point-min) (1- (point)))
                                          'citekeep-key)))
      (forward-line -1))))

(defun citekeep-resolve-apply ()
  "Send the answers back to citekeep and synchronise again."
  (interactive)
  (let ((unanswered (seq-remove
                     (lambda (conflict)
                       (citekeep--answer
                        (citekeep--get conflict 'incoming 'key)))
                     citekeep--conflicts)))
    (when unanswered
      (user-error "citekeep: %d question(s) still unanswered"
                  (length unanswered))))
  ;; Read every buffer-local value here, before anything switches buffer:
  ;; `with-temp-file' would see the global nil, and write an empty file.
  (let* ((file citekeep--resolve-file)
         (root citekeep--resolve-root)
         (decided (reverse citekeep--answers))
         (buffer (current-buffer))
         (settled (citekeep--send-answers root file decided)))
    (when (and settled (buffer-live-p buffer) (eq buffer (current-buffer)))
      (quit-window t))
    settled))

(defun citekeep--send-answers (root file decided)
  "Synchronise ROOT again, answering FILE's questions with DECIDED.

DECIDED is an alist of (KEY VERB . TARGET), the shape the resolution buffer
keeps. Shared with the single-question path, so that one answer and twenty
travel by the same road."
  (let ((answers (make-temp-file "citekeep-answers"))
        (settled nil))
    (unwind-protect
        (progn
          (with-temp-file answers
            (dolist (entry decided)
              (insert (format "%s %s%s\n" (cadr entry) (car entry)
                              (if (cddr entry)
                                  (concat " " (cddr entry)) "")))))
          ;; Synchronise first, close after: a run that comes back with more
          ;; questions must find its buffer still open.
          (setq settled (citekeep--sync-command root t answers file)))
      (delete-file answers))
    settled))

(defun citekeep--ask-identity (conflict)
  "Ask about one identity CONFLICT.  Return (VERB . TARGET), or nil.

The wording matches `citekeep-fetch''s question, because it is the same
question."
  (let* ((incoming (citekeep--get conflict 'incoming))
         (existing (citekeep--get conflict 'existing))
         (title (or (citekeep--get incoming 'title)
                    (citekeep--get incoming 'key)))
         (same "Same work — complete the library entry from this one")
         (distinct "Distinct work — enter it under a key of its own")
         (skip "Skip — leave it out of this synchronisation")
         (choice (completing-read
                  (format "%s [%s]: "
                          (truncate-string-to-width title 60 nil nil "…")
                          (citekeep--get conflict 'reason))
                  (append (when existing (list same)) (list distinct skip))
                  nil t)))
    (cond
     ((equal choice distinct) '("distinct"))
     ((equal choice skip) '("skip"))
     ((equal choice same)
      (let ((keys (mapcar (lambda (record) (citekeep--get record 'key))
                          existing)))
        (cons "same"
              (when (> (length keys) 1)
                (completing-read "Same as which entry? " keys nil t))))))))

(defun citekeep--open-resolve (root file conflicts)
  "Ask about identity CONFLICTS raised while synchronising FILE below ROOT."
  ;; One question does not need a buffer to be reviewed in: ask it the way
  ;; `citekeep-fetch' does. The buffer earns its weight from the second
  ;; question onwards, where answers are compared and revised before any of
  ;; them is applied.
  (if (= (length conflicts) 1)
      (let* ((conflict (car conflicts))
             (key (citekeep--get conflict 'incoming 'key))
             (answer (citekeep--ask-identity conflict)))
        (when answer
          (citekeep--send-answers
           root file (list (cons key (cons (car answer) (cdr answer)))))))
    (with-current-buffer (get-buffer-create "*citekeep resolve*")
      (citekeep-resolve-mode)
      (setq citekeep--conflicts conflicts
            citekeep--answers nil
            citekeep--resolve-root root
            citekeep--resolve-file file)
      (citekeep--draw-resolve)
      (pop-to-buffer (current-buffer)))))

(provide 'citekeep)
;;; citekeep.el ends here
