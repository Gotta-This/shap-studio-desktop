; QuickShot stays alive while the main app is closed. Stop it before NSIS
; replaces or removes quickshot.exe during an upgrade or uninstall.
!macro NSIS_HOOK_PREINSTALL
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM quickshot.exe /T' $0
  Sleep 500
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM quickshot.exe /T' $0
  Sleep 500
!macroend
