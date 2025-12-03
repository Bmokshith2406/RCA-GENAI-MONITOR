param(
    [string]$InstallDir = "C:\opt\etw-genai-monitor"
)

Write-Output "Creating $InstallDir"
New-Item -Path $InstallDir -ItemType Directory -Force | Out-Null
Write-Output "Copy project files into $InstallDir manually."

Write-Output "Creating Python venv..."
python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\Activate.ps1"
pip install --upgrade pip
pip install -r "$InstallDir\requirements.txt"

Write-Output "Now build the ETW tracer:"
Write-Output "  cd $InstallDir\windows\EtwKernelTracer"
Write-Output "  dotnet restore"
Write-Output "  dotnet build -c Release"

