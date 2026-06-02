# ansible-core コントローラの Windows ネイティブ移植

**English: [PORTING.md](PORTING.md)**

本書は、ansible-core の**コントローラ**を Windows でネイティブ動作させるために*何を*変更したか、
*なぜ*か、そして*将来の Ansible バージョンに同じ作業を再適用する方法*を説明します。本フォークを
保守するための主要リファレンスです。

ベースバージョン: ansible-core `2.22.0.dev0`（devel）。ファイル別の一覧は
[CHANGES_WINDOWS.md](CHANGES_WINDOWS.md) を参照してください。

---

## 1. 前提モデル: コントローラ側 vs モジュール側

Ansible のコードは2つの実行コンテキストに分かれます:

* **コントローラ側** — `ansible-playbook` を実行する場所で動くすべて（CLI、executor、inventory、
  テンプレート、接続プラグイン、AnsiballZ の組み立て）。**これを Windows で動かします。**
* **モジュール側** — `lib/ansible/modules/*` と `lib/ansible/module_utils/*` の大半。これらは管理
  対象ノード（通常 Linux）に送られて実行されます。対象がリモート Linux である限り問題になりません
  （リモートで動くため）。ただし一部の `module_utils` はコントローラでも import されるため（例:
  `DataLoader` 経由の `module_utils/basic.py`）、少なくとも Windows で *import できる*必要があります。

すべての変更の指針: **upstream（POSIX）の挙動をバイト単位で不変に保つ**こと。Windows 固有の挙動は
`os.name == 'nt'` 分岐や `try/except ImportError` ガードに閉じ込め、フォークを小さく・リベース可能に
保ちます。

## 2. ビルドと検証

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install pywinrm pypsrp   # winrm/psrp 用
```

スモークテスト（環境変数不要）:

```powershell
.\.venv\Scripts\ansible-playbook.exe --version
.\.venv\Scripts\ansible-playbook.exe --syntax-check -i "localhost," play.yml
```

コントローラは **CPython 3.12+** が必須（`lib/ansible/cli/__init__.py:_PY_MIN`）で、コードの一部は
PEP 695 構文を使うため、3.10/3.11 ではパッケージの import すらできません。

---

## 3. カテゴリ別の変更点

### A. インポート可能化 — POSIX 専用 stdlib import のガード

`Display` はほぼ全所から import され、それ（および import 連鎖上の数モジュール）が
`fcntl`/`termios`/`tty`/`pwd`/`pty` を無条件 import していたため、何かが動く前に Windows では import
失敗していました。

使用パターン:

```python
try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]
# 呼び出し側:  if fcntl is not None: ...
```

対象ファイル:

* `utils/display.py` — `termios`/`tty` をガード（不要になった `fcntl`/`struct` は削除）。
  `setraw()` の既定引数 `when=termios.TCSAFLUSH` は import 時に評価される → `when=None` にして内部で
  解決。`_set_column_width()` は `fcntl.ioctl(TIOCGWINSZ)` をクロスプラットフォームな
  `os.get_terminal_size()` に置換。libc の `wcwidth`/`wcswidth`
  （`ctypes.cdll.LoadLibrary(find_library('c'))`）は Windows で失敗 → `try/except` で囲み、
  `unicodedata` ベースの純 Python フォールバック `_char_width()` を用意。
* `_internal/_templating/_template_vars.py` — `pwd` をガード。`pwd.getpwuid()` は数値 uid に
  フォールバック。`os.uname()[1]` → `platform.node()`。
* `plugins/connection/__init__.py` — `fcntl` をガード。`connection_lock()/unlock()` は利用不可時に
  no-op（TODO: 本格的なクロスプラットフォームロック）。
* `plugins/connection/local.py` — `pty` をガード、`os.getuid()` をガード。
* `parsing/vault/__init__.py` — `fcntl` を削除。「fd かどうか」の判定は `os.fstat()`。
* `module_utils/basic.py` — `grp`/`pwd`/`fcntl` をガード（`DataLoader` 経由でコントローラでも import）。
* `cli/__init__.py` — `check_blocking_io()` は `os.get_blocking()` の `OSError` を捕捉（Windows の
  コンソール/パイプハンドルでは非対応）。

### B. ロケール / UTF-8 モード

Ansible は stdio/ファイルシステム/ロケールに UTF-8 を要求します。日本語 Windows の ANSI コード
ページは cp932 で、`open()` がそれを使ってしまいます。UTF-8 モード（PEP 540）はインタープリタ起動時
にしか有効化できないため:

* `cli/__init__.py` — 冒頭で、`os.name == 'nt'` かつ `not sys.flags.utf8_mode` のとき、CLI は
  `PYTHONUTF8=1` 付きで `subprocess.run([sys.executable, *sys.orig_argv[1:]], …)` により自身を一度
  再実行し、その戻り値で終了します。**`sys.orig_argv[0]` ではなく `sys.executable` を使うこと** —
  コンソールスクリプトランチャ下では前者は venv 外のベース python で `ansible` を import できません。
  ガード環境変数で無限再実行を防ぎます。
* `cli/__init__.py:initialize_locale()` — Windows では `sys.flags.utf8_mode` が立っていればロケールを
  受理（レガシーコードページを見ない）。無効なら「PYTHONUTF8=1 を設定」と明示エラー。

### C. プロセスモデル — fork → spawn ＋ ワーカーブートストラップ

`utils/multiprocessing.py` は `multiprocessing.get_context('fork')` をハードコードしていました。
Windows は `spawn` のみ。`WorkerProcess`（`executor/process/worker.py`）は fork 前提（メモリ/FD 継承、
`os.setsid`/`os.setpgid`/`os.killpg`、POSIX シグナル）で書かれていました。

* `utils/multiprocessing.py` — `fork` が無ければプラットフォーム既定コンテキストにフォールバック。
* `executor/process/worker.py`:
  * `os.setsid`/`os.setpgid`（`_detach`）、`os.killpg`（`_term`）、`os.O_NONBLOCK`
    （`getattr(os, 'O_NONBLOCK', 0)`）をガード。
  * `_bootstrap_worker_environment()` を追加（`run()` の最初に呼ぶ）: **spawn** では子がコントローラの
    初期化済みグローバルを継承しないため、`context.CLIARGS` を復元し、`init_plugin_loader()` を呼んで
    （コレクションファインダを設置し `ansible.builtin.*` を解決可能にする）、`display.verbosity` を
    CLIARGS から設定（ワーカーで `-vvv` を有効化）。冪等で、fork 下では no-op。

> **なぜスレッドでなく spawn か?** スレッドベースのワーカーは pickle を回避できますが、`Display` は
> シングルトンでそのキュー・プロキシがプロセス単位の設計（`parent_process() is not None` を表明）の
> ため、プロセスモデルは spawn に素直に対応します。spawn ではワーカー引数の pickle 化が既に成功して
> おり、不足はコントローラのグローバル再初期化だけでした。

spawn の副作用: ワーカーが `shared_loader_obj` を unpickle する際、`PluginLoader.__setstate__` が
`aliases={}` で `__init__` を呼び、全プラグインタイプで「Instantiating … PluginLoader with aliases is
deprecated」警告が発火。`plugins/loader.py` で `aliases` が真のときだけ警告するよう修正。

### D. クロスプラットフォームなパス処理

繰り返し現れたバグ種別: **リモート/POSIX** や **zip** のパスを `os.path`（Windows で `\`）で組み立てる、
または絶対判定を `startswith('/')` で行うコード。

* `_internal/_datatag/_tags.py` — `Origin._post_validate` の `path.startswith('/')` → `os.path.isabs`。
* `utils/collection_loader/_collection_finder.py` — `get_data` の `path[0] == '/'` → `os.path.isabs`。
* `parsing/dataloader.py` — `RE_TASKS` を `os.path.sep` から構築（エスケープ無しの `\` で正規表現が
  壊れる）→ セパレータ非依存の `r'(?:^|[\\/])+tasks[\\/]?$'`。
* `plugins/shell/__init__.py` — `ShellBase.join_path` の `os.path.join` → **`posixpath.join`**。シェル
  プラグインは（POSIX）リモート対象用のパスを組むため、常に `/` で結合すべき。（`powershell` シェルは
  既に `ntpath` で override 済み。）このバグでリモート tmp が `~/.ansible/tmp\ansible-tmp-…` になって
  いました。

### E. 設定のパス既定値（`config/base.yml`）

各パスリスト既定値（`collections`、`roles`、各プラグインタイプのパス）が `:` 区切り・
`/usr/share/...` の POSIX 文字列でした（例:
`{{ ANSIBLE_HOME ~ "/collections:/usr/share/ansible/collections" }}`）。Windows では設定マネージャが
パスリストを `os.pathsep`（`;`）で分割するため、`:` がドライブレター（`C:\…`）と衝突して
`COLLECTIONS_PATHS` が壊れ、`ansible-galaxy` が失敗しました。

* `constants.py` — `_pathlist(home, *system)` ヘルパーを追加（既定値テンプレートのコンテキストに
  `vars()` 経由で見える）。`os.pathsep` で結合し、**Windows では POSIX の `/usr/share`+`/etc`
  システムパスを除外**。POSIX 出力はバイト単位で同一。
* `config/base.yml` — 約20個のテンプレート既定値を
  `{{ _pathlist(ANSIBLE_HOME ~ "/x", "/usr/share/ansible/x") }}` に書き換え。

### F. 接続: `local` ＋ PowerShell（Windows）

Windows コントローラではローカルホストに対するモジュールは PowerShell モジュールで、生成される
コマンドラインは自己完結した `powershell.exe … -EncodedCommand <base64>` であり、
`/bin/sh -c '…'` ではありません。

* `plugins/connection/local.py`:
  * `os.name == 'nt'` で `Connection._shell_type = 'powershell'`（`ansible_shell_type` 不要。明示指定が
    あればそちら優先）。
  * `exec_command` でシェルが `_IS_WINDOWS` のとき: `/bin/sh` を実行ファイルにしない
    （`executable=None`）。コマンドを `shlex.split()` してインタープリタを直接起動（cmd.exe が
    `-EncodedCommand` 周りの POSIX クォートを壊さないように）。さらに**子プロセス env から
    `PSModulePath` を除去**（大文字小文字無視 — Windows の `os.environ` はキーを `PSMODULEPATH` に
    大文字化）。これが無いと Windows PowerShell 5.1 が（pwsh セッションから起動された場合）
    PowerShell 7 由来の `PSModulePath` を継承して非互換の PS7 モジュールをロードし、
    `Get-FileHash 認識不可` や `ObjectSecurity … member already present` の ETS エラーになります。
* `plugins/action/__init__.py` — `_low_level_execute_command` は `_connection._shell._IS_WINDOWS` の
  とき `<shell> -c '…'` ラップをスキップ。

### G. 接続: `ssh`（リモート Linux 管理）

`plugins/connection/ssh.py` は `fcntl`（パイプを非ブロッキング化）＋ `selectors` で `ssh.exe`
サブプロセスを読んでいました。Windows はパイプを `select` できず、`fcntl`/`pty` もありません。

* `import fcntl`/`import pty` をガード、`import threading` を追加。
* `_ThreadedPipeReader`・`_ThreadedSelector`（モジュールレベル）を追加: `fcntl` の無い環境では各パイプ
  を背景スレッドでバッファに読み出し、最小限の selector 互換オブジェクトが ready を報告。`_bare_run`
  の読み取りループは `fcntl is not None` で分岐し、ループ本体は不変（`stdout_obj`/`stderr_obj` ＋
  `key.fileobj.read()`）なので POSIX 経路は同一。
* `pty.openpty()` を `if pty is not None` でガード（パイプにフォールバック）。
* **`_build_command` は `os.name == 'nt'` で `ControlMaster`/`ControlPersist`/`ControlPath` の `-o`
  オプションを除去**し `_persistent=False` に — Windows OpenSSH は接続多重化に非対応で、放置すると
  接続失敗します。
* Windows 標準 OpenSSH（`ssh.exe`/`sftp.exe`/`scp.exe`）を使用。

### H. AnsiballZ のパッケージング（核心）

コントローラが Python モジュール zip を組み立てる際、arcname は POSIX、パッケージ判定はセパレータ
非依存である必要があります。`executor/module_common.py`:

* `LegacyModuleUtilLocator._find_module` — `is_package = info.origin.endswith('/__init__.py')` が
  Windows では `info.origin` が `\__init__.py` で終わるため失敗。結果、パッケージが
  `_internal/__init__.py` でなく `_internal.py` として zip 化され、リモートで
  `ModuleNotFoundError: ... _internal is not a package` に。`os.path.basename(info.origin) ==
  '__init__.py'` に修正。**これがリモート実行の核心バグ。**
* `LegacyModuleUtilLocator.output_path`（zip arcname）の `os.path.join` → `'/'.join`。
* embed の arcname の `str(rel_path)` → `rel_path.as_posix()`。
* `_get_ansible_module_fqn` で `\`→`/` 正規化（および `CORE_LIBRARY_PATH_RE` の `site_packages`）。
  これが無いと Windows パスが正規表現にマッチせず `ansible.legacy.<mod>` にフォールバックし、相対
  `..module_utils.X` 解決が破綻（`win_command` の C# `Process` util で最初に顕在化）。

### I. 接続: `winrm`（リモート Windows 管理）

`plugins/connection/winrm.py` は Windows でクリーンに import 可能（POSIX 依存なし）。`pip install
pywinrm` が必要。コード変更不要。Windows Server 2025 に対し HTTPS/NTLM で E2E 検証済み。

### J. 接続: `psrp`（リモート Windows 管理）

`plugins/connection/psrp.py` はクリーンに import 可能（`pip install pypsrp` が必要）ですが、認証時に
`Argument 'username' has incorrect type (expected str, got _AnsibleTaggedStr) … Cython is stricter`
で失敗。Ansible の設定/inventory 値は**タグ付き文字列**（str サブクラス）で、Windows の `pyspnego`
SSPI バックエンドは Cython でサブクラスを拒否（pywinrm は純 Python なので許容）。

* `psrp.py:_build_kwargs` — `_psrp_conn_kwargs`/`_psrp_runspace_kwargs` の値を
  `AnsibleTagHelper.as_native_type(...)`（`ansible.module_utils._internal._datatag` から）で
  ネイティブ型に変換。

Windows Server 2025 に対し HTTPS/NTLM で E2E 検証済み。（注: *localhost* に *ローカル*アカウントで
ループバック接続する psrp は NTLM が失敗することがありますが、これは Windows SSPI のループバックの
癖で ansible のバグではありません。実リモートホストでは動作します。）

### K. 対話プロンプト（`msvcrt`）

`Display.prompt`（`vars_prompt`/`--ask-vault-pass`/`--ask-*-pass` が使用）は `getpass`/`input` を
使い、Windows で元々動作します。`Display.prompt_until`（`pause` モジュール等が使用）は `termios` の
raw モード＋非ブロッキング fd 読み取りを使っていました。

* `utils/display.py` — `prompt_until` は Windows で例外を投げず、not-a-tty 判定の後、新メソッド
  `_read_console_stdin_windows()` に分岐。`msvcrt`（`kbhit`/`getwch`）で、同等のタイムアウト/割り込み
  (Ctrl+C)/補完(Enter)/バックスペース/エコー制御を実装。

### L. ロック

* `_internal/_locking.py` — `named_mutex` は POSIX で `fcntl.flock`、Windows で `msvcrt.locking`
  （同じブロッキングのコンテキストマネージャ API）。

### M. 壊れたシンボリックリンク（Windows チェックアウトの副産物）

シンボリックリンク非対応で Windows に展開すると、リンクはリンク先パスを書いたテキストファイルに
なります。

* `module_utils/ansible_release.py` はテキスト `../release.py` だった → 実体（`lib/ansible/release.py`
  と同内容）に置換。実行に影響する `lib/` 内の壊れたシンボリックリンクはこれのみ。`bin/` と `test/`
  には他にもあります（§5 / 公開タスク参照）。

---

## 4. 将来バージョン移植のチェックリスト

新しい upstream チェックアウトに対し、概ね次の順で上記パターンを適用します:

1. **import を通す。** `ansible-playbook --version` を実行し、各 `ImportError`/`AttributeError` を
   修正。コントローラの import 連鎖で新規の POSIX import
   （`fcntl|pwd|grp|pty|termios|tty|resource`）を grep してガード。`cli/__init__.py`（ロケール＋
   blocking-io）と UTF-8 再実行を再確認。
2. **プロセスモデル。** `utils/multiprocessing.py` の fork フォールバックと `worker.py` の
   `_bootstrap_worker_environment()` ＋ POSIX ガードがリファクタ後も残っているか確認。
3. **パス既定値。** `config/base.yml` のパスリストと `constants._pathlist` ヘルパーを再確認。
4. **ローカル PowerShell play**（`win_ping`/`win_command`）と**リモート Linux SSH play**
   （`ping`/`command`/`copy`）を実行し、リモート/zip パスでの新たな
   `os.path.join`/`startswith('/')`/`endswith('/__init__.py')` を修正
   （grep: `module_common.py`/`shell/`/`action/` の `endswith('/`, `[0] == '/'`, `os.path.join`）。
5. **接続。** `ssh.py` のスレッドリーダ＋ControlMaster 除去、`local.py` の PowerShell 処理、`psrp.py`
   のタグ付き文字列変換を再適用。`winrm.py` は通常変更不要。
6. **シンボリックリンク。** `module_utils/ansible_release.py` を実体化（配布用に `bin/` も対応）。

Windows でのみ失敗するときに有用な grep:

```text
endswith('/__init__.py')      # パッケージ判定
startswith('/') | [0] == '/'  # 絶対パス判定
os.path.join | os.path.sep    # リモート/zip パス構築
import fcntl|pwd|grp|pty|termios|tty|resource   # 新規 POSIX import
os.fork|setsid|killpg|getuid|getpgrp            # POSIX プロセス/ID 呼び出し
```

## 5. 既知の制限 / 未対応

* Python モジュールはリモート POSIX 対象でのみ実行（Windows 自身への `connection=local` は対象外）。
* パスワード必須の `become` over SSH（コントローラ側 PTY 経路をスキップ）。パスワード不要 sudo は動作。
* 永続接続デーモン（`network_cli`/`httpapi`）、`ansible-console`、`ansible-test`。
* `connection_lock()` は Windows で no-op。`bin/` のシンボリックリンクは配布用に未実体化。
