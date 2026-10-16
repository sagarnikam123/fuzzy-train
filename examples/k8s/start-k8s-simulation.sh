#!/usr/bin/env bash
# ==============================================================================
# fuzzy-train Kubernetes Simulation Launcher
#
# Creates the "fuzzy-train" namespace and starts real-time log generation.
#
# Usage:
#   ./start-k8s-simulation.sh [scenario]
#
# Scenarios:
#   all-in-one          : Complete 4-workload stack (multiline, JSON, HTTP, DaemonSet) [default]
#   microservices       : 4 distinct services (frontend, auth, payment, order)
#   daemonset-multiline : Per-node multi-line Java stack trace generator (1m error)
#   daemonset-json      : Per-node structured JSON generator (1m error)
#   sidecar             : Shared volume file logging with sidecar tailer
#   adhoc               : Runs a standalone ad-hoc pod with custom parameters
#   clean               : Deletes the "fuzzy-train" namespace and all resources
# ==============================================================================

set -euo pipefail

NAMESPACE="fuzzy-train"
SCENARIO="${1:-all-in-one}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify kubectl exists
if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: 'kubectl' command not found in PATH." >&2
  exit 1
fi

if [ "$SCENARIO" = "clean" ]; then
  echo "Deleting namespace '$NAMESPACE' and all resources..."
  kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
  echo "Clean up completed."
  exit 0
fi

# 1. Create the namespace if it doesn't already exist
echo "==> Ensuring namespace '$NAMESPACE' exists..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# 2. Deploy selected scenario
case "$SCENARIO" in
  all-in-one)
    echo "==> Deploying All-in-One Observability Stack..."
    kubectl apply -f "${SCRIPT_DIR}/all-in-one-namespace-stack.yaml"
    echo "==> Waiting for pods to become ready..."
    kubectl wait --for=condition=Ready pods --all -n "$NAMESPACE" --timeout=60s || true
    echo "==> Streaming multi-line logs (Ctrl+C to stop stream)..."
    kubectl logs -n "$NAMESPACE" -l app=fuzzy-train-multiline -f
    ;;

  microservices)
    echo "==> Deploying Microservices Mesh..."
    kubectl apply -f "${SCRIPT_DIR}/microservices-mesh.yaml"
    echo "==> Waiting for pods to become ready..."
    kubectl wait --for=condition=Ready pods --all -n "$NAMESPACE" --timeout=60s || true
    echo "==> Streaming auth-service logs with multi-line exceptions (Ctrl+C to stop)..."
    kubectl logs -n "$NAMESPACE" -l app=auth-service -f
    ;;

  daemonset-multiline)
    echo "==> Deploying Per-Node Multi-Line DaemonSet..."
    kubectl apply -f "${SCRIPT_DIR}/daemonset-per-node-multiline.yaml"
    echo "==> Streaming DaemonSet logs across all nodes (Ctrl+C to stop)..."
    kubectl logs -n "$NAMESPACE" -l app=fuzzy-train-node-multiline -f --max-log-requests=10
    ;;

  daemonset-json)
    echo "==> Deploying Per-Node JSON DaemonSet..."
    kubectl apply -f "${SCRIPT_DIR}/daemonset-per-node-json.yaml"
    echo "==> Streaming JSON DaemonSet logs across all nodes (Ctrl+C to stop)..."
    kubectl logs -n "$NAMESPACE" -l app=fuzzy-train-node-json -f --max-log-requests=10
    ;;

  sidecar)
    echo "==> Deploying Sidecar File Rotation Workload..."
    kubectl apply -f "${SCRIPT_DIR}/sidecar-file-rotation.yaml"
    echo "==> Waiting for pod to become ready..."
    kubectl wait --for=condition=Ready pods -l app=fuzzy-train-sidecar-file -n "$NAMESPACE" --timeout=60s || true
    echo "==> Streaming sidecar tailer output (Ctrl+C to stop)..."
    kubectl logs -n "$NAMESPACE" -l app=fuzzy-train-sidecar-file -c log-tailer -f
    ;;

  adhoc)
    echo "==> Launching ad-hoc fuzzy-train pod in '$NAMESPACE'..."
    kubectl run fuzzy-train-adhoc -n "$NAMESPACE" \
      --image=sagarnikam123/fuzzy-train:latest \
      --restart=Always \
      --labels="app=fuzzy-train-adhoc" \
      -- --log-format json --lines-per-second 10 --error-interval 1m --time-zone utc
    echo "==> Waiting for pod..."
    kubectl wait --for=condition=Ready pod/fuzzy-train-adhoc -n "$NAMESPACE" --timeout=60s || true
    echo "==> Streaming ad-hoc pod logs..."
    kubectl logs -n "$NAMESPACE" pod/fuzzy-train-adhoc -f
    ;;

  benchmark-1gb)
    echo "==> Deploying 1GB Volume Benchmark Job (1.0 MB/sec)..."
    kubectl apply -f "${SCRIPT_DIR}/volume-benchmark-job.yaml"
    echo "==> Streaming Job logs until 1GB is reached (Ctrl+C to stop)..."
    kubectl wait --for=condition=Ready pods -l app=fuzzy-train-volume-benchmark -n "$NAMESPACE" --timeout=60s || true
    kubectl logs -n "$NAMESPACE" -l app=fuzzy-train-volume-benchmark -f
    ;;

  *)
    echo "Unknown scenario: $SCENARIO"
    echo "Available scenarios: all-in-one, microservices, daemonset-multiline, daemonset-json, sidecar, benchmark-1gb, adhoc, clean"
    exit 1
    ;;
esac
