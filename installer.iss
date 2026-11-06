; Inno Setup script - SnapMitra Windows installer (no administrator rights needed)
#define AppName "SnapMitra"
#define AppVer  "3.0"
[Setup]
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=SnapMitra
DefaultDirName={autopf}\SnapMitra
DefaultGroupName=SnapMitra
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_out
OutputBaseFilename=SnapMitra-Setup
SetupIconFile=assets\snapmitra.ico
UninstallDisplayIcon={app}\SnapMitra.exe
UninstallDisplayName=SnapMitra - Your Smart Photo & Print Studio
WizardImageFile=assets\wizard_large.bmp
WizardSmallImageFile=assets\wizard_small.bmp
Compression=lzma2/fast
SolidCompression=no

[Files]
Source: "dist\SnapMitra\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\SnapMitra"; Filename: "{app}\SnapMitra.exe"; IconFilename: "{app}\SnapMitra.exe"
Name: "{group}\SnapMitra"; Filename: "{app}\SnapMitra.exe"; IconFilename: "{app}\SnapMitra.exe"

[Run]
Filename: "{app}\SnapMitra.exe"; Description: "Start SnapMitra"; Flags: nowait postinstall skipifsilent
