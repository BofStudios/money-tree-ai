; Built by scripts/build_exe.py, which passes /DAppVersion, /DSourceDir and
; /DLicensePage (the terms of use followed by the MIT licence).
; Per-user install, no admin rights needed. Keys, settings and learning live in
; %LOCALAPPDATA%\BofStudios\Money Tree AI, which an uninstall leaves in place.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Money Tree AI"
#endif
#ifndef LicensePage
  #define LicensePage "..\LICENSE"
#endif

[Setup]
AppId={{305D42B3-3C9B-4270-BE37-29D153D21509}
AppName=Money Tree AI
AppVersion={#AppVersion}
AppVerName=Money Tree AI {#AppVersion}
AppPublisher=BOF Studios
AppPublisherURL=https://github.com/BofStudios/money-tree-ai
DefaultDirName={autopf}\Money Tree AI
DefaultGroupName=Money Tree AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MoneyTreeAI-Setup-{#AppVersion}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\Money Tree AI.exe
LicenseFile={#LicensePage}
InfoBeforeFile=before-install.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Money Tree AI"; Filename: "{app}\Money Tree AI.exe"; IconFilename: "{app}\Money Tree AI.exe"
Name: "{group}\{cm:UninstallProgram,Money Tree AI}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Money Tree AI"; Filename: "{app}\Money Tree AI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Money Tree AI.exe"; Description: "{cm:LaunchProgram,Money Tree AI}"; Flags: nowait postinstall skipifsilent
