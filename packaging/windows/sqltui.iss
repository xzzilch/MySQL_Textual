#define AppName "SQLTUI"
#define AppVersion "0.1.0"
#define AppPublisher "SQLTUI"
#define AppExeName "SQLTUI.exe"

[Setup]
AppId={{6A5B4956-0FD1-4D14-8F9B-E1781E523019}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\SQLTUI
DefaultGroupName={#AppName}
OutputDir=..\..\dist\installer
OutputBaseFilename=SQLTUI-Setup-x64
SetupIconFile=..\..\dist\sqltui.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\..\dist\SQLTUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SQLTUI"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\SQLTUI"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SQLTUI"; Flags: postinstall nowait skipifsilent
