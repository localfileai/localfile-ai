param(
    [Parameter(Mandatory = $true)]
    [string]$Title,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]+(?:-[a-z0-9]+)*$')]
    [string]$Slug
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$reportDir = Join-Path $repoRoot 'docs\experiments'
$templatePath = Join-Path $reportDir 'TEMPLATE.md'

if (-not (Test-Path -LiteralPath $templatePath)) {
    throw "Report template not found: $templatePath"
}

$numbers = Get-ChildItem -LiteralPath $reportDir -File -Filter '*.md' |
    Where-Object { $_.BaseName -match '^(\d{3})-' } |
    ForEach-Object { [int]$Matches[1] }
if ($numbers) {
    $next = [int](($numbers | Measure-Object -Maximum).Maximum) + 1
} else {
    $next = 1
}
$number = '{0:D3}' -f $next
$target = Join-Path $reportDir "$number-$Slug.md"

if (Test-Path -LiteralPath $target) {
    throw "Report already exists: $target"
}

$content = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
$content = $content.Replace('{{REPORT_TITLE}}', "Experiment ${number}: $Title")
$content = $content.Replace('YYYY-MM-DD', (Get-Date -Format 'yyyy-MM-dd'))
[System.IO.File]::WriteAllText($target, $content, [System.Text.UTF8Encoding]::new($false))

Write-Output "Created: $target"
