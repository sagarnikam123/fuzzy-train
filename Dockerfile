# Use the official, slim Python image for production
FROM python:3.12-slim

# Set environment variables for best practices
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Install faker so shipped images always produce enriched logs.
# (The script still runs standalone without it, via graceful fallback.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the log generator script
COPY fuzzy-train.py .

# Set entrypoint for easy override
ENTRYPOINT ["python", "fuzzy-train.py"]
