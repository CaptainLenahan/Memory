; Inno Setup script for Memory-Setup-<version>.exe. Built by scripts\build.ps1 (locally or in GitHub Actions):
;   ISCC.exe /DAppVersion=1.2.3 packaging\memory.iss
; Per-user install (no admin rights), into %LOCALAPPDATA%\Programs\Memory. Your data lives in %LOCALAPPDATA%\Memory
; and is kept across updates and uninstalls (uninstall asks whether to delete it).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change AppId: it's how Windows recognises an update to the same app.
AppId={{6E3F1B2A-9C47-4D6B-8E21-3A5C7D9F0B14}
AppName=Memory
AppVersion={#AppVersion}
AppVerName=Memory {#AppVersion}
AppPublisher=CaptainLenahan
AppPublisherURL=https://github.com/CaptainLenahan/Memory
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Memory
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Memory-Setup-{#AppVersion}
SetupIconFile=..\frontend\icon.ico
UninstallDisplayIcon={app}\Memory.exe
UninstallDisplayName=Memory
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start Memory when I sign in to Windows (recommended)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Memory\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; clear out the previous version's bundled files so nothing stale is left behind after an update
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{userprograms}\Memory"; Filename: "{app}\Memory.exe"; Parameters: "--open"; Comment: "Open Memory"
Name: "{userdesktop}\Memory"; Filename: "{app}\Memory.exe"; Parameters: "--open"; Comment: "Open Memory"; Tasks: desktopicon

[Run]
Filename: "{app}\Memory.exe"; Parameters: "--install-startup --quiet"; StatusMsg: "Setting Memory to start with Windows..."; Flags: runhidden; Tasks: startup
Filename: "{app}\Memory.exe"; Parameters: "--remove-startup --quiet"; Flags: runhidden; Tasks: not startup
Filename: "{app}\Memory.exe"; Parameters: "--open"; Description: "Open Memory now"; Flags: postinstall nowait skipifsilent
; silent updates (/SILENT, e.g. scripted) still bring the server back up
Filename: "{app}\Memory.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{app}\Memory.exe"; Parameters: "--remove-startup --quiet"; Flags: runhidden; RunOnceId: "RemoveStartup"

[Code]
procedure StopMemory;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Memory.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopMemory;
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopMemory;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Memory');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Also delete your Memory data (tasks, notes, files and settings) in ' + DataDir + '?' + #13#10#13#10 +
                'Choose No to keep it for a future reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
