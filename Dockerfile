# Use the official, slim Python image for production
FROM python:3.12-slim

# Set environment variables for best practices
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy only the script (no requirements.txt needed if no dependencies)
COPY fuzzy-train.py .

# Set entrypoint for easy override
ENTRYPOINT ["python", "fuzzy-train.py"]
