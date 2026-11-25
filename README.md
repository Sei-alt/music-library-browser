# 音楽ライブラリ

音源フォルダーを選んで、アプリ専用ウィンドウで検索・並べ替え・再生・ジャケット設定を行うWindowsアプリです。バージョン0.2.0から、標準ブラウザーを開かずに使えます。

## 使い始める

### インストーラー版（0.2.1以降）

`MusicLibrary-Setup-0.2.1-x64.exe` を実行し、画面に従ってインストールします。
管理者権限は不要です。スタートメニューに「音楽ライブラリ」を登録し、デスクトップショートカットも選択できます。
標準のインストール先は `%LOCALAPPDATA%\Programs\MusicLibrary` です。
アプリ本体・ウィンドウ・ショートカット・インストーラーには専用アイコンを設定しています。
削除はWindowsの「インストールされているアプリ」から行えます。ライブラリ保存データ・音源・ジャケット変更前のバックアップは保持します。
更新版は同じ場所へ上書きインストールできます。起動中のアプリは終了してから更新してください。

### ZIP版

1. Windows用ZIPをすべて展開し、`MusicLibrary.exe`を起動します。
2. 「選択…」で音源フォルダーを指定し、「ライブラリを開く」を押します。
3. 初回は進捗を表示しながら一覧を作成し、アプリ専用ウィンドウで開きます。

Windows 10/11（64ビット）を対象としています。Pythonは同梱され、別途インストールは不要です。画面表示には Microsoft Edge WebView2 Runtime と .NET Framework 4.8 を使用します。WebView2が未導入の場合はMicrosoft公式サイト（https://developer.microsoft.com/microsoft-edge/webview2/ ）からEvergreen Runtimeをインストールしてください。
FFmpeg / ffprobeをPATHに導入するか、`tools`に`ffmpeg.exe`と`ffprobe.exe`を置いてください。FFmpegの入手先: https://ffmpeg.org/download.html 。この配布物にはFFmpegを同梱しません。
実行ファイルだけを取り出さず、`app`・`runtime`・同梱DLLなどと一緒に保持してください。

## 一覧と再生

- 曲名・アルバム名・アーティスト名・長さで並べ替え、検索、ページ件数変更。
- 「再生する」でアプリ内再生。「場所を開く」でエクスプローラーに音源を表示。
- ジャケットをクリックすると拡大画面に切り替わります。「CD」「ジャケット」で表示方法を選べます。
- 音量は0.1%刻み、再生速度は0.05倍刻みのバーと数値入力に対応。速度はホイールでも調整できます。
- WebView2の対応形式によっては再生できない音源もあります。

## ジャケットを設定する

一覧の各曲にある「ジャケットを設定」、または拡大画面の同名ボタンを押してください。
JPEG / PNG（10MB以下）を選び、画像を確認して「音源に保存」を押すと、選んだ1曲に埋め込みます。
MP3・M4A・WAV・FLACに対応し、画像は長辺1600px以内に調整します。
音声の再圧縮は行わず、保存前後の音声データの一致を確認します。
WAVのID3ジャケットを表示できるかは、再生アプリによって異なります。

保存前の音源全体は、ライブラリ保存先の`artwork-backups/<番号>/original.<拡張子>`に保管されます。
同じ場所の`info.json`に元のファイル名・場所を記録します。戻す場合は再生を止め、バックアップを元の名前・場所にコピーし、一覧を再読み込みしてください。

## 更新・フォルダーの切り替え

追加・削除・タグ変更後は、画面上部の「フォルダー変更・一覧の更新」を押し、「一覧を再読み込みして開く」を選んで開き直します。
別の音源フォルダーを選ぶと、それぞれ独立した一覧を使います。
保存先は`%LOCALAPPDATA%\MusicLibraryBrowser\libraries`です。音源の移動・削除は行いません。
ジャケットの保存操作を行ったときだけ、選択した音源のタグを書き換えます。
アプリ画面を閉じると、そのアプリが起動した一覧と再生も終了します。フォルダー選択画面は一覧の表示中に自動で隠れます。旧バージョンと同じ保存先を使うので、同じフォルダーを指定すると既存の一覧・ジャケット設定を引き継ぎます。ブラウザー用の拡張機能や外部サイトへの接続は不要です。

## ソースから実行・ビルド

Python 3.12以降とFFmpeg / ffprobeを用意します。Mutagenのソースは`app/vendor`に同梱しています。

```powershell
python app/library_app.py --source "D:\Music"
python app/library_app.py --source "D:\Music" --refresh
python -m unittest discover -s tests -v
python scripts/build_windows.py --runtime "D:\PythonRuntime" --output "D:\BuildOutput"
python scripts/build_installer.py --iscc "D:\Inno Setup 6\ISCC.exe" --release "D:\BuildOutput\MusicLibrary-Windows" --output "D:\BuildOutput"
```

ビルドにはWindows付属の.NET Framework C#コンパイラー、Microsoft WebView2 SDK、および`python.exe`・`DLLs`・`Lib`・`LICENSE.txt`を含むWindows用Pythonランタイムが必要です。
ビルドスクリプトは固定版WebView2 SDK 1.0.3912.50をMicrosoftのNuGetから取得し、SHA256を検証します。ダウンロード済みのパッケージを使う場合は `--webview2-package "D:\Microsoft.Web.WebView2.1.0.3912.50.nupkg"` を指定します。WebView2 Runtime本体は同梱しません。

ビルド後のWindows用ZIPとソースZIPはGitHub Releasesなどへの追加用に生成されます。

インストーラーは Inno Setup 6.7以降で作成します。スクリプトは `installer/MusicLibrary.iss`、アイコン原稿は `assets/music-library.svg` です。
PNGと複数サイズのICOも同梱しています。アイコンを再生成する場合のみNode.jsと `sharp` を用意し、`node scripts/render_icon.cjs` を実行します。

このプロジェクトはGPL-2.0-or-laterです。第三者コンポーネントは`THIRD_PARTY_NOTICES.md`を参照してください。
GitHubに追加する手順と確認事項は`docs/GITHUB_PREPARATION.md`にまとめています。
