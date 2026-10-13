# ccmux-jump

[English](README.md)

AI エージェントに作業を任せて並列で開発することが増え、どのディレクトリで何をしてもらっていたか、
分からなくなることがありました。各エージェントの状況を一箇所で確認し、必要なときにそのタブへ
戻れるようにしたくて、このツールを作りました。

自分の Windows＋WSL＋WezTerm＋tmux 環境に合わせた、かなり用途の限られるツールですが、
同じような環境で作業している誰かの役に立てばうれしいです。

tmux のポップアップから AI エージェントを探し、**接続済みの WezTerm タブへ移動**する
ツールです。移動元タブの tmux セッションは維持します。

対象環境は **Windows 版 WezTerm＋WSL** です。
[ccmux](https://github.com/epilande/ccmux) の情報を Python で取得し、
[fzf](https://github.com/junegunn/fzf) で一覧・検索・プレビューを表示します。
ccmux 本体の変更や WezTerm の Lua 設定追加は不要です。ccmux とは独立したプロジェクトです。

## できること

- 状態、エージェント名、プロジェクト、ブランチ、作業概要、ディレクトリを一覧表示
- 応答待ちを優先表示し、選択中の tmux ペインの画面をプレビュー
- ポップアップを開いている間、3秒ごとに一覧とプレビューを更新
- 選択したセッションに接続済みの WezTerm タブがあれば、そのタブへ移動
- 接続済みタブがなければ、移動元と同じウィンドウに新しいタブを作って接続

表示は独自の fzf 画面です。エージェントの検出や状態の判定には ccmux を利用します。

## 必要なもの

| 技術 | 条件 |
| --- | --- |
| 環境 | Windows 版 WezTerm から起動したローカル WSL、WSL Interop 有効 |
| Python | WSL 内の 3.10 以上。標準ライブラリのみ、pip パッケージ不要 |
| tmux | ポップアップと `run-shell -C` 対応版。3.7c で検証 |
| fzf | 0.73.0 以上。0.74.4 で検証 |
| ccmux | `ccmux show --json` が動作すること。1.4.3 で検証 |
| WezTerm | Windows CLI の `list`、`activate-pane`、`spawn` が使えること |

依存ツールはそれぞれの公式手順で導入してください。ccmux を Bun で実行する構成では
Bun も必要です。ポップアップの PATH から `python3`、`tmux`、`fzf`、`ccmux` が見える必要があります。

## 導入

WSL 内で実行します。

```sh
git clone https://github.com/datetaku/ccmux-jump.git
cd ccmux-jump
install -Dm755 ccmux_jump.py "$HOME/.local/bin/ccmux-jump"
```

Windows の `wezterm.exe` は PATH、`/mnt/c/Program Files/WezTerm/wezterm.exe`、
`/mnt/c/WezTerm/wezterm.exe` の順で探します。
別の場所なら、`~/.tmux.conf` のキー設定より前に **WSL 側の実行ファイルパス**を指定します。

```tmux
set-environment -g CCMUX_JUMP_WEZTERM '/mnt/c/Tools/WezTerm/wezterm.exe'
```

続いて `~/.tmux.conf` に追加します。`e` を使用済みなら別のキーを選んでください。

```tmux
bind-key e run-shell -C 'display-popup -EE -w 90% -h 80% "~/.local/bin/ccmux-jump --client-tty #{client_tty}"'
```

設定を反映します。WezTerm 側の再読み込みは不要です。

```sh
tmux source-file ~/.tmux.conf
```

更新時はリポジトリを pull して `install` を再実行します。
削除する場合は追加したキー設定と `~/.local/bin/ccmux-jump` を取り除き、tmux を再読み込みします。

## 操作

**tmux のプレフィックス → e** で開きます。プレフィックスが `Ctrl+Q` なら、
`Ctrl+Q` を押して離してから `e` を押します。この設定はプレフィックス自体を変更しません。

| 操作 | 動作 |
| --- | --- |
| 文字入力 | 一覧内の項目を検索 |
| 上下キー、Ctrl+K / Ctrl+J | エージェントを選択 |
| Enter | 対応するタブへ移動 |
| Ctrl+R | 即時更新 |
| Esc | 閉じる |

一覧の表示ラベルは英語です。`Question` は質問待ち、`Approval` は承認待ちを表します。
移動時にエラーがあればポップアップに表示を残します。Esc で閉じられます。

対象セッションに複数のタブが接続している場合、起動元が同じセッションなら起動元を優先し、
それ以外は直近に操作された tmux クライアントを選びます。

## 仕組みと制限

tmux クライアントの `/proc/<pid>/environ` から `WSL_INTEROP` を取得します。
その接続経由で Windows 側の `WEZTERM_PANE` を読み取り、WezTerm CLI の一覧と照合します。
対象の tmux window/pane を選択し、WezTerm CLI でタブを移動します。
移動元の接続先を変更する `switch-client` や `detach-client` は使いません。

- Windows WezTerm から直接接続したローカル WSL の tmux を対象とします。
  Linux/macOS のネイティブ端末、SSH、入れ子の tmux、異なる WSL ディストリビューション間の移動は対象外です。
- ccmux と同じ tmux サーバーで使ってください。ペインIDはサーバーごとに異なります。
- 同じ tmux セッションを複数のタブで開いている場合、window/pane の選択は通常どおり共有されます。
- 実機検証は1つの WezTerm ウィンドウ内のタブ移動で実施しています。別ウィンドウを前面に出す動作は未検証です。
- `unknown event: every` が出る場合は fzf を 0.73.0 以上へ更新してください。
- 一覧が空なら、まず `ccmux show --json` を確認してください。tmux ペインIDのある項目だけを表示します。
- タブ特定に失敗する場合は、WSL Interop が有効であることを確認し、WezTerm のタブから tmux に再接続してください。
- `cmd.exe` は PATH から探し、見つからなければ `/mnt/c/Windows/System32/cmd.exe` を使います。

エージェントの起動や worktree の作成は行いません。gtr など既存の運用をそのまま使えます。
デスクトップ通知や常駐の監視サービスも追加しません。

## 開発

```sh
python3 -m unittest discover -s tests -v
python3 ccmux_jump.py --help
```

自動テストは外部コマンドをモック化し、Windows GUI なしの Linux で実行できます。
GitHub Actions は Python 3.10 / 3.14 を対象としています。
実機での確認方法は [docs/testing.md](docs/testing.md) を参照してください。

## ライセンス

[MIT](LICENSE)。ccmux、fzf、tmux、WezTerm はそれぞれ独立したライセンスで提供され、
このリポジトリには同梱しません。
