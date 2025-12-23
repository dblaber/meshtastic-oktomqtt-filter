#!/bin/bash
set -e

# Build the command arguments
ARGS=()

# Add broker settings
if [ -n "$MQTT_BROKER" ]; then
    ARGS+=("--broker" "$MQTT_BROKER")
fi

if [ -n "$MQTT_PORT" ]; then
    ARGS+=("--port" "$MQTT_PORT")
fi

if [ -n "$MQTT_USERNAME" ]; then
    ARGS+=("--username" "$MQTT_USERNAME")
fi

if [ -n "$MQTT_PASSWORD" ]; then
    ARGS+=("--password" "$MQTT_PASSWORD")
fi

# Add topic settings
if [ -n "$INPUT_TOPIC" ]; then
    ARGS+=("--input-topic" "$INPUT_TOPIC")
fi

if [ -n "$OUTPUT_TOPIC" ]; then
    ARGS+=("--output-topic" "$OUTPUT_TOPIC")
fi

# Add optional settings
if [ "$SHOW_STATS" = "true" ]; then
    ARGS+=("--show-stats")
fi

if [ "$DEBUG" = "true" ]; then
    ARGS+=("--debug")
fi

if [ "$NO_DECRYPT_DEFAULT" = "true" ]; then
    ARGS+=("--no-decrypt-default")
fi

if [ "$ALLOW_NO_BITFIELD" = "true" ]; then
    ARGS+=("--allow-no-bitfield")
fi

if [ -n "$REJECT_LOG_FILE" ]; then
    ARGS+=("--reject-log" "$REJECT_LOG_FILE")
fi

# Parse comma-separated exempt nodes
if [ -n "$EXEMPT_NODES" ]; then
    IFS=',' read -ra NODES <<< "$EXEMPT_NODES"
    for node in "${NODES[@]}"; do
        # Trim whitespace
        node=$(echo "$node" | xargs)
        if [ -n "$node" ]; then
            ARGS+=("--exempt-node" "$node")
        fi
    done
fi

# Parse comma-separated channel keys
if [ -n "$CHANNEL_KEYS" ]; then
    IFS=',' read -ra KEYS <<< "$CHANNEL_KEYS"
    for key in "${KEYS[@]}"; do
        # Trim whitespace
        key=$(echo "$key" | xargs)
        if [ -n "$key" ]; then
            ARGS+=("--channel-key" "$key")
        fi
    done
fi

# If arguments were passed to the container, use those instead
if [ $# -gt 0 ]; then
    exec python mqtt_filter.py "$@"
else
    # Otherwise use the arguments we built from environment variables
    exec python mqtt_filter.py "${ARGS[@]}"
fi
