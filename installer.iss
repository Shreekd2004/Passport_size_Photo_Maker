; Inno Setup script - builds a normal Windows installer (no admin rights needed)
[Setup]
AppName=Passport Photo Maker
AppVersion=2.0
DefaultDirName={autopf}\PassportPhotoMaker
DefaultGroupName=Passport Photo Maker
PrivilegesRequired=lowest
OutputDir=installer_out
OutputBaseFilename=PassportPhotoMaker-Setup
Compression=lzma2/fast
SolidCompression=no
DisableProgramGroupPage=yes
UninstallDisplayName=Passport Photo Maker

[Files]
Source: "dist\PassportPhotoMaker\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Passport Photo Maker"; Filename: "{app}\PassportPhotoMaker.exe"
Name: "{group}\Passport Photo Maker"; Filename: "{app}\PassportPhotoMaker.exe"

[Run]
Filename: "{app}\PassportPhotoMaker.exe"; Description: "Start Passport Photo Maker"; Flags: nowait postinstall skipifsilent
