# Meshtastic MQTT Filter

Filters Meshtastic MQTT messages based on the "Ok to MQTT" flag, forwarding only authorized messages to an output topic.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python mqtt_filter.py \
  --broker mqtt.example.com \
  --port 1883 \
  --username your_username \
  --password your_password \
  --input-topic "msh/US/2/json/#" \
  --output-topic "filtered/meshtastic"
```

### Arguments

- `--broker`: MQTT broker hostname or IP (required)
- `--port`: MQTT broker port (default: 1883)
- `--username`: MQTT username (optional)
- `--password`: MQTT password (optional)
- `--input-topic`: Input topic to subscribe to (required)
- `--output-topic`: Output topic for filtered messages (required)
- `--client-id`: MQTT client ID (default: meshtastic_filter)
- `--debug`: Enable debug logging

## How It Works

1. Connects to the MQTT broker with provided credentials
2. Subscribes to the input topic
3. Receives Meshtastic protobuf messages
4. Checks if the message is marked as "Ok to MQTT" by examining:
   - Gateway ID (indicates message came through MQTT gateway)
   - Channel ID (public channels are ok to forward)
   - Decoded packet availability
5. If allowed, forwards the message to the output topic
6. If not allowed, logs and discards the message

## Example

```bash
# Filter messages from public Meshtastic MQTT
python mqtt_filter.py \
  --broker mqtt.meshtastic.org \
  --port 1883 \
  --input-topic "msh/#" \
  --output-topic "filtered/mesh" \
  --debug
```
