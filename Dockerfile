FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY mqtt_filter.py .

# Create a non-root user
RUN useradd -m -u 1000 meshtastic && \
    chown -R meshtastic:meshtastic /app

USER meshtastic

# Set entrypoint
ENTRYPOINT ["python", "mqtt_filter.py"]

# Default arguments (can be overridden)
CMD ["--help"]
