# PhiDiscovery Pilot Zero. Entirely local by default; no API requests.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "PhiDiscovery | Running offline verification tests" -ForegroundColor Cyan
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed; no report generated" }
Write-Host "Running cannabinoid evidence pilot (SYNTHETIC FIXTURE)" -ForegroundColor Cyan
python -m phidiscovery run examples/cannabinoid-pilot.json --out out
if ($LASTEXITCODE -ne 0) { throw "Evidence analysis failed" }
python -m phidiscovery check examples/cannabinoid-pilot.json out/report.json
if ($LASTEXITCODE -ne 0) { throw "Receipt verification failed" }
Write-Host "Comparing synthetic MGF to synthetic reference spectra" -ForegroundColor Cyan
python -m phidiscovery spectra examples/demo-spectra.mgf --library examples/demo-reference-spectra.json --out out/spectra-results.json
if ($LASTEXITCODE -ne 0) { throw "Spectrum analysis failed" }
Write-Host "Complete. Opening out/report.html (synthetic teaching dataset)." -ForegroundColor Green
Start-Process (Resolve-Path "out/report.html")
