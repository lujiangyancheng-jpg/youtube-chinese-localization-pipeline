#ifndef StageDir
  #define StageDir "..\build\super-resolution-pack\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppVersion
  #define AppVersion "0.7.0"
#endif

[Setup]
SetupIconFile={#SourcePath}\..\assets\branding\app-icon.ico
AppId={{4B2F285F-47D3-46C9-B6EE-5F18F22B6BD7}
AppName=Video Localizer AI Super Resolution Pack
AppVersion={#AppVersion}
AppPublisher=Video Localizer contributors
AppPublisherURL=https://github.com/lujiangyancheng-jpg/video-localizer
DefaultDirName={localappdata}\Programs\YouTube Chinese Localizer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=YouTube-Chinese-Localizer-{#AppVersion}-AI-Super-Resolution-Setup
Compression=lzma2/ultra64
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
UninstallDisplayName=Video Localizer AI Super Resolution Pack
UninstallFilesDir={app}\model-pack-uninstall\SuperResolution
InfoBeforeFile={#SourcePath}\super-resolution-pack-notice.txt

[Files]
Source: "{#StageDir}\runtime\super-resolution\*"; DestDir: "{app}\runtime\super-resolution"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\super-resolution-pack.json"; DestDir: "{app}\models"; Flags: ignoreversion
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
      'Select the folder where Video Localizer is already installed. ' +
      'Install the matching base application before this enhancement pack.';
    exit;
  end;
  if not FileExists(ManifestPath) or not LoadStringsFromFile(ManifestPath, ManifestLines) then begin
    Result := 'The selected folder does not contain a readable Video Localizer manifest.';
    exit;
  end;
  ApplicationMatches := False;
  VersionMatches := False;
  for Index := 0 to GetArrayLength(ManifestLines) - 1 do begin
    if (Pos('"application"', ManifestLines[Index]) > 0) and
       (Pos('"YouTube Chinese Localizer"', ManifestLines[Index]) > 0) then
      ApplicationMatches := True;
    if (Pos('"version"', ManifestLines[Index]) > 0) and
       (Pos('"{#AppVersion}"', ManifestLines[Index]) > 0) then
      VersionMatches := True;
  end;
  if not ApplicationMatches then begin
    Result := 'The selected folder is not a Video Localizer installation.';
    exit;
  end;
  if not VersionMatches then begin
    Result :=
      'This AI super-resolution pack requires Video Localizer v{#AppVersion}. ' +
      'Install the base package and component pack from compatible Releases.';
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
