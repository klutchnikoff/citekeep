;;; demo-init.el --- Minimal Emacs setup for the citekeep VHS demo -*- lexical-binding: t; -*-

(setq inhibit-startup-screen t
      initial-scratch-message nil
      make-backup-files nil
      auto-save-default nil
      ring-bell-function #'ignore
      use-short-answers t
      citekeep-cite-command "citep")

(menu-bar-mode -1)
(load-theme 'modus-vivendi t)
(fido-vertical-mode 1)

;; `fido-vertical-mode' imposes the `flex' style in the minibuffer, which
;; matches nearly every candidate and would hide the very filtering this demo
;; means to show.  Added last so that it wins, `substring' narrows on a typed
;; word the way the orderless setup of a real configuration does.
(add-hook 'minibuffer-setup-hook
          (lambda () (setq-local completion-styles '(substring basic)))
          90)

(let* ((demo-directory (file-name-directory (or load-file-name buffer-file-name)))
       (repository-root (expand-file-name ".." demo-directory)))
  (load (expand-file-name "editors/emacs/citekeep.el" repository-root)
        nil t)
  (setq citekeep-executable
        (expand-file-name "demo/citekeep-demo" repository-root)))

(setq citekeep-bib-file-function
      (lambda () (getenv "CITEKEEP_DEMO_BIB")))

(add-hook 'find-file-hook
          (lambda ()
            (when (and buffer-file-name
                       (string= (file-name-nondirectory buffer-file-name)
                                "paper.tex"))
              ;; Split in two, the TeX window is 47 columns wide — below the
              ;; 50 of `truncate-partial-width-windows', which truncates the
              ;; line even though `truncate-lines' is nil, so the recording
              ;; shows "$" markers instead of the document. These are the
              ;; three settings `visual-line-mode' makes, applied by hand so
              ;; that the C-e the cassette types keeps its usual meaning.
              (setq-local truncate-partial-width-windows nil)
              (setq-local truncate-lines nil)
              (setq-local word-wrap t)
              (goto-char (point-min))
              (search-forward "Project or personal library:")
              (end-of-line))))

(provide 'demo-init)
;;; demo-init.el ends here
