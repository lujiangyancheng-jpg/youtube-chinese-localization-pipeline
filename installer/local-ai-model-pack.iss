#ifndef StageDir
  #define StageDir "..\build\local-ai-model-pack\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.6.9"
#endif
#ifndef ModelPackAppId
  #define ModelPackAppId "98E9F02E-2C63-4B29-A62A-23CBBEEFB562"
#endif

[Setup]
AppId={#ModelPackAppId}
AppName=YouTube Chinese Localizer Local AI Model Pack
AppVersion={#AppVersion}
AppPublisher=YouTube Chinese Localization Pipeline contributors
AppPublisherURL=https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline
DefaultDirName={localappdata}\Programs\YouTube Chinese Localizer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=YouTube-Chinese-Localizer-{#AppVersion}-Local-AI-Model-Setup
Compression=none
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=1900000000
WizardStyle=modern
UninstallDisplayName=YouTube Localizer Local AI Model Pack
UninstallFilesDir={app}\model-pack-uninstall\local-ai
InfoBeforeFile={#SourcePath}\local-ai-model-pack-notice.txt

[Files]
Source: "{#StageDir}\models\ollama\*"; DestDir: "{app}\models\ollama"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\runtime\ollama\*"; DestDir: "{app}\runtime\ollama"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\model-pack-local-ai.json"; DestDir: "{app}\models"; Flags: ignoreversion
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
      'Install the matching base application before installing this Local AI model pack.';
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
      'This Local AI model pack requires YouTube Chinese Localizer v{#AppVersion}. ' +
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
