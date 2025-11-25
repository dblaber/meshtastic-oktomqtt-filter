# Meshtastic MQTT Filter

Filters Meshtastic MQTT messages based on the "Ok to MQTT" flag, forwarding only authorized messages to an output topic. Supports automatic decryption of encrypted packets using the default LongFast key or custom channel keys.

## Features

- Filters messages based on the "Ok to MQTT" bitfield flag (firmware 2.5+)
- Automatic decryption of encrypted packets with default LongFast key
- Support for custom channel encryption keys
- Statistics tracking and periodic reporting
- Daemon mode for background operation
- Docker support for easy deployment

## Installation

### Using Docker Compose (Recommended)

1. Create a `.env` file to override default settings (optional):

```bash
MQTT_BROKER=mqtt.patinhas.da4.org
MQTT_PORT=1883
MQTT_USERNAME=meshdev
MQTT_PASSWORD=large4cats
INPUT_TOPIC=msh/US/NY/#
OUTPUT_TOPIC=filtered/msh/US/NY
```

2. Start the service:

```bash
docker-compose up -d
```

3. View logs:

```bash
docker-compose logs -f
```

4. Stop the service:

```bash
docker-compose down
```

### Manual Installation

```bash
pip install -r requirements.txt
```

## Usage

### Docker Compose

The easiest way to run the filter is using Docker Compose. Edit the environment variables in [docker-compose.yml](docker-compose.yml) or create a `.env` file to override the defaults.

```bash
docker-compose up -d
```

To enable debug logging, uncomment the debug command section in [docker-compose.yml](docker-compose.yml).

### Command Line

```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --port 1883 \
  --username your_username \
  --password your_password \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/meshtastic" \
  --show-stats
```

### Daemon Mode

Run the filter in the background as a daemon:

```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/meshtastic" \
  --daemon
```

### Arguments

- `--broker`: MQTT broker hostname or IP (required)
- `--port`: MQTT broker port (default: 1883)
- `--username`: MQTT username (optional)
- `--password`: MQTT password (optional)
- `--input-topic`: Input topic to subscribe to, supports wildcards (required)
- `--output-topic`: Output topic for filtered messages (required)
- `--client-id`: MQTT client ID (default: meshtastic_filter)
- `--debug`: Enable debug logging
- `--show-stats`: Print statistics summary every 30 seconds
- `--daemon`: Run as daemon in background
- `--no-decrypt-default`: Disable decryption with default LongFast key
- `--channel-key`: Add custom channel encryption key (base64), can be specified multiple times

## How It Works

1. Connects to the MQTT broker with provided credentials
2. Subscribes to the input topic (supports wildcards like `msh/US/NY/#`)
3. Receives Meshtastic ServiceEnvelope protobuf messages
4. Attempts to decrypt encrypted packets using available keys:
   - Default LongFast key: `1PG7OiApB1nwvP+rz05pAQ==`
   - Custom channel keys (if provided)
5. Checks if the message has the "Ok to MQTT" flag set:
   - Bit 0 (0x01) of the bitfield in decoded data
   - Requires Meshtastic firmware 2.5+
6. If approved, forwards the message to the output topic
7. If not approved, logs and discards the message

## Examples

### Filter with decryption and statistics

```bash
python mqtt_filter.py \
  --broker mqtt.patinhas.da4.org \
  --username meshdev \
  --password large4cats \
  --input-topic "msh/US/NY/#" \
  --output-topic "filtered/msh/US/NY" \
  --show-stats
```

### Filter with custom encryption key

```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/EU_868/#" \
  --output-topic "filtered/mesh" \
  --channel-key "your-base64-key-here=" \
  --debug
```

### Run as daemon with statistics

```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --input-topic "msh/#" \
  --output-topic "filtered/mesh" \
  --show-stats \
  --daemon
```

## License

MIT License - see [LICENSE](LICENSE) file for details.
