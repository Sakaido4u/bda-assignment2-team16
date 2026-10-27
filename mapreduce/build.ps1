# Builds mapreduce\target\ghcn-mapreduce.jar inside a Maven container (no Maven/JDK needed on Windows).
# The Maven repository is cached in the named volume "bda16-m2" so rebuilds are fast.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
docker run --rm -v "${PWD}:/build" -v bda16-m2:/root/.m2 -w /build maven:3.9.9-eclipse-temurin-8 mvn -q -B package -DskipTests
if ($LASTEXITCODE -ne 0) { Write-Host "Maven build failed" -ForegroundColor Red; exit 1 }
Get-Item target\ghcn-mapreduce.jar | Format-Table Name, Length, LastWriteTime
