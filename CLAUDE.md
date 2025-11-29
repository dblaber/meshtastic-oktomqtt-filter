# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meshtastic MQTT Filter - A single-file Python application that filters Meshtastic MQTT messages based on the "Ok to MQTT" user preference flag (bitfield bit 0x01). The filter decrypts encrypted packets and only forwards messages from users who have explicitly enabled MQTT uplink in their Meshtastic firmware (v2.5+).

## Development Commands

### Running the filter
```bash
# Direct execution with test broker
python mqtt_filter.py --broker mqtt.patinhas.da4.org --username meshdev --password large4cats \
  --input-topic "msh/US/NY/#" --output-topic "filtered/msh/US/NY" --show-stats

# With debug logging
python mqtt_filter.py --broker mqtt.example.com --input-topic "msh/#" \
  --output-topic "filtered/mesh" --debug

# With rejection logging for troubleshooting
python mqtt_filter.py --broker mqtt.example.com --input-topic "msh/#" \
  --output-topic "filtered/mesh" --reject-log rejected_packets.log --show-stats

# As daemon (background process, Linux only)
python mqtt_filter.py --broker mqtt.example.com --input-topic "msh/#" \
  --output-topic "filtered/mesh" --daemon
```

### Docker deployment
```bash
# Build and run with Docker Compose (recommended)
docker compose up -d

# View logs
docker compose logs -f

# Stop service
docker compose down

# Rebuild after code changes
docker compose down
docker compose build --no-cache
docker compose up -d

# Build Docker image manually
docker build -t meshtastic-mqtt-filter .
```

### Dependencies
```bash
# Install dependencies
pip install -r requirements.txt

# Dependencies: paho-mqtt, meshtastic, protobuf, cryptography
```

## Architecture

### Single-file application structure
The entire application is in `mqtt_filter.py` with the following key components:

**MeshtasticMQTTFilter class**:
- MQTT client wrapper with encryption support
- Subscribes to input topic (supports wildcards like `msh/US/NY/#`)
- Decrypts packets, checks bitfield flags, forwards approved messages
- Tracks statistics (forwarded, rejected, decryption success/failure)
- Optional rejection logging to file for troubleshooting

**Message processing flow** (on_message method):
1. Parse ServiceEnvelope protobuf from MQTT payload
2. If encrypted: attempt decryption with available keys
3. Check bitfield bit 0x01 for "Ok to MQTT" approval
4. Forward approved messages to output topic (dynamic topic mapping)
5. Track statistics and log results

### Encryption implementation

**Critical implementation details**:
- Uses `cryptography` library (NOT pycryptodome)
- Algorithm: AES-128-CTR (or AES-256-CTR for derived keys)
- Nonce: `packet_id (8 bytes LE) + sender_id (8 bytes LE)` = 16 bytes
- Default LongFast key: `1PG7OiApB1nwvP+rz05pAQ==` (16 bytes, base64)

**Key derivation** (`_derive_key` method):
- Preset channels (LongFast): Use base key directly, NO derivation
- Custom named channels: `SHA256(base_key + channel_name_bytes)` → 32 bytes
- Channel name from `envelope.channel_id`

**Important**: LongFast is a modem preset name, NOT a custom channel. Never apply SHA256 derivation to "LongFast" - use the 16-byte base key as-is.

### Bitfield filtering

**"Ok to MQTT" detection** (`_check_ok_to_mqtt` method):
1. Check if packet has decoded data (not still encrypted)
2. Check if `packet.decoded.bitfield` field exists
3. Test bit 0: `packet.decoded.bitfield & 0x01`
4. Reject if bit not set or bitfield missing (older firmware)

**Rejection categories tracked**:
- `rejected_encrypted`: Still encrypted after decryption attempts
- `rejected_no_bitfield`: No bitfield field (firmware < 2.5)
- `rejected_bitfield_disabled`: Bitfield exists but bit 0x01 not set

**Rejection logging** (`_log_rejected_packet` method):
- Optional detailed logging of rejected packets to file (enabled with `--reject-log`)
- Logs rejection reason, node IDs, MQTT topic, channel info
- Extracts text from TEXT_MESSAGE_APP packets
- Extracts telemetry from TELEMETRY_APP packets
- Shows bitfield hex values for debugging
- Uses separate logger instance to avoid polluting main logs
- Pipe-separated format for easy parsing

### Python keyword handling

The protobuf field `from` is a Python keyword. Always access using:
```python
from_id = getattr(packet, 'from', 0)
```
Never use `packet.from` directly.

### Topic mapping

Input topics support wildcards (`msh/US/NY/#`). Output topics are dynamically generated:
```python
output_topic = msg.topic.replace(
    self.input_topic.rstrip('/#'),
    self.output_topic.rstrip('/#'),
    1
)
```

Example: Input `msh/US/NY/2/e/LongFast/!abc123` → Output `filtered/msh/US/NY/2/e/LongFast/!abc123`

## Configuration

### Environment variables (Docker)
Defined in `docker-compose.yml` with defaults:
- `MQTT_BROKER`: Broker hostname
- `MQTT_PORT`: Broker port (default 1883)
- `MQTT_USERNAME`, `MQTT_PASSWORD`: Credentials
- `INPUT_TOPIC`, `OUTPUT_TOPIC`: Topic paths

Override via `.env` file or `docker-compose.override.yml`.

### Command-line arguments
See `--help` for full list. Key flags:
- `--debug`: Enable debug logging
- `--show-stats`: Print stats every 30 seconds
- `--daemon`: Run as background daemon (Linux only)
- `--no-decrypt-default`: Disable default LongFast key
- `--channel-key`: Add custom encryption key (can repeat)
- `--reject-log`: Log file path for detailed rejection logging (helps troubleshoot filtering issues)

## Reference implementation

Decryption logic based on [malla project](https://github.com/zenitraM/malla) at `/tmp/malla/src/malla/utils/decryption.py`. When modifying encryption code, reference this implementation for correctness.

## License

MIT License - see LICENSE file.
