# Release Notes

## v1.0.0 - Initial Release

### Overview

First stable release of the Meshtastic MQTT Filter - a tool that filters Meshtastic MQTT messages based on the "Ok to MQTT" user preference, ensuring only authorized messages are forwarded to output topics.

### Features

#### Core Functionality
- **Message Filtering**: Filters messages based on the "Ok to MQTT" bitfield flag (bit 0x01)
  - Requires Meshtastic firmware 2.5+ for bitfield support
  - Respects user privacy preferences by only forwarding approved messages
  - Rejects messages from users who have disabled MQTT uplink

#### Encryption Support
- **Automatic Decryption**: Decrypts encrypted Meshtastic packets before filtering
  - Default LongFast key support (`1PG7OiApB1nwvP+rz05pAQ==`)
  - Custom channel key support via `--channel-key` argument
  - Proper key derivation for custom-named channels
  - AES-128-CTR decryption with correct nonce construction

#### Statistics & Monitoring
- **Real-time Statistics**: Track filter performance and message processing
  - Total messages processed
  - Forwarded vs rejected counts with percentages
  - Decryption success/failure counts
  - Detailed rejection reasons (encrypted, no bitfield, bitfield disabled)
  - Periodic statistics reporting (every 10 messages or 30 seconds with `--show-stats`)

#### Deployment Options
- **Multiple Deployment Methods**:
  - **Docker Compose**: Easy containerized deployment with environment variable configuration
  - **Daemon Mode**: Run as background service on Linux with `--daemon` flag
  - **Command Line**: Direct execution for testing and development

#### Flexible Configuration
- **MQTT Topic Wildcards**: Support for wildcard subscriptions (`msh/US/NY/#`)
- **Dynamic Topic Mapping**: Automatically maps input topics to output topics
- **Credential Support**: Username/password authentication for MQTT brokers
- **Debug Logging**: Comprehensive debug output with `--debug` flag

### Usage Examples

#### Docker Compose Deployment
```bash
# Edit .env file with your settings
docker-compose up -d
```

#### Command Line with Statistics
```bash
python mqtt_filter.py \
  --broker mqtt.patinhas.da4.org \
  --username meshdev \
  --password large4cats \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --show-stats
```

#### Daemon Mode
```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/#" \
  --output-topic "filtered/mesh" \
  --daemon
```

### Installation

#### Docker (Recommended)
```bash
docker-compose up -d
```

#### Python
```bash
pip install -r requirements.txt
python mqtt_filter.py --help
```

### Requirements

- Python 3.11+
- paho-mqtt >= 1.6.1
- meshtastic >= 2.2.0
- protobuf >= 4.21.0
- cryptography >= 41.0.0

### Technical Details

#### Encryption Implementation
- Uses `cryptography` library for AES-128-CTR decryption
- Nonce construction: `packet_id (8 bytes LE) + sender_id (8 bytes LE)`
- Key derivation: SHA256(base_key + channel_name) for custom channels
- LongFast preset channels use base key directly (no derivation)

#### Message Processing
1. Parse Meshtastic ServiceEnvelope protobuf
2. Attempt decryption if packet is encrypted
3. Check bitfield flag (bit 0x01) for "Ok to MQTT" approval
4. Forward approved messages to output topic
5. Track statistics and log results

### Known Limitations

- Bitfield checking requires Meshtastic firmware 2.5 or newer
  - Older firmware messages without bitfield are rejected by default
- Daemon mode only supported on Linux/Unix systems
- Statistics are in-memory only (reset on restart)

### License

MIT License - See [LICENSE](LICENSE) for details

### Contributing

Contributions welcome! Please open issues or pull requests on GitHub.

### Acknowledgments

- Meshtastic project for the excellent mesh networking platform
- [malla](https://github.com/zenitraM/malla) project for decryption implementation reference
