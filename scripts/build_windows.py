"""Build a folder-based Windows release. SPDX-License-Identifier: GPL-2.0-or-later"""
import argparse, hashlib, os, pathlib, shutil, subprocess, sys, zipfile, tempfile, urllib.request

PROJECT=pathlib.Path(__file__).resolve().parents[1]
VERSION='0.2.1'
WEBVIEW2_VERSION='1.0.3912.50'
WEBVIEW2_SHA256='8dd696301d8e5ad8389f26b636329bbf35754b793974e82168b1f6dda234eb07'
SOURCE_ITEMS=['app','assets','installer','launcher','scripts','tests','docs','README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore','requirements.txt']

def source_files():
    for name in SOURCE_ITEMS:
        item=PROJECT/name
        if item.is_file(): yield item
        else:
            for path in sorted(item.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc','.pyo'}: yield path

def archive(paths, target, root):
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in paths: bundle.write(path,path.relative_to(root).as_posix())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True,help='Directory containing python.exe, DLLs, Lib and LICENSE.txt')
    parser.add_argument('--output',default=str(PROJECT/'dist'))
    parser.add_argument('--webview2-package',help='Previously downloaded Microsoft.Web.WebView2 1.0.3912.50 .nupkg (optional)')
    args=parser.parse_args()
    runtime=pathlib.Path(args.runtime).resolve()
    if not (runtime/'python.exe').is_file() or not (runtime/'LICENSE.txt').is_file(): raise ValueError('A Windows Python runtime with LICENSE.txt is required')
    output=pathlib.Path(args.output).resolve(); output.mkdir(parents=True,exist_ok=True)
    # Use a pinned Microsoft SDK. The WebView2 Runtime itself is supplied by Windows.
    with tempfile.TemporaryDirectory(dir=output) as temp:
        package=pathlib.Path(args.webview2_package).resolve() if args.webview2_package else pathlib.Path(temp)/'webview2.nupkg'
        if not args.webview2_package:
            urllib.request.urlretrieve(f'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{WEBVIEW2_VERSION}/microsoft.web.webview2.{WEBVIEW2_VERSION}.nupkg',package)
        if hashlib.sha256(package.read_bytes()).hexdigest()!=WEBVIEW2_SHA256:
            raise ValueError('WebView2 SDK checksum does not match the pinned package')
        sdk=output/'webview2-build-sdk'
        if sdk.exists(): raise FileExistsError('Choose a fresh --output directory')
        sdk.mkdir()
        with zipfile.ZipFile(package) as archive_file:
            for name in ('lib/net462/Microsoft.Web.WebView2.Core.dll','lib/net462/Microsoft.Web.WebView2.WinForms.dll','runtimes/win-x64/native/WebView2Loader.dll','LICENSE.txt','NOTICE.txt'):
                (sdk/pathlib.PurePosixPath(name).name).write_bytes(archive_file.read(name))
    release=output/'MusicLibrary-Windows'
    if release.exists(): raise FileExistsError('Output folder already exists; choose a new --output directory')
    release.mkdir()
    shutil.copytree(PROJECT/'app',release/'app',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(PROJECT/'assets',release/'assets')
    shutil.copytree(runtime,release/'runtime',ignore=shutil.ignore_patterns('__pycache__','*.pyc','site-packages','ensurepip','idlelib','tkinter','turtledemo','test','tests','venv'))
    (release/'tools').mkdir()
    (release/'tools'/'README.txt').write_text('ffmpeg.exe と ffprobe.exe を必要に応じてこの場所に配置してください。PATHに導入済みの場合は不要です。\nこの配布物にはFFmpegを同梱していません。\n',encoding='utf-8-sig')
    for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md'): shutil.copy2(PROJECT/name,release/name)
    for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll'):
        shutil.copy2(sdk/name,release/name)
    (release/'licenses').mkdir()
    for name in ('LICENSE.txt','NOTICE.txt'): shutil.copy2(sdk/name,release/'licenses'/('WebView2-'+name))
    shutil.copy2(PROJECT/'docs'/'InnoSetup-LICENSE.txt',release/'licenses'/'InnoSetup-LICENSE.txt')
    (release/'source').mkdir()
    shutil.copy2(PROJECT/'launcher'/'MusicLibrary.cs',release/'source'/'MusicLibrary.cs')
    shutil.copy2(PROJECT/'scripts'/'build_windows.py',release/'source'/'build_windows.py')
    compiler=pathlib.Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET'/'Framework64'/'v4.0.30319'/'csc.exe'
    if not compiler.is_file(): raise FileNotFoundError('Windows .NET Framework C# compiler not found')
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
                    '/win32icon:'+str(PROJECT/'assets'/'music-library.ico'),
                    '/resource:'+str(PROJECT/'assets'/'music-library.ico')+',MusicLibrary.Icon',
                    '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll',
                    '/r:'+str(sdk/'Microsoft.Web.WebView2.Core.dll'),'/r:'+str(sdk/'Microsoft.Web.WebView2.WinForms.dll'),
                    '/out:'+str(release/'MusicLibrary.exe'),str(PROJECT/'launcher'/'MusicLibrary.cs')],check=True)
    (release/'MusicLibrary.exe.config').write_text('<?xml version="1.0" encoding="utf-8"?><configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/></startup></configuration>',encoding='utf-8')
    source_zip=output/f'music-library-browser-{VERSION}-source.zip'
    archive(list(source_files()),source_zip,PROJECT)
    shutil.copy2(source_zip,release/'source'/source_zip.name)
    release_zip=output/f'music-library-browser-{VERSION}-windows.zip'
    archive([p for p in sorted(release.rglob('*')) if p.is_file()],release_zip,output)
    sums=''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n' for path in (source_zip,release_zip))
    (output/'SHA256SUMS.txt').write_text(sums,encoding='ascii')
    # Only files from this SDK staging directory were created by this build.
    for item in sdk.iterdir(): item.unlink()
    sdk.rmdir()
    print(str(release/'MusicLibrary.exe'))
    print(str(source_zip));print(str(release_zip))

if __name__=='__main__': main()
