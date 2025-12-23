# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Meshtastic MQTT filter service that processes Meshtastic mesh network messages from MQTT, filtering them based on the "Ok to MQTT" bitfield flag (firmware 2.5+), and forwarding only authorized messages to an output topic. The service can automatically decrypt encrypted packets using the default LongFast key or custom channel keys. It also supports exempting specific node IDs from filtering to always forward their messages regardless of the "Ok to MQTT" flag.

## Architecture

### Single-File Python Application

The entire application is contained in `mqtt_filter.py` (480 lines). It implements:

1. **MeshtasticMQTTFilter class** (mqtt_filter.py:32-353): Main service class that handles:
   - MQTT client setup and connection management
   - Message subscription and processing pipeline
   - Decryption of encrypted packets
   - Statistics tracking and reporting

2. **Key Components**:
   - **Message Processing Pipeline** (on_message, mqtt_filter.py:103-174):
     - Parse ServiceEnvelope protobuf from MQTT payload
     - Attempt decryption if encrypted (mqtt_filter.py:134-145)
     - Check "Ok to MQTT" bitfield flag (mqtt_filter.py:150)
     - Forward approved messages to output topic

   - **Decryption System** (_decrypt_packet, mqtt_filter.py:225-310):
     - Supports multiple encryption keys (default LongFast + custom keys)
     - Uses AES-CTR mode with packet_id + sender_id as 16-byte nonce
     - Key derivation via SHA256(base_key + channel_name) for named channels
     - LongFast channel uses base key directly without derivation

   - **Authorization Check** (_check_ok_to_mqtt, mqtt_filter.py:342-375):
     - First checks if node ID is in the exempt list (bypasses all filtering)
     - Validates packet has decoded (non-encrypted) data
     - Checks bit 0 (0x01) of bitfield in decoded data
     - Tracks rejection reasons and exemptions in statistics

3. **Statistics Tracking** (mqtt_filter.py:96-106, 204-227):
   - Total messages, forwarded, rejected
   - Decryption success/failure counts
   - Exempt node forward counts
   - Rejection reason breakdown (encrypted, no bitfield, bitfield disabled)
   - Periodic reporting every 10 messages or 30 seconds (with --show-stats)

### Meshtastic Protocol Details

- Uses protobuf definitions from `meshtastic.protobuf` package:
  - `mqtt_pb2.ServiceEnvelope`: MQTT message wrapper
  - `mesh_pb2.Data`: Decoded packet data
  - `portnums_pb2`, `telemetry_pb2`: Port number types
- Default LongFast key: `1PG7OiApB1nwvP+rz05pAQ==` (base64)
- Encryption: AES-128-CTR with nonce = packet_id (8 bytes LE) + from_node (8 bytes LE)

## Development Commands

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run with debug logging
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --debug

# Run with statistics
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --show-stats

# Run as daemon
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --daemon

# Run with custom encryption keys
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --channel-key "base64-encoded-key-1=" \
  --channel-key "base64-encoded-key-2="

# Disable default LongFast decryption
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --no-decrypt-default

# Exempt specific nodes from filtering
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --exempt-node "0x12345678" \
  --exempt-node "!a1b2c3d4"
```

### Docker Development

```bash
# Build image
docker build -t meshtastic-mqtt-filter .

# Run container
docker run --rm meshtastic-mqtt-filter \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY"

# Run with docker-compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

### Configuration

Docker Compose uses environment variables (configure in `.env` file):
- `MQTT_BROKER`: MQTT broker hostname
- `MQTT_PORT`: MQTT broker port (default: 1883)
- `MQTT_USERNAME`: MQTT username
- `MQTT_PASSWORD`: MQTT password
- `INPUT_TOPIC`: Input topic pattern (supports wildcards like `msh/US/NY/#`)
- `OUTPUT_TOPIC`: Output topic for filtered messages
- `SHOW_STATS`: Enable statistics output (default: true)
- `DEBUG`: Enable debug logging (default: false)
- `NO_DECRYPT_DEFAULT`: Disable default LongFast decryption (default: false)
- `EXEMPT_NODES`: Comma-separated list of exempt node IDs (e.g., `0x12345678,!a1b2c3d4`)
- `CHANNEL_KEYS`: Comma-separated list of base64 channel keys

The entrypoint script (entrypoint.sh) parses these environment variables and converts them to command-line arguments.

## Testing

No automated tests are currently implemented. To test manually:

1. Connect to a Meshtastic MQTT broker with test data
2. Run the filter with `--debug` to see detailed message processing
3. Verify filtered messages appear on output topic
4. Check statistics with `--show-stats` to validate filtering logic

## Dependencies

Core dependencies (requirements.txt):
- `paho-mqtt>=1.6.1`: MQTT client library
- `meshtastic>=2.2.0`: Meshtastic protobuf definitions
- `protobuf>=4.21.0`: Protocol buffers
- `cryptography>=41.0.0`: AES encryption for packet decryption

## Important Implementation Notes

### Decryption Key Derivation

The key derivation logic (mqtt_filter.py:199-223, 252-257) has special handling:
- LongFast channel and empty channel names use the base key directly
- Named channels (except "LongFast") derive keys via SHA256(base_key + channel_name_utf8)
- This matches Meshtastic firmware's key derivation algorithm

### Topic Mapping

When forwarding messages (mqtt_filter.py:157), the input topic prefix is replaced with the output topic prefix while preserving the rest of the topic structure. For example:
- Input: `msh/US/NY/2/e/LongFast/!a1b2c3d4`
- Input topic pattern: `msh/US/NY/#`
- Output topic: `filtered/msh/US/NY`
- Resulting topic: `filtered/msh/US/NY/2/e/LongFast/!a1b2c3d4`

### Daemon Mode

The daemon implementation (mqtt_filter.py:468-506) uses double-fork to properly detach from terminal and prevent zombies. It redirects stdout/stderr to /dev/null, so logging won't be visible unless redirected to a file.

### Node Exemption

The node exemption feature (mqtt_filter.py:55-79) allows bypassing the "Ok to MQTT" filtering for specific trusted node IDs:
- Supports multiple node ID formats: `0xABCD1234` (hex with prefix), `ABCD1234` (hex without prefix), `!abcd1234` (Meshtastic format), or decimal
- Node IDs are stored as a set for O(1) lookup performance
- Exempt nodes are checked first in `_check_ok_to_mqtt` before any other filtering logic
- Messages from exempt nodes are always forwarded, even if encrypted or missing the bitfield flag
- Exempt message counts are tracked separately in statistics
