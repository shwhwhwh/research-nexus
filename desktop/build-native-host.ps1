param([string]$OutputPath = (Join-Path $PSScriptRoot 'NativeDockHost.exe'))
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '.NET Framework C# compiler is unavailable.' }
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /langversion:5 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.Core.dll ('/win32icon:' + (Join-Path $PSScriptRoot 'nexus-aurora-soft-rainbow.ico')) ('/out:' + $OutputPath) (Join-Path $PSScriptRoot 'NativeDockHost.cs')
if ($LASTEXITCODE -ne 0) { throw 'Native window component compilation failed.' }
