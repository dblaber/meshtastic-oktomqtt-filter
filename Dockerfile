FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY mqtt_filter.py .
COPY entrypoint.sh .

# Create a non-root user, logs directory, and make entrypoint executable
RUN useradd -m -u 1000 meshtastic && \
    mkdir -p /app/logs && \
    chown -R meshtastic:meshtastic /app && \
    chmod +x /app/entrypoint.sh

USER meshtastic

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default arguments (can be overridden)
CMD []
