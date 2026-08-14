#ifndef StageDir
  #define StageDir "..\build\whisper-model-pack\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.7.0"
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
SetupIconFile={#SourcePath}\..\assets\branding\app-icon.ico
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
function BaseInstallationError(const InstallDir: String): String;
var
  ManifestPath: String;
  ManifestLines: TArrayOfString;
  Index: Integer;
  ApplicationMatches: Boolean;
  VersionMatches: Boolean;
begin
  ManifestPath := AddBackslash(InstallDir) + 'offline-assets.json';
  if not FileExists(AddBackslash(InstallDir) + 'runtime\python\python.exe') then begin
    Result :=
      'Select the folder where YouTube Chinese Localizer is already installed. ' +
      'Install the matching base application before installing this Whisper model pack.';
    exit;
  end;
  if not FileExists(ManifestPath) or not LoadStringsFromFile(ManifestPath, ManifestLines) then begin
    Result :=
      'The selected folder does not contain a readable YouTube Chinese Localizer installation manifest. ' +
      'Reinstall the matching base application first.';
    exit;
  end;
  ApplicationMatches := False;
  VersionMatches := False;
  for Index := 0 to GetArrayLength(ManifestLines) - 1 do begin
    if (Pos('"application"', ManifestLines[Index]) > 0) and
       (Pos('"YouTube Chinese Localizer"', ManifestLines[Index]) > 0) then begin
      ApplicationMatches := True;
    end;
    if (Pos('"version"', ManifestLines[Index]) > 0) and
       (Pos('"{#AppVersion}"', ManifestLines[Index]) > 0) then begin
      VersionMatches := True;
    end;
  end;
  if not ApplicationMatches then begin
    Result := 'The selected folder is not a YouTube Chinese Localizer installation.';
    exit;
  end;
  if not VersionMatches then begin
    Result :=
      'This Whisper {#WhisperModel} model pack requires YouTube Chinese Localizer v{#AppVersion}. ' +
      'Install the matching base package and model pack from the same Release.';
    exit;
  end;
  Result := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorMessage: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then begin
    ErrorMessage := BaseInstallationError(WizardDirValue);
    if ErrorMessage <> '' then begin
      MsgBox(ErrorMessage, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := BaseInstallationError(WizardDirValue);
end;
