import concurrent.futures, csv, datetime, json, pathlib, shutil, sqlite3, subprocess, hashlib, secrets

import argparse, os
from artwork_editor import tool

SOURCE = None
OUT = None
PROBE = None
APP_ROOT = pathlib.Path(__file__).resolve().parent
EXTENSIONS = {'.mp3', '.m4a', '.wav', '.flac', '.aac', '.ogg', '.opus', '.wma', '.aiff', '.aif', '.ape', '.dsf', '.dff'}

def repair_tag(value):
    # Some legacy ID3 tags declare Latin-1 but contain CP932 bytes.
    # C1 controls are evidence of this error; leave accented Latin text alone.
    if not any(128 <= ord(ch) <= 159 for ch in value):
        return value
    try:
        raw = value.encode('latin1')
    except UnicodeEncodeError:
        return value
    for encoding in ('utf-8', 'cp932'):
        try:
            fixed = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if not any(128 <= ord(ch) <= 159 for ch in fixed) and any('\u3040' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff' for ch in fixed):
            return fixed
    return value

def scan(path):
    row = dict(title=path.stem, album='', artist='', seconds=None, length='', path=str(path), uri=path.as_uri(), title_from_filename=True, error='', cover='')
    try:
        result = subprocess.run([PROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], capture_output=True, encoding='utf-8', errors='replace', timeout=90, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        info = json.loads(result.stdout)
        picture = next((s for s in info.get('streams', []) if s.get('disposition', {}).get('attached_pic')), None)
        if picture:
            coverdir = OUT / 'covers'
            coverdir.mkdir(exist_ok=True)
            key = hashlib.sha256((str(path) + str(path.stat().st_mtime_ns)).encode()).hexdigest()
            cover = coverdir / (key + '.jpg')
            if not cover.exists():
                ffmpeg = tool(OUT, 'ffmpeg')
                image = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-map', '0:' + str(picture['index']), '-frames:v', '1', '-vf', 'scale=96:96:force_original_aspect_ratio=decrease', '-y', str(cover)], capture_output=True, timeout=90, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if image.returncode and cover.exists(): cover.unlink()
            if cover.exists(): row['cover'] = 'covers/' + cover.name
        fmt = info.get('format', {})
        streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
        tags = {}
        for s in streams:
            tags.update({k.lower(): v for k, v in s.get('tags', {}).items()})
        tags.update({k.lower(): v for k, v in fmt.get('tags', {}).items()})
        for key in ('title', 'album', 'artist'):
            value = repair_tag(str(tags.get(key, '')).strip())
            if value:
                row[key] = value
                if key == 'title': row['title_from_filename'] = False
        duration = fmt.get('duration') or next((s.get('duration') for s in streams if s.get('duration')), None)
        if duration is not None:
            row['seconds'] = round(float(duration), 3)
            total = round(row['seconds'])
            row['length'] = (f'{total//3600}:{total//60%60:02}:{total%60:02}' if total >= 3600 else f'{total//60}:{total%60:02}')
    except Exception as exc:
        row['error'] = str(exc)
    return row

def build(source, output, progress=None, excluded=()):
    global SOURCE, OUT, PROBE
    SOURCE, OUT = pathlib.Path(source).resolve(), pathlib.Path(output).resolve()
    if not SOURCE.is_dir(): raise ValueError('音源フォルダーが見つかりません。')
    if SOURCE == OUT: raise ValueError('一覧の保存先には音源と別のフォルダーを指定してください。')
    OUT.mkdir(parents=True, exist_ok=True)
    PROBE = tool(OUT, 'ffprobe')
    if not PROBE or not tool(OUT, 'ffmpeg'): raise RuntimeError('ffmpegとffprobeをPATHに追加するか、toolsフォルダーに配置してください。')
    exclusions = [OUT, *[pathlib.Path(p).resolve() for p in excluded]]
    files = []
    for parent, directories, names in os.walk(SOURCE):
        parent = pathlib.Path(parent)
        directories[:] = [name for name in directories if name not in {'.git', '$RECYCLE.BIN', 'System Volume Information'} and not any((parent/name).resolve().is_relative_to(p) for p in exclusions)]
        for name in names:
            path = parent/name
            if path.suffix.lower() in EXTENSIONS and path.is_file() and not any(path.resolve().is_relative_to(p) for p in exclusions): files.append(path)
    files.sort()
    if progress: progress(0, len(files))
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, row in enumerate(pool.map(scan, files), 1):
            rows.append(row)
            if progress: progress(i, len(files))
    temp = OUT / 'music.new.sqlite'
    if temp.exists(): temp.unlink()
    with sqlite3.connect(temp) as db:
        db.execute('CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, album TEXT, artist TEXT, seconds REAL, length TEXT, path TEXT UNIQUE NOT NULL, uri TEXT, title_from_filename INTEGER, error TEXT, cover TEXT)')
        for i, row in enumerate(rows, 1): row['id'] = i
        db.executemany('INSERT INTO tracks(id,title,album,artist,seconds,length,path,uri,title_from_filename,error,cover) VALUES(:id,:title,:album,:artist,:seconds,:length,:path,:uri,:title_from_filename,:error,:cover)', rows)
        for key in ('title','album','artist','seconds'):
            db.execute(f'CREATE INDEX tracks_{key} ON tracks({key})')
        db.execute('CREATE TABLE metadata (source TEXT, created TEXT)')
        db.execute('INSERT INTO metadata VALUES (?,?)', (str(SOURCE), datetime.datetime.now().astimezone().isoformat()))
        assert db.execute('SELECT COUNT(*) FROM tracks').fetchone()[0] == len(files)
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    temp.replace(OUT / 'music.sqlite')
    with (OUT / 'music.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['曲名','アルバム名','アーティスト名','長さ','長さ（秒）','ファイルパス','曲名はファイル名由来','読み取りエラー'])
        w.writerows([r[k] for k in ('title','album','artist','length','seconds','path','title_from_filename','error')] for r in rows)
    payload = json.dumps(rows, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (APP_ROOT / 'viewer.template.html').read_text(encoding='utf-8')
    tokenfile = OUT / 'local-token.txt'
    if not tokenfile.exists(): tokenfile.write_text(secrets.token_hex(32), encoding='ascii')
    (OUT / '音楽一覧.html').write_text(template.replace('__DATA__', payload).replace('__TOKEN__', tokenfile.read_text(encoding='ascii')), encoding='utf-8-sig')
    report = dict(source=str(SOURCE), tracks=len(rows), missing_album=sum(not r['album'] for r in rows), missing_artist=sum(not r['artist'] for r in rows), missing_duration=sum(r['seconds'] is None for r in rows), filename_titles=sum(r['title_from_filename'] for r in rows), errors=[{'path':r['path'],'error':r['error']} for r in rows if r['error']])
    report['covers'] = sum(bool(r['cover']) for r in rows)
    (OUT / '読み取り結果.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Build a music library from a chosen folder')
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args=parser.parse_args()
    report=build(args.source,args.output,progress=lambda current,total: print(f'{current}/{total}',flush=True))
    print(json.dumps(report,ensure_ascii=True))
