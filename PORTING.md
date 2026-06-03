# Porting ansible-core's controller to native Windows

**日本語版: [PORTING_JP.md](PORTING_JP.md)**

This document explains *what* was changed to make the ansible-core **controller** run natively on
Windows, *why*, and *how to re-apply the same work to a future Ansible version*. It is the primary
reference for maintaining this fork.

Base version: ansible-core `2.22.0.dev0` (devel). A flat per-file list is in
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md).

---

## 1. Mental model: controller vs. module side

Ansible code splits into two execution contexts:

* **Controller side** — everything that runs where you invoke `ansible-playbook` (CLI, executor,
  inventory, templating, connection plugins, AnsiballZ assembly). **This is what we make run on
  Windows.**
* **Module side** — `lib/ansible/modules/*` and most of `lib/ansible/module_utils/*`. These are
  shipped to and executed on the **managed node** (usually Linux). They are *not* a concern when the
  target is remote Linux (they run there) — except that a handful of `module_utils` files are also
  imported on the controller (e.g. `module_utils/basic.py` via `DataLoader`), so those must at least
  *import* on Windows.

Guiding principle for every change: **keep upstream (POSIX) behavior byte-for-byte identical**, and
confine Windows behavior to `os.name == 'nt'` branches or `try/except ImportError` guards, so the
fork stays small and rebasable.

## 2. Build & verify

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install pywinrm pypsrp   # for winrm/psrp
```

Smoke tests (no env vars needed):

```powershell
.\.venv\Scripts\ansible-playbook.exe --version
.\.venv\Scripts\ansible-playbook.exe --syntax-check -i "localhost," play.yml
```

The controller requires **CPython 3.12+** (`lib/ansible/cli/__init__.py:_PY_MIN`), and parts of the
code use PEP 695 syntax, so 3.10/3.11 cannot even import the package.

---

## 3. Changes by category

### A. Importability — guard POSIX-only stdlib imports

`Display` is imported almost everywhere, and it (plus a few other modules in the import chain)
imported `fcntl`/`termios`/`tty`/`pwd`/`pty` unconditionally, so the package failed to import on
Windows before anything ran.

Pattern used:

```python
try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]
# ... then at call sites:  if fcntl is not None: ...
```

Files:

* `utils/display.py` — guarded `termios`/`tty` (and dropped the now-unused `fcntl`/`struct`).
  `setraw()`'s default arg `when=termios.TCSAFLUSH` was evaluated at import time → changed to
  `when=None` and resolved inside. `_set_column_width()` replaced the `fcntl.ioctl(TIOCGWINSZ)`
  call with the cross-platform `os.get_terminal_size()`. The libc `wcwidth`/`wcswidth` lookup
  (`ctypes.cdll.LoadLibrary(find_library('c'))`) fails on Windows → wrapped in `try/except` with a
  pure-Python `unicodedata`-based `_char_width()` fallback.
* `_internal/_templating/_template_vars.py` — guarded `pwd`; `pwd.getpwuid()` falls back to the
  numeric uid; `os.uname()[1]` → `platform.node()`.
* `plugins/connection/__init__.py` — guarded `fcntl`; `connection_lock()/unlock()` no-op when
  unavailable (TODO: a real cross-platform lock).
* `plugins/connection/local.py` — guarded `pty`; guarded `os.getuid()`.
* `parsing/vault/__init__.py` — dropped `fcntl`; the "is this an fd?" check uses `os.fstat()`.
* `module_utils/basic.py` — guarded `grp`/`pwd`/`fcntl` (imported on the controller via `DataLoader`).
* `cli/__init__.py` — `check_blocking_io()` catches `OSError` from `os.get_blocking()` (unsupported
  on Windows console/pipe handles).

### B. Locale / UTF-8 mode

Ansible requires UTF-8 for stdio/filesystem/locale; on a Japanese Windows the ANSI code page is
cp932, which `open()` would otherwise use. UTF-8 mode (PEP 540) can only be enabled at interpreter
start, so:

* `cli/__init__.py` — at the very top, on `os.name == 'nt'` and `not sys.flags.utf8_mode`, the CLI
  re-execs itself once with `PYTHONUTF8=1` via `subprocess.run([sys.executable, *sys.orig_argv[1:]], …)`
  and exits with its return code. **Use `sys.executable`, not `sys.orig_argv[0]`** — under a
  console-script launcher the latter is a non-venv base python that cannot import `ansible`. A guard
  env var prevents an infinite re-exec loop.
* `cli/__init__.py:initialize_locale()` — on Windows, accept the locale when `sys.flags.utf8_mode` is
  set (instead of inspecting the legacy code page), otherwise emit a clear "set PYTHONUTF8=1" error.

### C. Process model — fork → spawn + worker bootstrap

`utils/multiprocessing.py` hard-coded `multiprocessing.get_context('fork')`. Windows only has
`spawn`. `WorkerProcess` (`executor/process/worker.py`) was written around fork (inherited memory/fds,
`os.setsid`/`os.setpgid`/`os.killpg`, POSIX signals).

* `utils/multiprocessing.py` — fall back to the platform default context when `fork` is unavailable.
* `executor/process/worker.py`:
  * Guarded `os.setsid`/`os.setpgid` (in `_detach`), `os.killpg` (in `_term`), and `os.O_NONBLOCK`
    (use `getattr(os, 'O_NONBLOCK', 0)`).
  * Added `_bootstrap_worker_environment()` (called first in `run()`): under **spawn** the child does
    not inherit the controller's initialized globals, so it restores `context.CLIARGS`, calls
    `init_plugin_loader()` (installs the collection finder so `ansible.builtin.*` resolves), and sets
    `display.verbosity` from CLIARGS (so `-vvv` works in the worker). This is idempotent and a no-op
    under fork.

> **Why spawn and not threads?** A thread-based worker would avoid pickling, but `Display` is a
> singleton whose queue-proxying is per-process (it asserts `parent_process() is not None`), so the
> process model maps more cleanly onto spawn. Spawn already pickled the worker args successfully; only
> the controller-global re-initialization above was missing.

A spawn side effect: the worker unpickles `shared_loader_obj`, and `PluginLoader.__setstate__` called
`__init__` with `aliases={}`, firing the "Instantiating … PluginLoader with aliases is deprecated"
warning for every plugin type. Fixed in `plugins/loader.py` by only warning when `aliases` is
truthy.

### D. Cross-platform path handling

The recurring bug class: code that builds **remote/POSIX** or **zip** paths using `os.path` (which is
`\`-based on Windows) or checks absoluteness with `startswith('/')`.

* `_internal/_datatag/_tags.py` — `Origin._post_validate` used `path.startswith('/')` → `os.path.isabs`.
* `utils/collection_loader/_collection_finder.py` — `get_data` used `path[0] == '/'` → `os.path.isabs`.
* `parsing/dataloader.py` — `RE_TASKS` was built from `os.path.sep` (unescaped `\` broke the regex) →
  a separator-agnostic `r'(?:^|[\\/])+tasks[\\/]?$'`.
* `plugins/shell/__init__.py` — `ShellBase.join_path` used `os.path.join` → **`posixpath.join`**. Shell
  plugins build paths for the (POSIX) remote target, so they must always join with `/`. (The
  `powershell` shell already overrides this with `ntpath`.) This bug produced remote tmp dirs like
  `~/.ansible/tmp\ansible-tmp-…`.

### E. Config path defaults (`config/base.yml`)

Every path-list default (`collections`, `roles`, every plugin-type path) was a `:`-joined,
`/usr/share/...`-style POSIX string, e.g. `{{ ANSIBLE_HOME ~ "/collections:/usr/share/ansible/collections" }}`.
On Windows the config manager splits path lists with `os.pathsep` (`;`) and the `:` collided with the
drive letter (`C:\…`), corrupting `COLLECTIONS_PATHS` and breaking `ansible-galaxy`.

* `constants.py` — added a `_pathlist(home, *system)` helper (visible to the default-templating
  context via `vars()`), which joins with `os.pathsep` and **omits the POSIX `/usr/share`+`/etc`
  system paths on Windows**. POSIX output is byte-identical.
* `config/base.yml` — ~20 templated defaults rewritten to `{{ _pathlist(ANSIBLE_HOME ~ "/x", "/usr/share/ansible/x") }}`.

### F. Connection: `local` + PowerShell on Windows

On a Windows controller, modules executed against the local host are PowerShell modules, and the
generated command line is a self-contained `powershell.exe … -EncodedCommand <base64>`, not a
`/bin/sh -c '…'`.

* `plugins/connection/local.py`:
  * `Connection._shell_type = 'powershell'` on `os.name == 'nt'` (so `ansible_shell_type` is not
    required; an explicit value still wins).
  * In `exec_command`, when the shell `_IS_WINDOWS`: don't use `/bin/sh` as the executable
    (`executable=None`); `shlex.split()` the command and run the interpreter directly (so cmd.exe does
    not mangle the POSIX quoting around `-EncodedCommand`); and **strip `PSModulePath` from the child
    env** (case-insensitively — Windows `os.environ` upper-cases keys to `PSMODULEPATH`). Without the
    last step, Windows PowerShell 5.1 inherits a PowerShell-7-polluted `PSModulePath` (when launched
    from a pwsh session) and loads incompatible PS7 modules → `Get-FileHash not recognized` and
    `ObjectSecurity … member already present` ETS errors.
* `plugins/action/__init__.py` — `_low_level_execute_command` skips the `<shell> -c '…'` wrapping when
  `_connection._shell._IS_WINDOWS`.

### G. Connection: `ssh` (manage remote Linux)

`plugins/connection/ssh.py` used `fcntl` (set pipes non-blocking) + `selectors` to read the `ssh.exe`
subprocess. Windows cannot `select` on pipes, has no `fcntl`/`pty`.

* Guarded `import fcntl`/`import pty`; added `import threading`.
* Added `_ThreadedPipeReader` and `_ThreadedSelector` (module level): on platforms without `fcntl`,
  each pipe is drained by a background thread into a buffer, and a minimal selector-compatible object
  reports readiness. `_bare_run`'s read loop branches on `fcntl is not None`; the loop body is
  unchanged (`stdout_obj`/`stderr_obj` + `key.fileobj.read()`), so the POSIX path is identical.
* `pty.openpty()` guarded with `if pty is not None` (falls back to pipes).
* **`_build_command` strips `ControlMaster`/`ControlPersist`/`ControlPath` `-o` options on
  `os.name == 'nt'`** and sets `_persistent=False` — Windows OpenSSH has no connection multiplexing,
  which otherwise fails the connection.
* Uses the built-in Windows OpenSSH (`ssh.exe`/`sftp.exe`/`scp.exe`).

### H. AnsiballZ packaging (the subtle one)

When the controller assembles the Python module zip, arcnames must be POSIX, and package detection
must be separator-agnostic. In `executor/module_common.py`:

* `LegacyModuleUtilLocator._find_module` — `is_package = info.origin.endswith('/__init__.py')` failed
  because on Windows `info.origin` ends with `\__init__.py`. Result: packages were zipped as
  `_internal.py` instead of `_internal/__init__.py`, so the remote raised
  `ModuleNotFoundError: ... _internal is not a package`. Fixed to
  `os.path.basename(info.origin) == '__init__.py'`. **This was the key remote-execution bug.**
* `LegacyModuleUtilLocator.output_path` (the zip arcname) used `os.path.join` → `'/'.join`.
* `_make_module embed` arcnames used `str(rel_path)` → `rel_path.as_posix()`.
* `_get_ansible_module_fqn` normalized `\`→`/` (and the `CORE_LIBRARY_PATH_RE` `site_packages`), else
  Windows paths failed the regex and fell back to `ansible.legacy.<mod>`, breaking relative
  `..module_utils.X` resolution (seen first with `win_command`'s C# `Process` util).

### I. Connection: `winrm` (manage remote Windows)

`plugins/connection/winrm.py` imports cleanly on Windows (no POSIX deps). Requires `pip install
pywinrm`. No code change needed; verified E2E over HTTPS/NTLM against Windows Server 2025.

### J. Connection: `psrp` (manage remote Windows)

`plugins/connection/psrp.py` imports cleanly (requires `pip install pypsrp`), but failed at auth with
`Argument 'username' has incorrect type (expected str, got _AnsibleTaggedStr) … Cython is stricter`.
Ansible's config/inventory values are **tagged strings** (str subclasses); the Windows SSPI backend in
`pyspnego` is Cython and rejects subclasses (pywinrm tolerates them because it is pure Python).

* `psrp.py:_build_kwargs` — convert `_psrp_conn_kwargs`/`_psrp_runspace_kwargs` values with
  `AnsibleTagHelper.as_native_type(...)` (from `ansible.module_utils._internal._datatag`).

Verified E2E over HTTPS/NTLM against Windows Server 2025. (Note: `psrp` to *localhost* with a *local*
account over loopback can still fail NTLM — that is a Windows SSPI loopback nuance, not an ansible
bug; real remote hosts work.)

### K. Interactive prompts (`msvcrt`)

`Display.prompt` (used by `vars_prompt`, `--ask-vault-pass`, `--ask-*-pass`) uses `getpass`/`input`
and already works on Windows. `Display.prompt_until` (used by the `pause` module and friends) used
`termios` raw mode + non-blocking fd reads.

* `utils/display.py` — `prompt_until` no longer raises on Windows; after the not-a-tty check it
  branches to a new `_read_console_stdin_windows()` that uses `msvcrt` (`kbhit`/`getwch`) with the
  same timeout / interrupt (Ctrl+C) / complete (Enter) / backspace / echo semantics.

### L. Locking

* `_internal/_locking.py` — `named_mutex` uses `fcntl.flock` on POSIX and `msvcrt.locking` on Windows
  (same blocking context-manager API).

### M. Broken symlinks (Windows checkout artifact)

When the repo is extracted on Windows without symlink support, symlinks become text files containing
their target path. These bite at runtime because the file's "content" is just the link target string.

Two flavors, both found and fixed:

* **Parent-relative** (target starts with `../`): e.g. `module_utils/ansible_release.py` → `../release.py`.
* **Same-directory** (target is a bare sibling filename, *no* `../` — easy to miss when scanning only
  for `../`): e.g. `modules/systemd.py` → `systemd_service.py`, and 15 jinja-test alias docs under
  `plugins/test/*.yml` (`change.yml` → `changed.yml`, `skip.yml` → `skipped.yml`, …).

The `systemd` case is instructive: the controller reads `modules/systemd.py`, gets the text
`systemd_service.py` (no `#!` interpreter line), and fails with
`module (ansible.legacy.systemd) is missing interpreter line` only when a play uses that module.

**Fix:** all broken symlinks under `lib/` that affect runtime are **materialized** (the real target
content is copied in), since a Windows checkout cannot follow symlinks at runtime. (`bin/` and many
`test/` symlinks are instead stored as real git symlinks, mode 120000 — fine on Linux; `bin/` also
ships `.cmd` launchers for Windows.) When detecting these, match both `../foo` *and* bare
`sibling.py` whose content resolves to an existing file in the same directory.

---

## 4. Re-porting checklist for a future Ansible version

Apply the patterns above to a fresh upstream checkout, roughly in this order:

1. **Get it to import.** Run `ansible-playbook --version`; fix each `ImportError`/`AttributeError` by
   grep-guarding new POSIX imports (`fcntl|pwd|grp|pty|termios|tty|resource`) in the controller import
   chain. Re-check `cli/__init__.py` (locale + blocking-io) and the UTF-8 re-exec.
2. **Process model.** Confirm `utils/multiprocessing.py` fork fallback and the `worker.py`
   `_bootstrap_worker_environment()` + POSIX guards survive any refactor.
3. **Path defaults.** Re-check `config/base.yml` path lists and the `constants._pathlist` helper.
4. **Run a local PowerShell play** (`win_ping`/`win_command`) and a **remote Linux SSH play**
   (`ping`/`command`/`copy`); fix any new `os.path.join`/`startswith('/')`/`endswith('/__init__.py')`
   on remote or zip paths (grep: `endswith('/`, `[0] == '/'`, `os.path.join` in `module_common.py`,
   `shell/`, `action/`).
5. **Connections.** Re-apply the `ssh.py` threaded reader + ControlMaster strip, `local.py` PowerShell
   handling, and `psrp.py` tagged-string conversion. `winrm.py` usually needs nothing.
6. **Symlinks.** Re-materialize `module_utils/ansible_release.py` (and handle `bin/` for distribution).

Useful greps when something fails on Windows but not Linux:

```text
endswith('/__init__.py')      # package detection
startswith('/') | [0] == '/'  # absolute-path checks
os.path.join | os.path.sep    # remote/zip path construction
import fcntl|pwd|grp|pty|termios|tty|resource   # new POSIX imports
os.fork|setsid|killpg|getuid|getpgrp            # POSIX process/identity calls
```

## 5. Known limitations / not done

* Python modules run only on remote POSIX targets (not `connection=local` against Windows itself).
* Password-prompted `become` over SSH (controller PTY path skipped); passwordless sudo works.
* Persistent-connection daemon (`network_cli`/`httpapi`), `ansible-console`, `ansible-test`.
* `connection_lock()` is a no-op on Windows; `bin/` symlinks are not materialized for distribution.
