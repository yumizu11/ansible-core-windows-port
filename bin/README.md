# `bin/` — launchers

This directory contains two kinds of launchers for the Ansible CLIs:

* **`ansible-playbook`, `ansible`, … (no extension)** — the upstream **POSIX symlinks** into
  `../lib/ansible/cli/*.py`. These are what Linux/macOS use when running from a source checkout.
  (On a Windows checkout they appear as small text files; ignore them there.)

* **`*.cmd` (e.g. `ansible-playbook.cmd`)** — **Windows launchers** added by this fork. Each one runs
  the corresponding CLI from this source tree:

  ```cmd
  set "PYTHONPATH=<repo>\lib;%PYTHONPATH%"
  python <repo>\lib\ansible\cli\<cli>.py %*
  ```

## Using the Windows launchers

Requirements: **Python 3.12+** on `PATH` (or set `ANSIBLE_PYTHON` to a specific interpreter, e.g. a
virtualenv's `python.exe`). With this on `PATH`, the launchers work straight from the source tree —
no `pip install` needed.

```powershell
# add bin to PATH for the session, then use the CLIs by name:
$env:Path = "$PWD\bin;$env:Path"
ansible-playbook --version
ansible-playbook -i "localhost," -c local examples\play_local.yml

# or call a launcher directly:
.\bin\ansible-playbook.cmd --version

# or point at a specific interpreter (e.g. a venv):
$env:ANSIBLE_PYTHON = "C:\path\to\.venv\Scripts\python.exe"
.\bin\ansible-playbook.cmd --version
```

> **Tip:** `pip install -e .` also installs proper console-script executables
> (`…\Scripts\ansible-playbook.exe`), which is the recommended way to run if you have a virtualenv.
> The `*.cmd` launchers are for running directly from the source tree.

Notes:

* `ansible-test` has no `.cmd` launcher — it is POSIX-only and out of scope for the Windows port.
* The launchers forward all arguments (`%*`) and propagate the CLI's exit code.
