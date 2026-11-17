param([Parameter(Mandatory=$true)][string]$DocxPath,
      [Parameter(Mandatory=$true)][string]$PdfPath,
      [Parameter(Mandatory=$true)][string]$ReportPath)
$ErrorActionPreference = 'Stop'
$wordApp = $null
$wordDoc = $null
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordApp.AutomationSecurity = 3
    $wordDoc = $wordApp.Documents.Open([IO.Path]::GetFullPath($DocxPath), $false, $false, $false)
    $wordDoc.Fields.Update() | Out-Null
    $wordDoc.Repaginate()
    foreach ($toc in $wordDoc.TablesOfContents) { $toc.Update() }
    $wordDoc.Repaginate()
    foreach ($toc in $wordDoc.TablesOfContents) { $toc.UpdatePageNumbers() }
    foreach ($section in $wordDoc.Sections) {
        foreach ($footer in $section.Footers) { $footer.Range.Fields.Update() | Out-Null }
        foreach ($header in $section.Headers) { $header.Range.Fields.Update() | Out-Null }
    }
    $wordDoc.Repaginate()
    $wordDoc.Save()
    $wordDoc.ExportAsFixedFormat([IO.Path]::GetFullPath($PdfPath),17,$false,0,0,1,1,0,$true,$true,1,$true,$true,$false)
    $result = [ordered]@{pages=$wordDoc.ComputeStatistics(2); toc_count=$wordDoc.TablesOfContents.Count; headings=@()}
    foreach ($paragraph in $wordDoc.Paragraphs) {
        if ($paragraph.OutlineLevel -le 3) {
            $result.headings += [ordered]@{title=$paragraph.Range.Text.Trim(); page=$paragraph.Range.Information(3); level=$paragraph.OutlineLevel}
        }
    }
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath),($result | ConvertTo-Json -Depth 6),(New-Object Text.UTF8Encoding($false)))
} finally {
    # Cleanup must not mask an export error or fail after Word has already exited.
    if ($null -ne $wordDoc) { try { $wordDoc.Close($false) } catch {} }
    if ($null -ne $wordApp) { try { $wordApp.Quit() } catch {} }
    if ($null -ne $wordDoc) { try { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordDoc) | Out-Null } catch {} }
    if ($null -ne $wordApp) { try { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApp) | Out-Null } catch {} }
}
