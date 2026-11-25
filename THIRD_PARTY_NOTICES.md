# Third-party notices

## Mutagen 1.47.0

- Copyright: the Mutagen contributors (individual copyright notices remain in source files).
- License: GPL-2.0-or-later.
- Upstream: https://github.com/quodlibet/mutagen
- Original Python source and notices: `app/vendor/mutagen`.
- License text: `app/vendor/mutagen-1.47.0.dist-info/COPYING`.

## CPython (Windows release only)

The Windows archive includes an unmodified CPython runtime, with optional development tools and cached bytecode omitted.
The original Python license and bundled component notices are retained in `runtime/LICENSE.txt`.
Source and version information: https://www.python.org/downloads/source/ .
CPython is not included in the repository source archive.

## FFmpeg / ffprobe

FFmpeg is an external runtime dependency and is not included in either archive.
Users may use an existing installation or place their separately obtained executables in `tools`.
Upstream: https://ffmpeg.org/ .

## Windows / .NET Framework

The launcher uses the .NET Framework and Windows Forms installed with Windows.
These platform components are not distributed by this project.

## Microsoft WebView2 SDK 1.0.3912.50

Copyright (C) Microsoft Corporation. All rights reserved.
The Windows release includes Microsoft.Web.WebView2.Core.dll, Microsoft.Web.WebView2.WinForms.dll and the x64 WebView2Loader.dll from the unmodified Microsoft NuGet package.
License and notices are retained in docs/WebView2-LICENSE.txt and docs/WebView2-NOTICE.txt in the source archive, and licenses/WebView2-LICENSE.txt and licenses/WebView2-NOTICE.txt in the Windows archive.
Package: https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3912.50
The separately installed Evergreen WebView2 Runtime is not included.

## Inno Setup 6.7.3 (installer only)

The setup and uninstaller are built with Inno Setup by Jordan Russell and Martijn Laan.
Upstream: https://jrsoftware.org/ . The compiler is not included in the app.
The original license is retained in `docs/InnoSetup-LICENSE.txt` in the source and `licenses/InnoSetup-LICENSE.txt` in the installed application.

## Application artwork

The music library icon is original vector artwork included under this project's GPL-2.0-or-later license.
The development-only renderer uses Sharp and the rasterization is included as PNG and ICO. Sharp is not shipped with the runtime application.
