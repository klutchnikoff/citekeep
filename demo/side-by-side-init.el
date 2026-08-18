;;; side-by-side-init.el --- Side-by-side setup for the citekeep VHS demo -*- lexical-binding: t; -*-

(let ((demo-directory (file-name-directory (or load-file-name buffer-file-name))))
  (load (expand-file-name "demo-init.el" demo-directory) nil t))

(defvar citekeep-demo-reveal-delay 0.5
  "Seconds the demo holds the previous view before focusing a new record.")

(defvar-local citekeep-demo--window-start nil
  "Where the bibliography window was looking before the last refresh.")

(defun citekeep-demo-remember-view ()
  "Record where the bibliography window is looking, before a refresh."
  (when-let ((window (get-buffer-window (current-buffer) t)))
    (setq citekeep-demo--window-start (window-start window))))

(defun citekeep-demo-follow-latest-entry ()
  "Reveal the BibTeX record citekeep has just materialised.
Hold the previous view for `citekeep-demo-reveal-delay' seconds, so that
the record is seen arriving below what the file already held rather than
simply being there, then bring it to the top of the window."
  (let ((buffer (current-buffer))
        (window (get-buffer-window (current-buffer) t)))
    (when (and window citekeep-demo--window-start)
      (set-window-start window (min citekeep-demo--window-start (point-max))))
    (run-at-time
     citekeep-demo-reveal-delay nil
     (lambda ()
       (when (buffer-live-p buffer)
         (with-current-buffer buffer
           (goto-char (point-max))
           (when (re-search-backward "^@[[:alpha:]]+{" nil t)
             (beginning-of-line)
             (let ((entry-start (point))
                   (window (get-buffer-window buffer t)))
               (when window
                 (set-window-point window entry-start)
                 (set-window-start window entry-start))))))))))

(defun citekeep-demo-open-bib-beside-tex ()
  "Open the isolated project bibliography beside its LaTeX document."
  (when (and buffer-file-name
             (string= (file-name-nondirectory buffer-file-name) "paper.tex"))
    (let ((tex-window (selected-window)))
      (set-window-buffer tex-window (current-buffer))
      (split-window-right)
      (other-window 1)
      (find-file (getenv "CITEKEEP_DEMO_BIB"))
      (visual-line-mode 1)
      (setq-local truncate-lines nil)
      (add-hook 'before-revert-hook
                #'citekeep-demo-remember-view nil t)
      (add-hook 'after-revert-hook
                #'citekeep-demo-follow-latest-entry nil t)
      (goto-char (point-min))
      (set-window-hscroll (selected-window) 0)
      (select-window tex-window)
      (set-window-hscroll tex-window 0))))

(add-hook 'find-file-hook #'citekeep-demo-open-bib-beside-tex t)

(provide 'side-by-side-init)
;;; side-by-side-init.el ends here
