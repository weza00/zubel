; Instalador de Zubel (Inno Setup 6).
; Compilar:  iscc /DAppVersion=1.0.0 installer\zubel.iss   (o python tools\build.py)
;
; Se instala por usuario (sin permisos de administrador) para que la carpeta
; del programa sea escribible: ahí viven yt-dlp, FFmpeg y Deno (en {app}\bin)
; y pueden actualizarse desde la propia app. Durante la instalación se
; descargan sus últimas versiones desde los repositorios oficiales.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Zubel"
#define AppExe "Zubel.exe"

[Setup]
AppId={{6B0B6F2E-4C1A-4E0B-9C3E-5A7D2F9B1A0E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Zubel
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Zubel-{#AppVersion}-setup
SetupIconFile=..\assets\zubel.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Zubel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Descarga yt-dlp, FFmpeg y Deno (últimas versiones) a {app}\bin.
Filename: "{app}\{#AppExe}"; Parameters: "--install-deps"; StatusMsg: "Descargando yt-dlp, FFmpeg y Deno…"; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Los componentes descargados no los registra el instalador: se borran aparte.
Type: filesandordirs; Name: "{app}\bin"
