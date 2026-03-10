param(
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    [Parameter(Mandatory = $false)]
    [string]$WrapperKey = ""
)

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "windows\start_remote_wrappers.bat"

if (-not (Test-Path $script)) {
    Write-Error "Missing script: $script"
    exit 1
}

$taskName = "agentchattr-remote-wrappers"
$arg = "`"$script`" $ServerUrl"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $arg"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if ($WrapperKey) {
    [Environment]::SetEnvironmentVariable("AGENTCHATTR_WRAPPER_KEY", $WrapperKey, "User")
    Write-Host "Saved AGENTCHATTR_WRAPPER_KEY to User environment."
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Installed startup task: $taskName"
Write-Host "You can run now with: Start-ScheduledTask -TaskName $taskName"
