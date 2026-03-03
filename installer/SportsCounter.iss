#define MyAppName "SportsCounter"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "SportsCounter"
#define MyAppExeName "SportsCounter.exe"

#ifndef LangName
  #define LangName "english"
#endif

#ifndef LangFile
  #define LangFile "compiler:Default.isl"
#endif

[Setup]
AppId={{A6FFDF4C-8D6A-42F2-8A2F-2D70060A5F95}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=SportsCounter_Setup_Admin_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "{#LangName}"; MessagesFile: "{#LangFile}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "..\dist\SportsCounter.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\USER_MANUAL_ZH.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName}\用户手册"; Filename: "{app}\docs\USER_MANUAL_ZH.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
