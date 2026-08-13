#ifndef StageDir
  #define StageDir "..\build\offline-installer\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.6.8"
#endif
#ifndef PackageTier
  #define PackageTier "Complete"
#endif

[Setup]
AppId={{96FB8698-9622-4824-9224-87C402D0BA9E}
AppName=YouTube Chinese Localizer
AppVersion={#AppVersion}
AppPublisher=YouTube Chinese Localization Pipeline contributors
AppPublisherURL=https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline
DefaultDirName={localappdata}\Programs\YouTube Chinese Localizer
DefaultGroupName=YouTube Chinese Localizer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=YouTube-Chinese-Localizer-{#AppVersion}-{#PackageTier}-Offline-Setup
#if PackageTier == "Standard"
; Standard contains no multi-gigabyte LLM blob, so high LZMA2 compression substantially reduces
; the download without removing a runtime, model, font, or hardware fallback.
Compression=lzma2/ultra64
SolidCompression=yes
#else
; The Complete package contains a large already-compressed Qwen blob. Recompressing it gives
; negligible savings while significantly increasing build and install time.
Compression=none
SolidCompression=no
#endif
DiskSpanning=yes
DiskSliceSize=1900000000
WizardStyle=modern
UninstallDisplayIcon={app}\Localize Studio.exe
VersionInfoVersion={#AppVersion}
VersionInfoProductName=YouTube Chinese Localizer Offline
VersionInfoDescription=Offline English-Chinese video localization application

#if PackageTier == "Standard"
InfoBeforeFile={#SourcePath}\standard-package-notice.txt
#else
InfoBeforeFile={#SourcePath}\complete-package-notice.txt
#endif

[Dirs]
Name: "{userappdata}\YouTube Chinese Localizer"
Name: "{userdocs}\YouTube Localizer Projects"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Keep the visible shortcut target outside a custom Unicode install directory. The relay launcher
; resolves the true installation root through the per-user uninstall record using Unicode APIs.
Source: "{#StageDir}\Localize Studio.exe"; DestDir: "{userappdata}\YouTube Chinese Localizer"; DestName: "Localize Studio Launcher.exe"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\Localize Studio Launcher.exe"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\YouTube Chinese Localizer\Localize Studio Launcher.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\Localize Studio Launcher.exe"; ValueType: string; ValueName: "Path"; ValueData: "{userappdata}\YouTube Chinese Localizer"; Flags: uninsdeletevalue

[UninstallDelete]
Type: files; Name: "{userappdata}\YouTube Chinese Localizer\Localize Studio Launcher.exe"

#if PackageTier == "Standard"
[InstallDelete]
Type: filesandordirs; Name: "{app}\models\faster-whisper-medium"
Type: filesandordirs; Name: "{app}\models\ollama"
Type: filesandordirs; Name: "{app}\runtime\ollama"
#endif

[Icons]
Name: "{autoprograms}\YouTube Chinese Localizer"; Filename: "{userappdata}\YouTube Chinese Localizer\Localize Studio Launcher.exe"; WorkingDir: "{userdocs}\YouTube Localizer Projects"
Name: "{autoprograms}\YouTube Localizer CLI"; Filename: "{app}\YouTube Localizer CLI.cmd"; WorkingDir: "{userdocs}\YouTube Localizer Projects"
Name: "{autoprograms}\Verify YouTube Localizer Installation"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Verify Offline Install.ps1"" -InstallRoot ""{app}"" -SkipInference"; WorkingDir: "{app}"
Name: "{userdesktop}\YouTube Chinese Localizer"; Filename: "{userappdata}\YouTube Chinese Localizer\Localize Studio Launcher.exe"; WorkingDir: "{userdocs}\YouTube Localizer Projects"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\Localize Studio.exe"; Description: "Launch YouTube Chinese Localizer"; WorkingDir: "{userdocs}\YouTube Localizer Projects"; Flags: postinstall nowait skipifsilent
