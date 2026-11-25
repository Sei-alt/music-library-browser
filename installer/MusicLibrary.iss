; SPDX-License-Identifier: GPL-2.0-or-later
#ifndef ReleaseDir
  #error ReleaseDir must point to MusicLibrary-Windows
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#define AppVersion "0.2.1"
#ifdef SmokeTestRoot
  #define IconPrograms SmokeTestRoot + "\start-menu"
  #define IconDesktop SmokeTestRoot + "\desktop"
#else
  #define IconPrograms "{userprograms}"
  #define IconDesktop "{userdesktop}"
#endif

[Setup]
AppId={{E1B26DAD-D63C-42DF-B5BD-8CFF82894E7D}
AppName=音楽ライブラリ
AppVersion={#AppVersion}
AppVerName=音楽ライブラリ {#AppVersion}
AppPublisher=Music Library contributors
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=音楽ライブラリ セットアップ
DefaultDirName={localappdata}\Programs\MusicLibrary
DefaultGroupName=音楽ライブラリ
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AppMutex=MusicLibraryDesktop
SetupMutex=MusicLibrarySetup
SetupIconFile=..\assets\music-library.ico
UninstallDisplayIcon={app}\MusicLibrary.exe
UninstallDisplayName=音楽ライブラリ
LicenseFile=..\LICENSE
InfoBeforeFile=..\docs\INSTALL-BEFORE.txt
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=MusicLibrary-Setup-{#AppVersion}-x64
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
ChangesEnvironment=no
#ifdef SmokeTestRoot
; Test builds keep shortcuts in the workspace and omit system registration.
; This branch is absent from the distributed installer.
CreateUninstallRegKey=no
UsePreviousAppDir=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousLanguage=no
#endif

[Languages]
Name: japanese; MessagesFile: compiler:Languages\Japanese.isl
Name: english; MessagesFile: compiler:Default.isl

[Tasks]
Name: desktopicon; Description: デスクトップにショートカットを作成する; GroupDescription: ショートカット:

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc,*.pyo"

[Icons]
Name: "{#IconPrograms}\音楽ライブラリ"; Filename: "{app}\MusicLibrary.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MusicLibrary.exe"; AppUserModelID: MusicLibrary.Desktop; Check: not WizardNoIcons
Name: "{#IconDesktop}\音楽ライブラリ"; Filename: "{app}\MusicLibrary.exe"; WorkingDir: "{app}"; IconFilename: "{app}\MusicLibrary.exe"; AppUserModelID: MusicLibrary.Desktop; Tasks: desktopicon; Check: not WizardNoIcons

[Run]
Filename: "{app}\MusicLibrary.exe"; Description: 音楽ライブラリを起動する; Flags: nowait postinstall skipifsilent

; App data, artwork backups and the user's music live outside {app}.
; They are deliberately retained on uninstall. Do not add [UninstallDelete].

[Code]
function InitializeSetup(): Boolean;
var
  Release: Cardinal;
begin
  Result := RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', Release) and (Release >= 528040);
  if not Result then
    MsgBox('.NET Framework 4.8 以降が必要です。Windows Update を実行してから、もう一度インストールしてください。', mbError, MB_OK);
end;
