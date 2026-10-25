[Setup]
AppId={{54785D43-52BB-41EC-BD0F-6EAEB7595061}
AppName=SHAP 分析工作台
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\SHAPStudio
DefaultGroupName=SHAP Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=SHAPStudio-Setup-Windows-x64
SetupIconFile=clinical_studio\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SHAPStudio.exe

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\SHAPStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SHAP Studio"; Filename: "{app}\SHAPStudio.exe"
Name: "{autodesktop}\SHAP Studio"; Filename: "{app}\SHAPStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SHAPStudio.exe"; Description: "Launch SHAP Studio"; Flags: nowait postinstall skipifsilent
