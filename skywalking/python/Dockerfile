FROM python:3.12-slim

LABEL maintainer="sagarnikam123"
LABEL description="Fake log generator with SkyWalking integration"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY fuzzy-train-skywalking.py .

# Default environment variables
ENV SW_AGENT_NAME="skywalking-test::fuzzy-train-python"
ENV SW_AGENT_COLLECTOR_BACKEND_SERVICES="skywalking-satellite.skywalking.svc:11800"
ENV SW_AGENT_LOG_REPORTER_ACTIVE="true"

# Run the application
ENTRYPOINT ["python3", "-u", "fuzzy-train-skywalking.py"]
CMD ["--lines-per-second", "1"]
