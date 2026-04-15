param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $projectRoot "data"
$sourceRootItem = Get-ChildItem -LiteralPath $dataRoot -Directory |
    Where-Object { $_.Name -like "DNA*" } |
    Select-Object -First 1
$sourceRoot = if ($sourceRootItem) { $sourceRootItem.FullName } else { $null }
$catalogPath = Join-Path $dataRoot "file_catalog.csv"

function Get-Marker {
    param([string]$RelativePath)

    if ($RelativePath -match "\\COI\\") {
        return "COI"
    }
    if ($RelativePath -match "\\gPlant\\") {
        return "gPlant"
    }
    return "general"
}

function Get-QiimeGroup {
    param([string]$RelativePath)

    if ($RelativePath -match "\\Repset\\") {
        return "Repset"
    }
    if ($RelativePath -match "\\Sequences\\") {
        return "Sequences"
    }
    if ($RelativePath -match "\\Table\\") {
        return "Table"
    }
    return "Other"
}

function Get-Category {
    param(
        [System.IO.FileInfo]$File,
        [string]$RelativePath
    )

    $ext = $File.Extension.ToLowerInvariant()
    $marker = Get-Marker $RelativePath

    switch ($ext) {
        ".docx" { return @("01_knowledge_docs", "thesis_and_notes") }
        ".pdf" { return @("01_knowledge_docs", "thesis_and_notes") }
        ".xlsx" { return @("02_tables", $marker) }
        ".tsv" { return @("02_tables", $marker) }
        ".csv" { return @("02_tables", $marker) }
        ".html" { return @("03_reports", $marker) }
        ".htm" { return @("03_reports", $marker) }
        ".txt" { return @("03_reports", $marker) }
        ".fasta" { return @("04_sequences_fasta", $marker) }
        ".fa" { return @("04_sequences_fasta", $marker) }
        ".gz" { return @("05_raw_reads_fastq", $marker) }
        ".qza" { return @("06_qiime2_artifacts", $marker, (Get-QiimeGroup $RelativePath)) }
        ".qzv" { return @("06_qiime2_artifacts", $marker, (Get-QiimeGroup $RelativePath)) }
        ".png" { return @("07_images", $marker) }
        ".jpg" { return @("07_images", $marker) }
        ".jpeg" { return @("07_images", $marker) }
        default { return @("99_other", $marker) }
    }
}

function Get-UniqueDestination {
    param(
        [string]$Directory,
        [string]$FileName
    )

    $candidate = Join-Path $Directory $FileName
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }

    $base = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    $ext = [System.IO.Path]::GetExtension($FileName)
    $index = 2

    while ($true) {
        $candidate = Join-Path $Directory "$base-$index$ext"
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
        $index += 1
    }
}

if (-not $sourceRoot -or -not (Test-Path -LiteralPath $sourceRoot)) {
    Write-Host "Source folder already organized or not found:" $sourceRoot
    exit 0
}

$moves = New-Object System.Collections.Generic.List[object]
$files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File

foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($sourceRoot.Length + 1)
    $categoryParts = Get-Category -File $file -RelativePath $relativePath
    $destinationDir = $dataRoot
    foreach ($part in $categoryParts) {
        $destinationDir = Join-Path $destinationDir $part
    }
    $destination = Get-UniqueDestination -Directory $destinationDir -FileName $file.Name

    $moves.Add([PSCustomObject]@{
        Source = $file.FullName
        OriginalRelativePath = (Join-Path (Split-Path -Leaf $sourceRoot) $relativePath)
        Category = $categoryParts[0]
        Marker = Get-Marker $relativePath
        Extension = $file.Extension.ToLowerInvariant()
        SizeBytes = $file.Length
        Destination = $destination
        NewRelativePath = $destination.Substring($dataRoot.Length + 1)
    })
}

if ($DryRun) {
    $moves |
        Group-Object Category |
        Sort-Object Name |
        Select-Object Name, Count |
        Format-Table -AutoSize
    exit 0
}

foreach ($move in $moves) {
    $destinationDir = Split-Path -Parent $move.Destination
    New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
    try {
        Move-Item -LiteralPath $move.Source -Destination $move.Destination -ErrorAction Stop
        $move | Add-Member -NotePropertyName Status -NotePropertyValue "moved" -Force
        $move | Add-Member -NotePropertyName Error -NotePropertyValue "" -Force
    }
    catch {
        $move | Add-Member -NotePropertyName Status -NotePropertyValue "failed" -Force
        $move | Add-Member -NotePropertyName Error -NotePropertyValue $_.Exception.Message -Force
        Write-Warning ("Skipped locked or unavailable file: " + $move.Source)
    }
}

$catalogRows = $moves |
    Select-Object OriginalRelativePath, NewRelativePath, Category, Marker, Extension, SizeBytes, Status, Error

if (Test-Path -LiteralPath $catalogPath) {
    $catalogRows | Export-Csv -LiteralPath $catalogPath -NoTypeInformation -Encoding UTF8 -Append
}
else {
    $catalogRows | Export-Csv -LiteralPath $catalogPath -NoTypeInformation -Encoding UTF8
}

Write-Host "Moved files:" (@($moves | Where-Object { $_.Status -eq "moved" }).Count)
Write-Host "Failed files:" (@($moves | Where-Object { $_.Status -eq "failed" }).Count)
Write-Host "Catalog:" $catalogPath
