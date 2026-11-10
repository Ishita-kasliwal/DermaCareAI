# Keeps Windows from IDLE-sleeping only while a given process is running, then exits.
# It does not change any power settings: it just signals "system busy" once a minute
# (SetThreadExecutionState). Closing the lid or choosing Sleep still works.
#   .\scripts\keep_awake_while.ps1 -ProcessId 1234
param([Parameter(Mandatory)][int]$ProcessId)

Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
'@
$ES_SYSTEM_REQUIRED = [uint32]1

Write-Host "Keeping the PC awake while process $ProcessId runs..."
while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
    [void][Win32.Power]::SetThreadExecutionState($ES_SYSTEM_REQUIRED)
    Start-Sleep -Seconds 60
}
Write-Host "Process $ProcessId finished; normal sleep behaviour resumes."
