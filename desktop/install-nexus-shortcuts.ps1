$ErrorActionPreference='Stop'
$nexusRoot=Split-Path -Parent $PSScriptRoot
$nexusEntry=Join-Path $nexusRoot 'Start Research Nexus.vbs'
$nexusIcon=Join-Path $PSScriptRoot 'nexus-aurora-soft-rainbow.ico'
$nexusBackups=Join-Path $nexusRoot 'data\shortcut-backups'
if (!(Test-Path -LiteralPath $nexusEntry) -or !(Test-Path -LiteralPath $nexusIcon)) {throw 'Nexus assets are missing.'}
New-Item -ItemType Directory -Path $nexusBackups -Force | Out-Null
$nexusShell=New-Object -ComObject WScript.Shell
$nexusFolders=@($nexusRoot,[Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))
foreach($nexusFolder in $nexusFolders) {
    $nexusOld=Join-Path $nexusFolder 'Research Bridge.lnk'
    if(Test-Path -LiteralPath $nexusOld) {
        $oldLink=$nexusShell.CreateShortcut($nexusOld)
        if($oldLink.WorkingDirectory -eq $nexusRoot -or $oldLink.Arguments.Contains($nexusRoot)) {
            $backup=Join-Path $nexusBackups ((Split-Path $nexusFolder -Leaf)+'-Research-Bridge-'+(Get-Date -Format 'yyyyMMddHHmmss')+'.lnk')
            Move-Item -LiteralPath $nexusOld -Destination $backup
        }
    }
    $nexusLinkPath=Join-Path $nexusFolder 'Research Nexus.lnk'
    $nexusLink=$nexusShell.CreateShortcut($nexusLinkPath)
    $nexusLink.TargetPath=Join-Path $env:WINDIR 'System32\wscript.exe'
    $nexusLink.Arguments='"'+$nexusEntry+'"'
    $nexusLink.WorkingDirectory=$nexusRoot
    $nexusLink.IconLocation=$nexusIcon+',0'
    $nexusLink.Description='Research Nexus - your connected research workspace'
    $nexusLink.Save()
    [pscustomobject]@{Shortcut=$nexusLinkPath;Icon=$nexusLink.IconLocation}
}
