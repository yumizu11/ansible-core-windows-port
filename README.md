[![Repository License](https://img.shields.io/badge/license-GPL%20v3.0-brightgreen.svg)][copying]

# ansible-core — native Windows port (unofficial)

**日本語版: [README_JP.md](README_JP.md)**

This repository is an **unofficial fork** of [ansible-core](https://github.com/ansible/ansible)
modified so that the **Ansible controller runs natively on Windows** — i.e. you can run
`ansible-playbook` (and the other CLIs) directly on a Windows machine, with no WSL, Cygwin, or
Linux VM.

Upstream ansible-core officially supports only a POSIX control node; on Windows the documented
approach is to use WSL. This fork removes/guards the POSIX-only assumptions in the **controller**
so it works on a stock Windows + CPython install.

> [!IMPORTANT]
> **This is not an official Ansible / Red Hat project.** "Ansible" is a trademark of Red Hat, Inc.
> This fork is not affiliated with, endorsed by, or supported by the Ansible project or Red Hat.
> It is licensed under **GPL-3.0-or-later**, the same as upstream ansible-core. Based on
> ansible-core `2.21.0` (the `stable-2.21` line). For production automation, prefer official Ansible.

## What works

Verified end-to-end on a Windows controller (Windows 11 + CPython 3.12):

| Connection | Target managed | Modules | Verified against |
|---|---|---|---|
| `local` | the Windows host itself | PowerShell (`ansible.windows.win_*`) | local machine |
| `ssh` | remote **Linux** | Python (`ping`, `command`, `setup`, `copy`, …) | AWS EC2 (RHEL 9) |
| `winrm` | remote **Windows** | PowerShell | Windows Server 2025 (HTTPS) |
| `psrp` | remote **Windows** | PowerShell | Windows Server 2025 (HTTPS) |

Also working: fact gathering, file transfer (sftp/scp and PowerShell copy), idempotency,
passwordless `become` (sudo) over SSH, interactive prompts (`vars_prompt`, `pause`, `--ask-*`),
and the CLIs `ansible`, `ansible-playbook`, `ansible-doc`, `ansible-config`, `ansible-inventory`,
`ansible-vault`, and `ansible-galaxy`.

See **[PORTING.md](PORTING.md)** for the full technical write-up of every change (and a guide for
re-porting future Ansible versions). A flat list of modified files is in
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md).

## Requirements

* **Windows 10/11 or Windows Server** (x64).
* **CPython 3.12 or newer** (the controller requires 3.12+; it is also used in UTF-8 mode — handled
  automatically, see below).
* For `ssh` connections: the built-in Windows **OpenSSH client** (`ssh.exe`, included in modern Windows).
* For `winrm` / `psrp` connections: `pip install pywinrm` / `pip install pypsrp` respectively, and a
  reachable WSMan listener on the target.

## Installation

```powershell
# from the repository root (this folder)
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .

# optional, for managing Windows targets:
.\.venv\Scripts\python.exe -m pip install pywinrm pypsrp
```

The CLIs are then available as `\.venv\Scripts\ansible-playbook.exe`, `ansible.exe`, etc.

> [!TIP]
> Run the installed **console scripts** (`ansible-playbook.exe`), or activate the venv and use
> `ansible-playbook`. Avoid `python -m ansible.cli.playbook` **from the repository root**, because
> the repo's own `ansible\` folder would shadow the installed package on `sys.path`.

## Quick start

### Manage the local Windows host (`connection=local`)

```yaml
# play_local.yml
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.windows.win_ping:
    - ansible.windows.win_command: whoami
```

```powershell
ansible-galaxy collection install ansible.windows
ansible-playbook -i "localhost," -c local play_local.yml
```

### Manage a remote Linux host over SSH

```yaml
# inventory_ssh.yml
all:
  hosts:
    linux1:
      ansible_host: 203.0.113.10
      ansible_user: ec2-user
      ansible_connection: ssh
      ansible_ssh_private_key_file: 'C:\Users\you\.ssh\key.pem'
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no'
```

```powershell
$env:ANSIBLE_HOST_KEY_CHECKING = "False"
ansible-playbook -i inventory_ssh.yml your_play.yml
```

### Manage a remote Windows host over WinRM or PSRP

```yaml
# inventory_win.yml  (HTTPS / self-signed cert example)
all:
  hosts:
    win1:
      ansible_host: 203.0.113.20
      ansible_user: Administrator
      ansible_password: "{{ lookup('env', 'WIN_PW') }}"
      ansible_connection: winrm          # or: psrp
      ansible_port: 5986
      ansible_winrm_transport: ntlm       # psrp: ansible_psrp_auth: ntlm
      ansible_winrm_scheme: https         # psrp: ansible_psrp_protocol: https
      ansible_winrm_server_cert_validation: ignore   # psrp: ansible_psrp_cert_validation: ignore
```

```powershell
$env:WIN_PW = "<password>"
ansible-playbook -i inventory_win.yml your_play.yml
```

## Notes & ergonomics

* **No special environment variables are required.** UTF-8 mode is enabled automatically (the CLI
  re-execs itself with `PYTHONUTF8=1` on Windows when needed), config path defaults are made
  platform-aware, and `connection=local` defaults to the PowerShell shell on Windows.
* **Windows OpenSSH has no connection multiplexing**; the SSH connection automatically drops
  `ControlMaster`/`ControlPersist`/`ControlPath` on Windows.

## Known limitations

* Python modules can only run on **remote POSIX** targets (over SSH). Running Python modules against
  the Windows host itself (`connection=local`) is not a goal — use PowerShell `win_*` modules there.
* **Password-prompted `become` over SSH** is not verified (the controller-side PTY path is skipped on
  Windows). Passwordless sudo works.
* Persistent connections (`network_cli`/`httpapi` via the connection daemon) are not ported.
* `ansible-console` (interactive REPL) and `ansible-test` (POSIX-only) are out of scope.

## Relationship to upstream Ansible / attribution

This is a derivative work of ansible-core. The original project README is preserved at
[README.upstream.md](README.upstream.md). All upstream copyright notices and license headers are
retained. Changes made by this fork are summarized in [PORTING.md](PORTING.md) and
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md), as required by the GPL.

* Upstream project: <https://github.com/ansible/ansible>
* Upstream documentation: <https://docs.ansible.com/>

## License

GNU General Public License v3.0 or later. See [COPYING] for the full text.

[copying]: COPYING
