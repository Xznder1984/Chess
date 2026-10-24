#define AppName "Chess"
#define AppVersion "1.0.0"

[Setup]
AppId={{72D8F758-9F90-4AF8-AC83-8881E3EACB15}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Chess
DefaultGroupName=Chess
OutputDir=release
OutputBaseFilename=Chess-Setup-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\Chess\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Chess"; Filename: "{app}\Chess.exe"
Name: "{autodesktop}\Chess"; Filename: "{app}\Chess.exe"

[Run]
Filename: "{app}\Chess.exe"; Description: "Launch Chess"; Flags: postinstall nowait skipifsilent
