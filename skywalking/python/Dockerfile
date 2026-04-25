FROM python:3.12-slim

LABEL maintainer="sagarnikam123"
LABEL description="Fake log generator with SkyWalking integration"

WORKDIR /app

# Install build dependencies for psutil (C extension), then clean up
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy application
COPY fuzzy-train-skywalking.py .

# Default environment variables
ENV SW_AGENT_NAME="skywalking-test::fuzzy-train-python"
ENV SW_AGENT_COLLECTOR_BACKEND_SERVICES="skywalking-satellite.skywalking.svc:11800"
ENV SW_AGENT_LOG_REPORTER_ACTIVE="true"

# Run the application
ENTRYPOINT ["python3", "-u", "fuzzy-train-skywalking.py"]
CMD ["--lines-per-second", "1"]
