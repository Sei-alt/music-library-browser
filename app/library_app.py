"""Folder-based desktop entry point. SPDX-License-Identifier: GPL-2.0-or-later"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

sys.dont_write_bytecode = True

APP_ROOT = Path(__file__).resolve().parent
VERSION = '0.2.1'


def state(phase, message, current=0, total=0):
    print('STATE: ' + json.dumps(dict(phase=phase, message=message, current=current, total=total), ensure_ascii=True), flush=True)


def profile_directory(source, data_home):
    key = hashlib.sha256(os.path.normcase(str(Path(source).resolve())).encode('utf-8')).hexdigest()[:24]
    return Path(data_home).resolve() / 'libraries' / key


def find_running(profile, port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for number in range(port, port + 20):
        host = f'http://127.0.0.1:{number}'
        try:
            with opener.open(host + '/instance', timeout=.15) as response:
                instance = json.load(response)
            if instance.get('version') == 6 and instance.get('root') == str(profile):
                return host
        except (OSError, ValueError):
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description='音源フォルダーを指定して音楽一覧を開きます。')
    parser.add_argument('--source', required=True)
    parser.add_argument('--data-home', default=str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MusicLibraryBrowser'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--scan-only', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65515:
        parser.error('port must be between 1024 and 65515')
    source = Path(args.source).resolve()
    if not source.is_dir():
        raise ValueError('音源フォルダーを選択してください。')
    data_home = Path(args.data_home).resolve()
    profile = profile_directory(source, data_home)
    if source.is_relative_to(data_home):
        raise ValueError('アプリの保存先以外の音源フォルダーを選択してください。')
    if not args.scan_only:
        running = find_running(profile, args.port)
        if running:
            if args.refresh:
                raise ValueError('このフォルダーの一覧は起動中です。先に停止してから再読み込みしてください。')
            state('existing', '起動済みのライブラリを開きます。')
            print('URL: ' + running, flush=True)
            if not args.no_browser:
                import webbrowser
                webbrowser.open(running)
            return
    os.environ['MUSIC_LIBRARY_DATA_DIR'] = str(profile)
    os.environ['MUSIC_LIBRARY_TOOLS_DIR'] = str(APP_ROOT.parent / 'tools')
    profile.mkdir(parents=True, exist_ok=True)
    needs_scan = args.refresh or not (profile / 'music.sqlite').is_file() or not (profile / '音楽一覧.html').is_file()
    report = None
    if needs_scan:
        state('scan', '音源フォルダーを調べています…')
        import build_music_db
        def progress(current, total):
            if current == 0 or current == total or current % 10 == 0:
                state('scan', f'楽曲を読み込み中: {current:,} / {total:,}', current, total)
        report = build_music_db.build(source, profile, progress=progress, excluded=(data_home, APP_ROOT, APP_ROOT.parent/'runtime', APP_ROOT.parent/'tools'))
    else:
        # Always use this release's interface while retaining the selected library.
        import re
        template = (APP_ROOT / 'viewer.template.html').read_text(encoding='utf-8')
        html = (profile / '音楽一覧.html').read_text(encoding='utf-8-sig')
        payload = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)
        token = (profile / 'local-token.txt').read_text(encoding='ascii')
        (profile / '音楽一覧.html').write_text(template.replace('__DATA__', payload).replace('__TOKEN__', token), encoding='utf-8-sig')
    data_home.mkdir(parents=True, exist_ok=True)
    (data_home / 'last-folder.txt').write_text(str(source), encoding='utf-8')
    state('ready', '一覧の準備ができました。')
    if args.report:
        Path(args.report).write_text(json.dumps(dict(source=str(source), profile=str(profile), version=VERSION, report=report), ensure_ascii=False, indent=2), encoding='utf-8')
    if args.scan_only:
        return
    import local_browser
    local_browser.serve(args.port, open_browser=not args.no_browser)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        state('error', str(error))
        raise SystemExit(1)
