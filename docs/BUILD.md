# Building & Testing the Docker Image

This guide covers building the `fuzzy-train` container image (single-platform and
multi-platform), and testing it locally.

The image installs [`faker`](https://pypi.org/project/Faker/) (see [`requirements.txt`](../requirements.txt))
so shipped images always produce enriched logs; the script still falls back to its
built-in generator if faker is ever absent.

## Prerequisites

- [Docker](https://www.docker.com/) with [Buildx](https://docs.docker.com/build/buildx/)
  (bundled with Docker Desktop and recent Docker Engine).
- For pushing images: a Docker Hub account and `docker login`.

Check Buildx is available:

```bash
docker buildx version
docker buildx ls
```

## Single-platform build (local)

Builds for your current architecture and loads the image into the local Docker store:

```bash
docker build -t fuzzy-train:local .
```

## Multi-platform build (amd64 + arm64)

A multi-platform image targets both `linux/amd64` (e.g. EKS / most cloud) and
`linux/arm64` (e.g. Apple Silicon). Buildx builds each platform and assembles a
single multi-arch manifest.

> **Important:** a multi-platform result cannot be kept in the local image store.
> Buildx must either `--push` it to a registry or `--load` a single platform.

### 1. Create a Buildx builder (one time)

The default `docker` driver cannot emit a multi-arch manifest — use the
`docker-container` driver:

```bash
docker buildx create --name multiarch --driver docker-container --use
docker buildx inspect --bootstrap
```

(If a `multiarch` builder already exists, select it with `docker buildx use multiarch`.)

### 2. Build and push both platforms

```bash
docker login

docker buildx build --builder multiarch \
  --platform linux/amd64,linux/arm64 \
  -t sagarnikam123/fuzzy-train:2.3.0 \
  -t sagarnikam123/fuzzy-train:latest \
  --push .
```

### 3. Build without pushing (verify both arches compile)

Useful in CI or before you have registry access — the result stays in the build
cache only:

```bash
docker buildx build --builder multiarch \
  --platform linux/amd64,linux/arm64 \
  -t fuzzy-train:multiarch-test .
```

You will see a warning that the build result remains in the build cache; that is
expected when neither `--push` nor `--load` is given.

### 4. Load a single platform locally for testing

To run a specific arch on your machine (Apple Silicon = `arm64`):

```bash
docker buildx build --builder multiarch \
  --platform linux/arm64 \
  -t fuzzy-train:local --load .
```

## Testing the container

```bash
# Version
docker run --rm fuzzy-train:local --version

# Default enriched JSON logs to stdout (Ctrl-C to stop)
docker run --rm fuzzy-train:local

# Bounded run: exactly 5 lines then exit
docker run --rm fuzzy-train:local --count 5

# Bounded run: ~1 MB then exit, written to a mounted volume
docker run --rm -v "$(pwd)/logs":/logs fuzzy-train:local \
  --max-bytes 1048576 --file /logs/app.log

# Gzip + split into 4-line parts (app.log.gz, app1.log.gz, app2.log.gz)
docker run --rm -v "$(pwd)/logs":/logs fuzzy-train:local \
  --count 10 --split-by 4 --file /logs/app.log.gz

# Fake-time stepping: 3 logs, timestamps 1 minute apart
docker run --rm fuzzy-train:local --count 3 --time-step 1m --time-zone UTC

# Verify a pushed multi-arch image (pulls the arch matching your host)
docker run --rm sagarnikam123/fuzzy-train:2.3.0 --version
```

Read gzip output on the host:

```bash
gzip -dc logs/app.log.gz | head
```

## Running the test suite

The pytest suite in [`tests/`](../tests/) covers each CLI argument and the combinations that
interact (bounded runs, gzip, split, faker fallback, etc.).

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run the full suite (quiet)
pytest tests/ -q

# Verbose: show each test name and result
pytest tests/ -v

# Run a subset by keyword (e.g. only split-related tests)
pytest tests/ -k split

# Run a single test
pytest tests/test_fuzzy_train.py::test_cli_count_exact_lines

# Stop at the first failure, show local variables
pytest tests/ -x -l
```

A green run ends with a line like `81 passed in ~8s`. Any failure prints the
failing test name, the assertion, and a diff of expected vs actual so you can
pinpoint the regression.

## Cleanup

```bash
# Remove local test images
docker rmi fuzzy-train:local fuzzy-train:multiarch-test 2>/dev/null

# Remove the builder (optional)
docker buildx rm multiarch
```
