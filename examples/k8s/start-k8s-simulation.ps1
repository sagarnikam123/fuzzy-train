<#
.SYNOPSIS
    Creates the 'fuzzy-train' Kubernetes namespace and starts log generation workloads.
.DESCRIPTION
    Helper script for Minikube, Kind, Docker Desktop, EKS, and GKE.
.PARAMETER Scenario
    The simulation scenario: all-in-one (default), microservices, daemonset-multiline,
    daemonset-json, sidecar, adhoc, clean
.EXAMPLE
    .\start-k8s-simulation.ps1 -Scenario all-in-one
    .\start-k8s-simulation.ps1 -Scenario microservices
    .\start-k8s-simulation.ps1 -Scenario clean
#>

param(
    [ValidateSet("all-in-one", "microservices", "daemonset-multiline", "daemonset-json", "sidecar", "benchmark-1gb", "adhoc", "clean")]
    [string]$Scenario = "all-in-one"
)

$Namespace = "fuzzy-train"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Error "'kubectl' command not found in PATH."
    exit 1
}

if ($Scenario -eq "clean") {
    Write-Host "==> Deleting namespace '$Namespace' and all resources..." -ForegroundColor Yellow
    kubectl delete namespace $Namespace --ignore-not-found=true
    Write-Host "Clean up completed." -ForegroundColor Green
    exit 0
}

# 1. Ensure namespace exists
Write-Host "==> Ensuring namespace '$Namespace' exists..." -ForegroundColor Cyan
kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -

switch ($Scenario) {
    "all-in-one" {
        Write-Host "==> Deploying All-in-One Observability Stack..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\all-in-one-namespace-stack.yaml"
        Write-Host "==> Streaming multi-line logs (Ctrl+C to stop stream)..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=fuzzy-train-multiline -f
    }
    "microservices" {
        Write-Host "==> Deploying Microservices Mesh..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\microservices-mesh.yaml"
        Write-Host "==> Streaming auth-service logs with multi-line exceptions (Ctrl+C to stop)..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=auth-service -f
    }
    "daemonset-multiline" {
        Write-Host "==> Deploying Per-Node Multi-Line DaemonSet..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\daemonset-per-node-multiline.yaml"
        Write-Host "==> Streaming DaemonSet logs across all nodes (Ctrl+C to stop)..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=fuzzy-train-node-multiline -f --max-log-requests=10
    }
    "daemonset-json" {
        Write-Host "==> Deploying Per-Node JSON DaemonSet..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\daemonset-per-node-json.yaml"
        Write-Host "==> Streaming JSON DaemonSet logs across all nodes (Ctrl+C to stop)..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=fuzzy-train-node-json -f --max-log-requests=10
    }
    "sidecar" {
        Write-Host "==> Deploying Sidecar File Rotation Workload..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\sidecar-file-rotation.yaml"
        Write-Host "==> Streaming sidecar tailer output (Ctrl+C to stop)..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=fuzzy-train-sidecar-file -c log-tailer -f
    }
    "adhoc" {
        Write-Host "==> Launching ad-hoc fuzzy-train pod in '$Namespace'..." -ForegroundColor Cyan
        kubectl run fuzzy-train-adhoc -n $Namespace `
            --image=sagarnikam123/fuzzy-train:latest `
            --restart=Always `
            --labels="app=fuzzy-train-adhoc" `
            -- --log-format json --lines-per-second 10 --error-interval 1m --time-zone utc
        Write-Host "==> Streaming ad-hoc pod logs..." -ForegroundColor Green
        kubectl logs -n $Namespace pod/fuzzy-train-adhoc -f
    }
    "benchmark-1gb" {
        Write-Host "==> Deploying 1GB Volume Benchmark Job (1.0 MB/sec)..." -ForegroundColor Cyan
        kubectl apply -f "$ScriptDir\volume-benchmark-job.yaml"
        Write-Host "==> Streaming Job logs until 1GB is reached..." -ForegroundColor Green
        kubectl logs -n $Namespace -l app=fuzzy-train-volume-benchmark -f
    }
}
