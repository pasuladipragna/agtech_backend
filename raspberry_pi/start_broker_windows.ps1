# =========================================================
# AgriTech Rover - Windows MQTT Broker Quick-Start Script
# =========================================================
# This installs and starts Mosquitto MQTT broker using Docker.
# The Raspberry Pi will connect to this broker via your LAN IP.

# Step 1: Check if Docker is available
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "[ERROR] Docker is not installed. Please install Docker Desktop from https://www.docker.com/products/docker-desktop" -ForegroundColor Red
    Write-Host "        After installing, re-run this script." -ForegroundColor Yellow
    exit 1
}

Write-Host "[INFO] Starting Mosquitto MQTT broker on port 1883..." -ForegroundColor Cyan

# Stop any existing broker container
docker stop agtech-mqtt 2>$null; docker rm agtech-mqtt 2>$null

# Start Mosquitto in a container, allowing anonymous connections
docker run -d `
    --name agtech-mqtt `
    -p 1883:1883 `
    -v "$PSScriptRoot\mosquitto.conf:/mosquitto/config/mosquitto.conf" `
    eclipse-mosquitto

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] MQTT Broker started successfully!" -ForegroundColor Green
} else {
    # Fallback: try without config file
    docker run -d --name agtech-mqtt -p 1883:1883 eclipse-mosquitto mosquitto -p 1883 --allow-anonymous true
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  MQTT Broker is running on port 1883" -ForegroundColor Green  
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Find and display the LAN IP
$lanIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.*" } | Select-Object -First 1).IPAddress
Write-Host "[INFO] Your LAN IP address is: $lanIP" -ForegroundColor Yellow
Write-Host "[INFO] On the Raspberry Pi, run:" -ForegroundColor Yellow
Write-Host "         export ROVER_MQTT_BROKER=$lanIP" -ForegroundColor Cyan
Write-Host "         python3 pi_rover.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "[INFO] The backend server and Pi must be on the same WiFi network." -ForegroundColor Yellow
