Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "[clean] Done." -ForegroundColor Green
