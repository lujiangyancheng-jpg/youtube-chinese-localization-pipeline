#ifndef StageDir
  #define StageDir "..\build\offline-installer\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.6.0"
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
Compression=none
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=1900000000
WizardStyle=modern
UninstallDisplayIcon={app}\runtime\python\pythonw.exe
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

#if PackageTier == "Standard"
[InstallDelete]
Type: filesandordirs; Name: "{app}\models\faster-whisper-medium"
Type: filesandordirs; Name: "{app}\models\ollama"
Type: filesandordirs; Name: "{app}\runtime\ollama"
#endif

[Icons]
Name: "{autoprograms}\YouTube Chinese Localizer"; Filename: "{app}\Launch Localizer.cmd"; WorkingDir: "{userdocs}\YouTube Localizer Projects"
Name: "{autoprograms}\YouTube Localizer CLI"; Filename: "{app}\YouTube Localizer CLI.cmd"; WorkingDir: "{userdocs}\YouTube Localizer Projects"
Name: "{autoprograms}\Verify YouTube Localizer Installation"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Verify Offline Install.ps1"" -InstallRoot ""{app}"" -SkipInference"; WorkingDir: "{app}"
Name: "{userdesktop}\YouTube Chinese Localizer"; Filename: "{app}\Launch Localizer.cmd"; WorkingDir: "{userdocs}\YouTube Localizer Projects"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\Launch Localizer.cmd"; Description: "Launch YouTube Chinese Localizer"; WorkingDir: "{userdocs}\YouTube Localizer Projects"; Flags: postinstall nowait skipifsilent
