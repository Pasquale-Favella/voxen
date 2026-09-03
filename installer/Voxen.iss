#define MyAppName "Voxen"
#define MyAppVersion "0.1.1"
#define MyAppPublisher "Voxen"
#define MyAppExeName "Voxen.exe"

[Setup]
AppId={{A3EF4D8D-7C93-4C36-9B6C-VOXEN0000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Voxen
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=Voxen-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\dist\Voxen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Voxen"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\Voxen"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia Voxen"; Flags: nowait postinstall skipifsilent
