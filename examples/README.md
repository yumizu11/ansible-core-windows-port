# Examples

Ready-to-run samples for the native-Windows ansible-core port. All values here are placeholders —
replace IPs, users, and key paths, and supply passwords via environment variables (never commit
real credentials).

Run from the repo root with the installed console script (see the main [README](../README.md)):

```powershell
.\.venv\Scripts\ansible-playbook.exe -i examples\inventory_xxx.yml examples\play_xxx.yml
```

| File | What it shows |
|---|---|
| `play_local.yml` | Manage the **local Windows host** with PowerShell `win_*` modules (`-c local`) |
| `play_linux.yml` + `inventory_ssh.yml.example` | Manage a **remote Linux** host over **SSH** |
| `play_windows.yml` + `inventory_winrm.yml.example` | Manage a **remote Windows** host over **WinRM** |
| `play_windows.yml` + `inventory_psrp.yml.example` | Manage a **remote Windows** host over **PSRP** |

Copy an `*.example` inventory to a real name (e.g. `inventory_ssh.yml`), edit it, and keep it out of
git. For Windows targets, set the password as an env var first:

```powershell
$env:WIN_PW = "..."          # used by the winrm/psrp inventories
```

---

## examples（日本語）

Windows ネイティブ移植版の即実行サンプルです。すべてプレースホルダなので、IP・ユーザー・鍵パスを
置き換え、パスワードは環境変数で渡してください（実際の認証情報はコミットしないこと）。`*.example` の
インベントリは実名にコピーして編集し、git 管理外にしてください。
