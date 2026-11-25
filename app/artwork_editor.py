"""Embed front covers without re-encoding audio; retain a full original backup."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from mutagen.id3 import ID3, ID3NoHeaderError, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture
from mutagen.wave import WAVE

SUPPORTED = {'.mp3', '.m4a', '.wav', '.flac'}
EDIT_LOCK = threading.RLock()
MAX_UPLOAD = 10 * 1024 * 1024


def tool(root, name):
    bundled = Path(root) / 'runtime' / (name + '.exe')
    tools_dir = os.environ.get('MUSIC_LIBRARY_TOOLS_DIR')
    alternate = Path(tools_dir) / (name + '.exe') if tools_dir else None
    if bundled.is_file(): return str(bundled)
    if alternate and alternate.is_file(): return str(alternate)
    return shutil.which(name)


def run(root, name, args, data=None, timeout=180):
    command = tool(root, name)
    if not command:
        raise ValueError('ffmpeg / ffprobe が見つかりません。')
    return subprocess.run([command, '-v', 'error', *args], input=data,
                          capture_output=True, check=True, timeout=timeout,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout


def image_bytes(root, data, size, codec='png'):
    return run(root, 'ffmpeg', ['-i', 'pipe:0', '-map', '0:v:0', '-frames:v', '1',
               '-vf', f'scale=min({size}\\,iw):min({size}\\,ih):force_original_aspect_ratio=decrease',
               '-map_metadata', '-1', '-f', 'image2pipe', '-c:v', codec, 'pipe:1'], data, 40)


def normalize_image(root, data):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('画像は10MB以下のJPEGまたはPNGを選んでください。')
    if not (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('JPEGまたはPNG画像を選んでください。')
    info = json.loads(run(root, 'ffprobe', ['-i', 'pipe:0', '-show_streams', '-of', 'json'], data, 20))
    stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
    w, h = stream.get('width', 0), stream.get('height', 0)
    if not w or not h or max(w, h) > 8192 or w * h > 25_000_000:
        raise ValueError('画像が大きすぎます。8192px以下・2500万画素以下の画像を選んでください。')
    picture = image_bytes(root, data, 1600)
    if not picture.startswith(b'\x89PNG') or len(picture) > 16 * 1024 * 1024:
        raise ValueError('画像を読み込めませんでした。別の画像を選んでください。')
    return picture


def read_picture(path):
    path = Path(path)
    if path.suffix.lower() == '.mp3':
        try:
            pictures = ID3(path, translate=False).getall('APIC')
        except ID3NoHeaderError:
            return None
        pictures.sort(key=lambda p: p.type != 3)
        return pictures[0].data if pictures else None
    if path.suffix.lower() == '.m4a':
        covers = MP4(path).get('covr', [])
        return bytes(covers[0]) if covers else None
    if path.suffix.lower() == '.flac':
        pictures = FLAC(path).pictures
        pictures.sort(key=lambda p: p.type != 3)
        return pictures[0].data if pictures else None
    if path.suffix.lower() == '.wav':
        audio = WAVE(path)
        pictures = audio.tags.getall('APIC') if audio.tags else []
        pictures.sort(key=lambda p: p.type != 3)
        return pictures[0].data if pictures else None
    return None


def embed(path, image):
    extension = Path(path).suffix.lower()
    if extension == '.mp3':
        try:
            tags = ID3(path, translate=False)
            version = 3 if tags.version[1] == 3 else 4
        except ID3NoHeaderError:
            tags, version = ID3(), 3
        tags.delall('APIC')
        tags.add(APIC(encoding=1, mime='image/png', type=3, desc='Front cover', data=image))
        tags.save(path, v2_version=version)
    elif extension == '.m4a':
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags['covr'] = [MP4Cover(image, imageformat=MP4Cover.FORMAT_PNG)]
        audio.save()
    elif extension == '.flac':
        audio = FLAC(path)
        picture = Picture()
        picture.type, picture.mime, picture.desc, picture.data = 3, 'image/png', 'Front cover', image
        picture.width = int.from_bytes(image[16:20], 'big')
        picture.height = int.from_bytes(image[20:24], 'big')
        picture.depth = 32
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()
    elif extension == '.wav':
        audio = WAVE(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall('APIC')
        audio.tags.add(APIC(encoding=1, mime='image/png', type=3, desc='Front cover', data=image))
        audio.save()
    else:
        raise ValueError('ジャケットの埋め込みはMP3・M4A・WAV・FLACに対応しています。')


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def audio_hash(root, path):
    return run(root, 'ffmpeg', ['-nostdin', '-i', str(path), '-map', '0:a', '-c', 'copy',
                               '-f', 'hash', '-hash', 'sha256', 'pipe:1']).strip()


def save_cover(root, path, image):
    """Caller validates the library path; edits are serialized for safe replacement."""
    root, path = Path(root), Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError('ジャケットの埋め込みはMP3・M4A・WAV・FLACに対応しています。')
    with EDIT_LOCK:
        normalized = normalize_image(root, image)
        thumb = image_bytes(root, normalized, 96, 'mjpeg')
        original_hash = file_hash(path)
        original_audio = audio_hash(root, path)
        if shutil.disk_usage(path.parent).free < path.stat().st_size + 20 * 1024 * 1024:
            raise ValueError('音源の保存に必要な空き容量がありません。')
        if shutil.disk_usage(root).free < path.stat().st_size + 20 * 1024 * 1024:
            raise ValueError('バックアップを保存する空き容量がありません。')
        with tempfile.NamedTemporaryFile(prefix='.artwork-', suffix=path.suffix, dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            shutil.copy2(path, temporary)
            embed(temporary, normalized)
            if read_picture(temporary) != normalized or audio_hash(root, temporary) != original_audio:
                raise ValueError('保存内容の検証に失敗しました。元の音源は変更していません。')
            saved_hash = file_hash(temporary)
            if file_hash(path) != original_hash:
                raise ValueError('処理中に音源が変更されました。もう一度操作してください。')
            key = uuid.uuid4().hex
            backup_dir = root / 'artwork-backups' / key
            backup_dir.mkdir(parents=True)
            backup = backup_dir / ('original' + path.suffix.lower())
            shutil.copy2(path, backup)
            if file_hash(backup) != original_hash or file_hash(path) != original_hash:
                raise ValueError('バックアップの検証に失敗しました。元の音源は変更していません。')
            manifest = {'path': str(path), 'filename': path.name, 'created': datetime.datetime.now().astimezone().isoformat(),
                        'original_sha256': original_hash, 'saved_sha256': saved_hash}
            (backup_dir / 'info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            overrides = root / 'artwork-overrides'
            overrides.mkdir(exist_ok=True)
            thumb_name = hashlib.sha256((str(path) + saved_hash).encode()).hexdigest() + '.jpg'
            (overrides / thumb_name).write_bytes(thumb)
            os.replace(temporary, path)
            return {'cover': 'artwork-overrides/' + thumb_name, 'backup': key, 'revision': saved_hash[:20]}
        finally:
            temporary.unlink(missing_ok=True)
