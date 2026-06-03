# Changes made by the native-Windows port

This is the flat list of files modified by this fork of ansible-core, with a one-line summary each.
Rationale and detail are in [PORTING.md](PORTING.md) (English) / [PORTING_JP.md](PORTING_JP.md)
(日本語). Section letters refer to PORTING.md §3. Base: ansible-core `2.21.0`.

Provided to satisfy the GPL requirement to state the changes made to the licensed work.

## Modified files (`lib/ansible/…`)

| File | Change | §|
|---|---|---|
| `cli/__init__.py` | Auto re-exec in UTF-8 mode on Windows; UTF-8-mode-aware locale check; `check_blocking_io` catches `OSError` | B, A |
| `utils/display.py` | Guard `termios`/`tty` imports; `os.get_terminal_size` for width; `unicodedata` `wcwidth` fallback; guard `register_at_fork`/`getuid`; `setraw` default arg; Windows `msvcrt` prompt path | A, K |
| `utils/multiprocessing.py` | Fall back to platform-default context when `fork` is unavailable | C |
| `executor/process/worker.py` | Spawn worker bootstrap (CLIARGS, plugin loader, verbosity); guard `setsid`/`setpgid`/`killpg`/`O_NONBLOCK` | C |
| `executor/module_common.py` | AnsiballZ: `is_package` via `basename`; zip arcnames POSIX (`/`.join, `as_posix`); module-FQN path normalization | H, D |
| `plugins/loader.py` | Only warn on `PluginLoader(aliases=…)` deprecation when aliases are non-empty (spawn unpickle noise) | C |
| `plugins/shell/__init__.py` | `ShellBase.join_path` uses `posixpath.join` (remote/POSIX paths) | D |
| `plugins/action/__init__.py` | Skip `<shell> -c '…'` wrapping when the shell is a Windows/PowerShell shell | F |
| `plugins/connection/__init__.py` | Guard `fcntl`; `connection_lock`/`unlock` no-op when unavailable | A |
| `plugins/connection/local.py` | Guard `pty`/`getuid`; default `powershell` shell on Windows; Windows exec (no `/bin/sh`, `shlex.split`, strip `PSModulePath`) | A, F |
| `plugins/connection/ssh.py` | Guard `fcntl`/`pty`; threaded pipe reader/selector for non-blocking I/O; strip `ControlMaster`/`ControlPersist`/`ControlPath` on Windows; strip embedded `"` from `-o` values (`IdentityFile`/`User`) so `ssh.exe` arg parsing isn't corrupted | A, G |
| `plugins/connection/psrp.py` | Convert connection kwargs to native types (`AnsibleTagHelper.as_native_type`) for pyspnego/Cython | J |
| `parsing/dataloader.py` | `RE_TASKS` accepts both `/` and `\` separators | D |
| `parsing/vault/__init__.py` | Drop `fcntl`; fd check via `os.fstat` | A |
| `constants.py` | `import os`; add `_pathlist()` helper for platform-aware path-list defaults | E |
| `config/base.yml` | ~20 path-list defaults routed through `_pathlist(...)` | E |
| `_internal/_locking.py` | `named_mutex` uses `msvcrt.locking` on Windows / `fcntl.flock` on POSIX | L |
| `_internal/_templating/_template_vars.py` | Guard `pwd` (uid fallback); `platform.node()` for the template host | A |
| `_internal/_datatag/_tags.py` | `Origin` absolute-path check via `os.path.isabs` | D |
| `utils/collection_loader/_collection_finder.py` | `get_data` absolute-path check via `os.path.isabs` | D |
| `module_utils/basic.py` | Guard `grp`/`pwd`/`fcntl` imports (imported on the controller via `DataLoader`) | A |
| `module_utils/ansible_release.py` | Materialize broken symlink (was the text `../release.py`) | M |
| `modules/systemd.py` | Materialize broken symlink (was the text `systemd_service.py`); otherwise `ansible.builtin.systemd` fails with "missing interpreter line" | M |
| `plugins/test/*.yml` (15 files) | Materialize broken same-directory symlinks for jinja-test alias docs (`change.yml`→`changed.yml`, `skip.yml`→`skipped.yml`, …) | M |

## New files (this fork)

| File | Purpose |
|---|---|
| `README.md` / `README_JP.md` | Windows-port readme (EN/JP) |
| `README.upstream.md` | Preserved original upstream Ansible README |
| `PORTING.md` / `PORTING_JP.md` | Technical porting write-up + re-port guide (EN/JP) |
| `CHANGES_WINDOWS.md` | This file |

## Not modified but relevant

* Upstream **symlinks** become plain text files on a Windows checkout. The runtime-affecting ones
  under `lib/` are materialized (real content copied in): `module_utils/ansible_release.py`,
  `modules/systemd.py`, and 15 `plugins/test/*.yml` alias docs. `bin/*` and many `test/` symlinks are
  stored as real git symlinks (mode 120000) instead; `bin/` also ships `.cmd` launchers for Windows.
  Remaining same-directory symlinks under `test/` (test-suite only) are not materialized.
