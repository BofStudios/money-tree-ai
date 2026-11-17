; Built by scripts/build_exe.py, which passes /DAppVersion, /DSourceDir and
; /DLicensePage (the terms of use followed by the MIT licence).
; Per-user install, no admin rights needed. Keys, settings and learning live in
; %LOCALAPPDATA%\BofStudios\Money Tree AI, which an uninstall leaves in place.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Money Bot"
#endif
#ifndef LicensePage
  #define LicensePage "..\LICENSE"
#endif

[Setup]
AppId={{305D42B3-3C9B-4270-BE37-29D153D21509}
AppName=Money Bot
AppVersion={#AppVersion}
AppVerName=Money Bot {#AppVersion}
AppPublisher=BOF Studios
AppPublisherURL=https://github.com/BofStudios/money-tree-ai
DefaultDirName={autopf}\Money Bot
DefaultGroupName=Money Bot
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MoneyBot-Setup-{#AppVersion}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\Money Bot.exe
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
Name: "{group}\Money Bot"; Filename: "{app}\Money Bot.exe"; IconFilename: "{app}\Money Bot.exe"
Name: "{group}\{cm:UninstallProgram,Money Bot}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Money Bot"; Filename: "{app}\Money Bot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Money Bot.exe"; Description: "{cm:LaunchProgram,Money Bot}"; Flags: nowait postinstall skipifsilent
