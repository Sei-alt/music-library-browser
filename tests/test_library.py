"""Integration tests use generated audio only, never a personal music library."""
import base64
from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zlib

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
import artwork_editor as editor
import build_music_db
import library_app

def png():
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',8,8,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\x20\x80\xa0'*8)*8))+chunk(b'IEND',b'')

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg and ffprobe required')
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/'音源 フォルダー'
        self.source.mkdir()
        self.data=self.root/'データ 保存先'
        self.data.mkdir()
    def tearDown(self): self.temp.cleanup()
    def audio(self,suffix='.mp3'):
        codecs={'.mp3':'libmp3lame','.m4a':'aac','.wav':'pcm_s16le','.flac':'flac'}
        path=self.source/('日本語 曲名'+suffix)
        editor.run(self.data,'ffmpeg',['-y','-f','lavfi','-i','sine=frequency=440:duration=0.4','-c:a',codecs[suffix],'-metadata','title=曲名 日本語','-metadata','artist=テスト作者',str(path)])
        return path
    def test_folder_profiles_and_update(self):
        self.audio()
        report=build_music_db.build(self.source,self.data)
        self.assertEqual(report['tracks'],1)
        with closing(sqlite3.connect(self.data/'music.sqlite')) as db:
            title,artist=db.execute('SELECT title,artist FROM tracks').fetchone()
            self.assertEqual((title,artist),('曲名 日本語','テスト作者'))
        first=library_app.profile_directory(self.source,self.root/'settings')
        self.assertEqual(first,library_app.profile_directory(self.source,self.root/'settings'))
        self.assertNotEqual(first,library_app.profile_directory(self.root/'other',self.root/'settings'))
        html=(self.data/'音楽一覧.html').read_text(encoding='utf-8-sig')
        self.assertIn('edit.textContent=\'ジャケットを設定\'',html)
        self.assertNotIn('__TOKEN__',html)
        self.audio('.wav')
        self.assertEqual(build_music_db.build(self.source,self.data)['tracks'],2)
    def test_cover_editing_formats(self):
        for suffix in ('.mp3','.m4a','.wav','.flac'):
            with self.subTest(format=suffix):
                path=self.audio(suffix)
                before=editor.audio_hash(self.data,path)
                original=editor.file_hash(path)
                result=editor.save_cover(self.data,path,png())
                self.assertEqual(before,editor.audio_hash(self.data,path))
                self.assertEqual(original,editor.file_hash(self.data/'artwork-backups'/result['backup']/('original'+suffix)))
                self.assertTrue(editor.read_picture(path).startswith(b'\x89PNG'))
                # A later full scan must retain the newly embedded jacket.
                report=build_music_db.build(self.source,self.data)
                with closing(sqlite3.connect(self.data/'music.sqlite')) as db:
                    cover=db.execute('SELECT cover FROM tracks WHERE path=?',(str(path),)).fetchone()[0]
                self.assertTrue(cover)
    def test_upload_security_and_reload(self):
        path=self.audio()
        build_music_db.build(self.source,self.data)
        previous=os.environ.get('MUSIC_LIBRARY_DATA_DIR')
        os.environ['MUSIC_LIBRARY_DATA_DIR']=str(self.data)
        try:
            spec=importlib.util.spec_from_file_location('test_browser_backend',APP/'local_browser.py')
            backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
        finally:
            if previous is None:os.environ.pop('MUSIC_LIBRARY_DATA_DIR',None)
            else:os.environ['MUSIC_LIBRARY_DATA_DIR']=previous
        server=backend.LibraryHTTPServer(('127.0.0.1',0),backend.Handler)
        # A second viewer must never silently share the same Windows port.
        with self.assertRaises(OSError):
            backend.LibraryHTTPServer(server.server_address,backend.Handler)
        host='http://127.0.0.1:'+str(server.server_address[1]);backend.HOST=host
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token=(self.data/'local-token.txt').read_text(encoding='ascii')
        body=dict(id=1,path=str(path),token=token,image=base64.b64encode(png()).decode())
        def upload(value,origin=None):
            headers={'Content-Type':'text/plain'}
            if origin:headers['Origin']=origin
            return opener.open(urllib.request.Request(host+'/artwork',data=json.dumps(value).encode(),headers=headers),timeout=30)
        try:
            before=editor.file_hash(path)
            for value,origin,status in [({**body,'token':'invalid'},None,403),({**body,'path':str(self.root/'outside.mp3')},None,404),({**body,'image':'bm90LWltYWdl'},None,400),(body,'https://example.invalid',403)]:
                with self.assertRaises(urllib.error.HTTPError) as error:upload(value,origin)
                self.assertEqual(error.exception.code,status)
            self.assertEqual(before,editor.file_hash(path))
            with upload(body) as response:result=json.load(response)
            with opener.open(host+'/') as response:html=response.read().decode('utf-8')
            rows=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
            self.assertEqual(rows[0]['cover'],result['cover'])
            query=urllib.parse.urlencode(dict(token=token,path=str(path)))
            request=urllib.request.Request(host+'/audio/1?'+query,headers={'Range':'bytes=0-63'})
            with opener.open(request) as response:
                self.assertEqual(response.status,206);self.assertEqual(response.read(),path.read_bytes()[:64])
        finally:server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main()
