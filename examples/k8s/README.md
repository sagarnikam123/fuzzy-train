# Kubernetes Log Generator Manifests & Recipes

Ready-to-apply manifests for **Minikube**, **Kind**, **EKS**, **GKE**, and on-premise Kubernetes clusters.

Every manifest in this directory **automatically creates the `fuzzy-train` namespace** and deploys resources into it, ensuring your `default` namespace remains clean.

---

## 🚀 1. The All-in-One Observability Stack (Recommended)

Creates the `fuzzy-train` namespace and starts **4 concurrent workloads** (Multi-line Java, Structured JSON, HTTP access simulator, and Per-node DaemonSet with 3m error intervals):

```bash
kubectl apply -f examples/k8s/all-in-one-namespace-stack.yaml
```

### View Pods in Namespace
```bash
kubectl get pods -n fuzzy-train
```

### Stream Workload Logs
```bash
# 1. Multi-line stack traces (Java Spring Boot)
kubectl logs -n fuzzy-train -l app=fuzzy-train-multiline -f

# 2. Continuous JSON logs (10 lines/sec)
kubectl logs -n fuzzy-train -l app=fuzzy-train-json -f

# 3. HTTP access log simulator (status 200 & 500)
kubectl logs -n fuzzy-train -l app=fuzzy-train-http -f

# 4. Per-node DaemonSet logs (from all nodes)
kubectl logs -n fuzzy-train -l app=fuzzy-train-node-daemon -f --max-log-requests=10
```

---

## 2. Per-Node DaemonSets (Generate Logs on Every Node)

DaemonSets deploy a pod onto every node in your cluster (including control-plane/master nodes via tolerations). Perfect for evaluating node-level collectors (**Fluent Bit**, **Vector**, **Promtail**) tailing `/var/log/pods`.

### A. Per-Node Multi-Line Stack Trace DaemonSet (1m Error Interval)
Emits continuous Java logs and triggers a realistic **multi-line stack trace once every 1 minute (`-e 1m`)**:
```bash
kubectl apply -f examples/k8s/daemonset-per-node-multiline.yaml

# Tail logs:
kubectl logs -n fuzzy-train -l app=fuzzy-train-node-multiline -f --max-log-requests=10
```

> **Tip:** To change the error interval to 3 minutes, simply change `-e 1m` to `-e 3m` in the manifest args.

### B. Per-Node Structured JSON DaemonSet (1m Error Interval)
Generates structured JSON logs on every node with an `ERROR` level entry emitted every **1 minute (`-e 1m`)**:
```bash
kubectl apply -f examples/k8s/daemonset-per-node-json.yaml

# Tail logs:
kubectl logs -n fuzzy-train -l app=fuzzy-train-node-json -f --max-log-requests=10
```

---

## 3. Individual Deployments

### A. Multi-Line Stack Trace Deployment (1m Error Interval)
```bash
kubectl apply -f examples/k8s/multiline-stacktrace.yaml
kubectl logs -n fuzzy-train -l app=fuzzy-train-multiline -f
```

### B. Continuous Structured JSON Logs (10 lines/sec)
```bash
kubectl apply -f examples/k8s/infinite-json-stdout.yaml
kubectl logs -n fuzzy-train -l app=fuzzy-train-json -f
```

### C. HTTP Access Log & Alert Rule Simulator (1m Error Interval)
```bash
kubectl apply -f examples/k8s/http-access-simulator.yaml
kubectl logs -n fuzzy-train -l app=fuzzy-train-http -f
```

### D. High-Throughput Stress Test (2,000 lines/sec)
```bash
kubectl apply -f examples/k8s/high-throughput-load.yaml
kubectl logs -n fuzzy-train -l app=fuzzy-train-load -f
```

---

## 4. Advanced Observability Architectures

### A. Microservices Mesh (4 Services with 1m & 3m Error Intervals)
Creates the `fuzzy-train` namespace and starts 4 interconnected tiers (`frontend-gateway`, `auth-service`, `payment-service`, `order-service`):
```bash
kubectl apply -f examples/k8s/microservices-mesh.yaml

# Tail auth-service Python exceptions (1m error interval):
kubectl logs -n fuzzy-train -l app=auth-service -f

# Tail payment-service Java Spring Boot stack traces (3m error interval):
kubectl logs -n fuzzy-train -l app=payment-service -f
```

### B. Shared-Volume File Logging with Sidecar Tailer
Simulates legacy apps writing to rotated files (`/var/log/app/fuzzy-train.log`) with a sidecar tailing to stdout:
```bash
kubectl apply -f examples/k8s/sidecar-file-rotation.yaml
kubectl logs -n fuzzy-train -l app=fuzzy-train-sidecar-file -c log-tailer -f
```

### C. Periodic Batch Job Simulation (CronJob)
Runs every 5 minutes, generating 500 JSON log entries per batch run:
```bash
kubectl apply -f examples/k8s/cronjob-batch-simulation.yaml
```

### D. Fixed-Volume & Throughput Benchmark Job (1 GB / 10 GB at 0.5 MB/s or 1.0 MB/s)
Runs a Kubernetes `Job` that generates a precise total volume (e.g., 1 GB or 10 GB) at a fixed throughput rate (e.g. 0.5 MB/s or 1.0 MB/s) and terminates with exit code 0:
```bash
kubectl apply -f examples/k8s/volume-benchmark-job.yaml

# Stream logs while benchmark is running:
kubectl logs -n fuzzy-train -l job-name=fuzzy-train-volume-benchmark -f

# Check Job completion status:
kubectl get jobs -n fuzzy-train
```
> **Throughput Formula**:
> - **1.0 MB/sec** in JSON (~250 bytes/line): `-r 4000`
> - **0.5 MB/sec** in JSON (~250 bytes/line): `-r 2000`
> - **Stop at 10 GB**: edit manifest `args` to `--max-bytes 10gb` (takes ~2.8 hours at 1.0 MB/s or ~5.6 hours at 0.5 MB/s).

---

## ⚡ 5. One-Click Interactive Launcher Scripts

Both scripts verify `kubectl`, create the `fuzzy-train` namespace, and immediately begin streaming logs:

### Linux / macOS:
```bash
chmod +x examples/k8s/start-k8s-simulation.sh

# Run all-in-one stack:
./examples/k8s/start-k8s-simulation.sh all-in-one

# Run microservices mesh:
./examples/k8s/start-k8s-simulation.sh microservices

# Run per-node DaemonSet:
./examples/k8s/start-k8s-simulation.sh daemonset-multiline

# Clean up namespace and all resources:
./examples/k8s/start-k8s-simulation.sh clean
```

### Windows (PowerShell):
```powershell
# Run all-in-one stack:
.\examples\k8s\start-k8s-simulation.ps1 -Scenario all-in-one

# Run microservices mesh:
.\examples\k8s\start-k8s-simulation.ps1 -Scenario microservices

# Clean up:
.\examples\k8s\start-k8s-simulation.ps1 -Scenario clean
```

---

## 🧹 Clean Up

To delete everything in one command, simply delete the namespace:
```bash
kubectl delete namespace fuzzy-train
```
Or delete individual manifest files:
```bash
kubectl delete -f examples/k8s/all-in-one-namespace-stack.yaml
```

