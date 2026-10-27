# Opens the generated report in Microsoft Word (hidden), refreshes all fields so the
# contents table gets real page numbers, saves the .docx and exports a .pdf next to it.
param([string]$Docx = "$PSScriptRoot\..\BDA_Assignment2_Team16_Final.docx")
$ErrorActionPreference = 'Stop'
$path = (Resolve-Path $Docx).Path
$pdf = [System.IO.Path]::ChangeExtension($path, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($path, $false, $false, $false)
    $doc.Repaginate()
    [void]$doc.Fields.Update()
    foreach ($s in $doc.Sections) { foreach ($f in $s.Footers) { [void]$f.Range.Fields.Update() } }
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)     # 17 = wdExportFormatPDF
    Write-Host ("pages: {0}" -f $doc.ComputeStatistics(2))
    $doc.Close($false)
    Write-Host "saved $path"
    Write-Host "saved $pdf"
}
finally {
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
