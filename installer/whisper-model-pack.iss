#ifndef StageDir
  #define StageDir "..\build\whisper-model-pack\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.6.6"
#endif
#ifndef WhisperModel
  #define WhisperModel "Small"
#endif
#ifndef ModelDirectory
  #define ModelDirectory "faster-whisper-small"
#endif
#ifndef ModelPackAppId
  #define ModelPackAppId "1D590E67-81C8-4D04-9AFE-167A52D8D8B4"
#endif

[Setup]
AppId={#ModelPackAppId}
AppName=YouTube Chinese Localizer Whisper {#WhisperModel} Model Pack
AppVersion={#AppVersion}
AppPublisher=YouTube Chinese Localization Pipeline contributors
AppPublisherURL=https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline
DefaultDirName={localappdata}\Programs\YouTube Chinese Localizer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=YouTube-Chinese-Localizer-{#AppVersion}-Whisper-{#WhisperModel}-Model-Setup
Compression=none
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=1900000000
WizardStyle=modern
UninstallDisplayName=YouTube Localizer Whisper {#WhisperModel} Model Pack
UninstallFilesDir={app}\model-pack-uninstall\{#WhisperModel}
InfoBeforeFile={#SourcePath}\whisper-model-pack-notice.txt

[Files]
Source: "{#StageDir}\models\{#ModelDirectory}\*"; DestDir: "{app}\models\{#ModelDirectory}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\model-pack-{#WhisperModel}.json"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "{#StageDir}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and not FileExists(AddBackslash(WizardDirValue) + 'runtime\python\python.exe') then
    MsgBox(
      'Select the folder where YouTube Chinese Localizer is already installed. ' +
      'The default location is normally correct. Install the base application before installing this model pack.',
      mbInformation,
      MB_OK);
end;
