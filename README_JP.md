[![Repository License](https://img.shields.io/badge/license-GPL%20v3.0-brightgreen.svg)][copying]

# ansible-core — Windows ネイティブ移植版（非公式）

**English: [README.md](README.md)**

> ⚠️ **注意: `main` ブランチは ansible-core の `devel` を追跡しています。**
> `main` は upstream の `devel` ブランチの**ある時点のスナップショット**（現在は `2.22.0.dev0`）を
> 基にした Windows ネイティブ移植です。`devel` は未リリースで頻繁に変化するため、本ブランチは最新の
> upstream と乖離する可能性があり、**不具合や誤動作を含む場合があります**。動作検証済みの安定版が
> 必要な場合は、リリースブランチ（例: **[`stable-2.21`](../../tree/stable-2.21)**）とその Windows
> リリースパッケージを使用してください。

本リポジトリは [ansible-core](https://github.com/ansible/ansible) の**非公式フォーク**で、
**Ansible コントローラを Windows 上でネイティブに動作**させるよう改変したものです。WSL・Cygwin・
Linux VM を使わず、Windows マシン上で直接 `ansible-playbook`（および他の CLI）を実行できます。

upstream の ansible-core は公式にはコントローラ（制御ノード）を POSIX のみサポートし、Windows では
WSL の利用が案内されています。本フォークは**コントローラ側**の POSIX 専用前提を除去・ガードし、
素の Windows + CPython で動作するようにしています。

> [!IMPORTANT]
> **本プロジェクトは Ansible / Red Hat の公式プロジェクトではありません。** 「Ansible」は
> Red Hat, Inc. の商標です。本フォークは Ansible プロジェクトや Red Hat とは無関係で、承認・
> サポートも受けていません。ライセンスは upstream と同じ **GPL-3.0-or-later** です。ベースは
> ansible-core `2.22.0.dev0`（`devel` 系）。本番運用には公式 Ansible の利用を推奨します。

## 動作確認済みの機能

Windows コントローラ（Windows 11 + CPython 3.12）で end-to-end 検証済み:

| 接続方式 | 管理対象 | モジュール | 検証環境 |
|---|---|---|---|
| `local` | Windows ホスト自身 | PowerShell (`ansible.windows.win_*`) | ローカルマシン |
| `ssh` | リモート **Linux** | Python (`ping`/`command`/`setup`/`copy` 等) | AWS EC2 (RHEL 9) |
| `winrm` | リモート **Windows** | PowerShell | Windows Server 2025 (HTTPS) |
| `psrp` | リモート **Windows** | PowerShell | Windows Server 2025 (HTTPS) |

その他: ファクト収集、ファイル転送（sftp/scp および PowerShell copy）、冪等性、パスワード不要な
`become`(sudo) over SSH、対話プロンプト（`vars_prompt`/`pause`/`--ask-*`）、および CLI 一式
（`ansible` / `ansible-playbook` / `ansible-doc` / `ansible-config` / `ansible-inventory` /
`ansible-vault` / `ansible-galaxy`）も動作します。

すべての変更点の技術的詳細（および将来の Ansible バージョンを移植する際の手引き）は
**[PORTING_JP.md](PORTING_JP.md)** を参照してください。変更ファイルの一覧は
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md) にあります。

## 必要要件

* **Windows 10/11 または Windows Server**（x64）。
* **CPython 3.12 以上**（コントローラは 3.12+ が必須。UTF-8 モードでも実行されますが、これは自動処理）。
* `ssh` 接続: Windows 標準の **OpenSSH クライアント**（`ssh.exe`。最近の Windows に同梱）。
* `winrm` / `psrp` 接続: それぞれ `pip install pywinrm` / `pip install pypsrp`、および対象側で
  WSMan リスナーが到達可能であること。

## インストール

```powershell
# リポジトリのルート（このフォルダ）で
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .

# Windows 対象を管理する場合（任意）:
.\.venv\Scripts\python.exe -m pip install pywinrm pypsrp
```

これで `\.venv\Scripts\ansible-playbook.exe` などの CLI が利用可能になります。

> [!TIP]
> インストールされた**コンソールスクリプト**（`ansible-playbook.exe`）を使うか、venv を有効化して
> `ansible-playbook` を使ってください。**リポジトリのルートから** `python -m ansible.cli.playbook`
> を実行するのは避けてください（リポジトリ内の `ansible\` フォルダが `sys.path` 上でインストール済み
> パッケージを隠してしまうため）。

## クイックスタート

### ローカル Windows ホストを管理（`connection=local`）

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

### リモート Linux を SSH で管理

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

### リモート Windows を WinRM / PSRP で管理

```yaml
# inventory_win.yml  (HTTPS / 自己署名証明書の例)
all:
  hosts:
    win1:
      ansible_host: 203.0.113.20
      ansible_user: Administrator
      ansible_password: "{{ lookup('env', 'WIN_PW') }}"
      ansible_connection: winrm          # または: psrp
      ansible_port: 5986
      ansible_winrm_transport: ntlm       # psrp の場合: ansible_psrp_auth: ntlm
      ansible_winrm_scheme: https         # psrp の場合: ansible_psrp_protocol: https
      ansible_winrm_server_cert_validation: ignore   # psrp の場合: ansible_psrp_cert_validation: ignore
```

```powershell
$env:WIN_PW = "<パスワード>"
ansible-playbook -i inventory_win.yml your_play.yml
```

## 補足・エルゴノミクス

* **特別な環境変数は不要です。** UTF-8 モードは自動有効化（必要時に CLI が `PYTHONUTF8=1` 付きで
  自身を再実行）、設定のパス既定値はプラットフォーム対応化、`connection=local` は Windows で
  PowerShell シェルを既定にします。
* **Windows の OpenSSH は接続多重化に非対応**のため、SSH 接続では Windows 上で
  `ControlMaster`/`ControlPersist`/`ControlPath` を自動的に除去します。

## 既知の制限

* Python モジュールは**リモートの POSIX** 対象（SSH 経由）でのみ実行できます。Windows ホスト自身
  （`connection=local`）に対して Python モジュールを動かすことは目標外です。そこでは PowerShell の
  `win_*` モジュールを使ってください。
* **パスワード必須の `become`(sudo) over SSH** は未検証です（コントローラ側の PTY 経路を Windows で
  スキップしているため）。パスワード不要の sudo は動作します。
* 永続接続（接続デーモン経由の `network_cli`/`httpapi`）は未移植です。
* `ansible-console`（対話 REPL）と `ansible-test`（POSIX 専用）は対象外です。

## upstream Ansible との関係・帰属表示

本リポジトリは ansible-core の二次的著作物です。元の README は
[README.upstream.md](README.upstream.md) に保存しています。upstream の著作権表示・ライセンスヘッダは
すべて保持しています。本フォークによる変更点は [PORTING_JP.md](PORTING_JP.md) と
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md) に GPL の要求に従って記載しています。

* upstream プロジェクト: <https://github.com/ansible/ansible>
* upstream ドキュメント: <https://docs.ansible.com/>

## ライセンス

GNU General Public License v3.0 or later。全文は [COPYING] を参照してください。

[copying]: COPYING
