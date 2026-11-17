; Old clients call quitAndInstall(false, true). Only updater-launched installs
; run silently; a normal first install keeps the assisted setup wizard.
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!macro customInit
  Push $R0
  Push $R1
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "--updated" $R1
  ${IfNot} ${Errors}
    SetSilent silent
  ${EndIf}
  Pop $R1
  Pop $R0
  ClearErrors
!macroend
