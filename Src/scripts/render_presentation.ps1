param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$PdfPath
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $InputPath).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$pdfOutput = [System.IO.Path]::GetFullPath($PdfPath)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$existingPpt = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count
$powerPoint = New-Object -ComObject PowerPoint.Application
$presentation = $null
try {
    $presentation = $powerPoint.Presentations.Open($sourcePath, $true, $false, $false)
    $presentation.Export($outputPath, 'PNG', 1600, 900)
    $presentation.SaveAs($pdfOutput, 32)
    $risks = @()
    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasTextFrame -and $shape.TextFrame2.HasText) {
                if ($shape.TextFrame2.TextRange.BoundHeight -gt $shape.Height + 3) {
                    $risks += "Slide $($slide.SlideIndex): possible vertical overflow: $($shape.TextFrame2.TextRange.Text)"
                }
            }
        }
    }
    @{ slides = $presentation.Slides.Count; overflow_risks = $risks } | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $outputPath 'powerpoint-check.json') -Encoding utf8
    Write-Output "PowerPoint rendered $($presentation.Slides.Count) slides; possible overflow risks: $($risks.Count)."
} finally {
    if ($null -ne $presentation) { $presentation.Close() }
    if ($existingPpt -eq 0) { $powerPoint.Quit() }
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerPoint) | Out-Null
}
