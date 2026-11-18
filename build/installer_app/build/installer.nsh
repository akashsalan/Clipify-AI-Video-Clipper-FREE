; Clipify AI Setup - NSIS Custom Hooks
; Prevents creation of an unverified setup wizard uninstaller that triggers Windows 11 Smart App Control

!macro customInstall
  ; Remove the setup wrapper uninstaller entry so only the actual Clipify AI application appears in Installed Apps
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\clipify-ai-setup"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\clipify-ai-setup"
!macroend

