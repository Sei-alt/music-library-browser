import http.server, json, pathlib, sqlite3, subprocess, threading, webbrowser, urllib.request, functools, shutil, argparse, re, base64, binascii, os, socket
from urllib.parse import urlsplit, unquote, parse_qs
from explorer_select import select_file
from contextlib import contextmanager
import artwork_editor
ROOT = pathlib.Path(os.environ.get('MUSIC_LIBRARY_DATA_DIR', pathlib.Path(__file__).resolve().parent)).resolve()
HOST = 'http://127.0.0.1:8765'
TOKEN = (ROOT / 'local-token.txt').read_text(encoding='ascii')

class LibraryHTTPServer(http.server.ThreadingHTTPServer):
    # SO_REUSEADDR on Windows lets unrelated processes bind the same port,
    # which can route the app to an older viewer or another music folder.
    allow_reuse_address = os.name != 'nt'
    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

@contextmanager
def database():
    connection = sqlite3.connect(ROOT / 'music.sqlite')
    try:
        with connection: yield connection
    finally:
        connection.close()

@functools.lru_cache(maxsize=12)
def full_artwork(path, modified, size):
    # Decode the embedded cover on demand; keep the original music file untouched.
    try: picture_bytes = artwork_editor.read_picture(path)
    except Exception: picture_bytes = None
    if picture_bytes:
        return artwork_editor.image_bytes(ROOT, picture_bytes, 1400, 'mjpeg')
    def tool(name):
        return artwork_editor.tool(ROOT, name)
    probe = subprocess.run([tool('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', path], capture_output=True, timeout=20, check=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    picture = next((s for s in json.loads(probe.stdout).get('streams', []) if s.get('disposition', {}).get('attached_pic')), None)
    if not picture: raise ValueError('No embedded artwork')
    result = subprocess.run([tool('ffmpeg'), '-v', 'error', '-nostdin', '-i', path, '-map', '0:' + str(picture['index']), '-frames:v', '1', '-vf', "scale='min(1400,iw)':'min(1400,ih)':force_original_aspect_ratio=decrease", '-q:v', '2', '-f', 'image2pipe', '-c:v', 'mjpeg', 'pipe:1'], capture_output=True, timeout=25, check=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if not result.stdout.startswith(b'\xff\xd8') or len(result.stdout) > 12 * 1024 * 1024: raise ValueError('Invalid artwork')
    return result.stdout

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, status, data, mime='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin', HOST))
        self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def trusted(self):
        return self.headers.get('Host') == urlsplit(HOST).netloc and self.headers.get('Origin', HOST) in (HOST, 'null')
    def do_GET(self):
        if not self.trusted(): return self.reply(403, b'{}')
        p = unquote(urlsplit(self.path).path)
        if p.startswith('/audio/'):
            return self.audio(p)
        if p.startswith('/artwork/'):
            return self.artwork(p)
        if p == '/instance':
            return self.reply(200, json.dumps({'root': str(ROOT), 'version': 6}).encode())
        if p in ('/', '/音楽一覧.html'):
            html = (ROOT / '音楽一覧.html').read_text(encoding='utf-8-sig')
            match = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', html, re.S)
            if match:
                with database() as db:
                    covers = dict(db.execute('SELECT path, cover FROM tracks'))
                rows = json.loads(match.group(2))
                for row in rows:
                    if row['path'] in covers: row['cover'] = covers[row['path']]
                payload = json.dumps(rows, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
                html = html[:match.start(2)] + payload + html[match.end(2):]
            return self.reply(200, html.encode('utf-8'), 'text/html; charset=utf-8')
        if p.startswith('/covers/') or p.startswith('/artwork-overrides/'):
            target = (ROOT / p.lstrip('/')).resolve()
            directory = 'covers' if p.startswith('/covers/') else 'artwork-overrides'
            if target.parent == (ROOT / directory).resolve() and target.suffix == '.jpg' and target.is_file():
                return self.reply(200, target.read_bytes(), 'image/jpeg')
        self.reply(404, b'{}')
    def artwork(self, endpoint):
        query = parse_qs(urlsplit(self.path).query)
        if query.get('token') != [TOKEN]: return self.reply(403, b'{}')
        try:
            track_id = int(endpoint.removeprefix('/artwork/'))
            with database() as db:
                row = db.execute('SELECT path FROM tracks WHERE id=?', (track_id,)).fetchone()
                source = pathlib.Path(db.execute('SELECT source FROM metadata').fetchone()[0]).resolve()
            if not row or query.get('path') != [row[0]]: raise ValueError()
            path = pathlib.Path(row[0]).resolve()
            if not path.is_relative_to(source) or not path.is_file(): raise ValueError()
            stat = path.stat()
            image = full_artwork(str(path), stat.st_mtime_ns, stat.st_size)
        except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError, TypeError):
            return self.reply(404, b'{}')
        try: self.reply(200, image, 'image/jpeg')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
    def audio(self, endpoint):
        query = parse_qs(urlsplit(self.path).query)
        if query.get('token') != [TOKEN]: return self.reply(403, b'{}')
        try:
            track_id = int(endpoint.removeprefix('/audio/'))
            db = sqlite3.connect(ROOT / 'music.sqlite')
            try:
                row = db.execute('SELECT path FROM tracks WHERE id=?', (track_id,)).fetchone()
                source = pathlib.Path(db.execute('SELECT source FROM metadata').fetchone()[0]).resolve()
            finally: db.close()
            if not row or query.get('path') != [row[0]]: raise ValueError()
            path = pathlib.Path(row[0]).resolve()
            if not path.is_relative_to(source) or not path.is_file(): raise ValueError()
        except (ValueError, OSError, sqlite3.Error):
            return self.reply(404, b'{}')
        size = path.stat().st_size
        start, end = 0, size - 1
        requested = self.headers.get('Range')
        if requested:
            try:
                if not requested.startswith('bytes=') or ',' in requested: raise ValueError()
                left, right = requested[6:].split('-', 1)
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    suffix = int(right)
                    if suffix <= 0: raise ValueError()
                    start = max(0, size - suffix)
                if start < 0 or start >= size or end < start: raise ValueError()
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        mime = {'.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav','.flac':'audio/flac'}.get(path.suffix.lower(),'application/octet-stream')
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type', mime)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'no-store')
        if requested: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk: break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
    def do_POST(self):
        if self.path == '/artwork':
            return self.save_artwork()
        if not self.trusted() or self.path != '/reveal': return self.reply(403, b'{}')
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n < 1024: raise ValueError()
            body = json.loads(self.rfile.read(n))
            if body.get('token') != TOKEN: return self.reply(403, b'{}')
            with database() as db:
                row = db.execute('SELECT path FROM tracks WHERE id=?', (int(body['id']),)).fetchone()
                source = pathlib.Path(db.execute('SELECT source FROM metadata').fetchone()[0]).resolve()
            if not row or row[0] != body.get('path'): raise ValueError()
            path = pathlib.Path(row[0]).resolve()
            if not path.is_relative_to(source) or not path.is_file(): raise ValueError()
            select_file(path)
            self.reply(200, b'{"ok":true}')
        except Exception:
            self.reply(400, b'{"ok":false}')

    def save_artwork(self):
        if not self.trusted(): return self.reply(403, b'{}')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 14 * 1024 * 1024: raise ValueError('画像は10MB以下にしてください。')
            body = json.loads(self.rfile.read(length))
            if body.get('token') != TOKEN: return self.reply(403, b'{}')
            with database() as db:
                row = db.execute('SELECT path FROM tracks WHERE id=?', (int(body['id']),)).fetchone()
                source = pathlib.Path(db.execute('SELECT source FROM metadata').fetchone()[0]).resolve()
            if not row or body.get('path') != row[0]: return self.reply(404, b'{}')
            path = pathlib.Path(row[0]).resolve()
            if not path.is_relative_to(source) or not path.is_file(): return self.reply(404, b'{}')
            image = base64.b64decode(body['image'], validate=True)
            with artwork_editor.EDIT_LOCK:
                result = artwork_editor.save_cover(ROOT, path, image)
                try:
                    with database() as db:
                        db.execute('UPDATE tracks SET cover=? WHERE path=?', (result['cover'], row[0]))
                except sqlite3.Error:
                    result['refresh_warning'] = '音源への保存は完了しました。一覧の更新には起動ウィンドウの「一覧を再読み込みして開く」を実行してください。'
            full_artwork.cache_clear()
            self.reply(200, json.dumps({'ok': True, **result}).encode())
        except PermissionError:
            self.reply(409, json.dumps({'error': '音源を保存できません。他のアプリで使用中の場合は閉じて再試行してください。'}).encode())
        except (ValueError, KeyError, TypeError, binascii.Error) as error:
            self.reply(400, json.dumps({'error': str(error) if isinstance(error, ValueError) and not isinstance(error, (json.JSONDecodeError, binascii.Error)) else '画像または選択した曲を確認してください。'}).encode())
        except Exception:
            self.reply(400, json.dumps({'error': '保存できませんでした。画像・音源の形式と空き容量を確認してください。'}).encode())

def serve(start_port=8765, open_browser=True):
    global HOST
    if not 1024 <= start_port <= 65515: raise ValueError('Invalid local port')
    for port in range(start_port, start_port + 20):
        HOST = f'http://127.0.0.1:{port}'
        try:
            server = LibraryHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(HOST + '/instance', timeout=1) as response:
                    instance = json.load(response)
                if instance.get('root') == str(ROOT) and instance.get('version') == 6:
                    print('URL: ' + HOST, flush=True)
                    if open_browser: webbrowser.open(HOST)
                    return
            except (OSError, ValueError):
                pass
    else:
        raise RuntimeError('利用できるローカルポートがありません。')
    print('URL: ' + HOST, flush=True)
    if open_browser: threading.Timer(0.5, lambda: webbrowser.open(HOST)).start()
    try: server.serve_forever()
    finally: server.server_close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local music library viewer')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    serve(args.port, not args.no_browser)
