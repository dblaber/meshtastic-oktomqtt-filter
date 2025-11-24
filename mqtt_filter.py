#!/usr/bin/env python3
"""
Meshtastic MQTT Filter
Filters Meshtastic MQTT messages based on 'Ok to MQTT' flag
"""

import argparse
import base64
import hashlib
import json
import logging
import struct
import sys
import time
from typing import List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import paho.mqtt.client as mqtt
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default Meshtastic LongFast channel key
DEFAULT_KEY = base64.b64decode("1PG7OiApB1nwvP+rz05pAQ==")


class MeshtasticMQTTFilter:
    def __init__(
        self,
        broker: str,
        port: int,
        input_topic: str,
        output_topic: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = "meshtastic_filter",
        show_stats: bool = False,
        decrypt_default: bool = True,
        channel_keys: Optional[List[str]] = None
    ):
        self.broker = broker
        self.port = port
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.username = username
        self.password = password
        self.show_stats = show_stats

        # Encryption keys
        self.keys = []
        if decrypt_default:
            self.keys.append(('default', DEFAULT_KEY))
            logger.info("Encryption: Using default LongFast key")

        if channel_keys:
            for i, key_b64 in enumerate(channel_keys):
                try:
                    key = base64.b64decode(key_b64)
                    self.keys.append((f'custom-{i}', key))
                    logger.info(f"Encryption: Added custom key #{i}")
                except Exception as e:
                    logger.error(f"Failed to decode custom key #{i}: {e}")

        # Statistics tracking
        self.stats = {
            'total': 0,
            'forwarded': 0,
            'rejected_encrypted': 0,
            'rejected_no_bitfield': 0,
            'rejected_bitfield_disabled': 0,
            'decrypted': 0,
            'decryption_failed': 0
        }
        self.last_stats_time = time.time()

        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        if username and password:
            self.client.username_pw_set(username, password)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            client.subscribe(self.input_topic)
            logger.info(f"Subscribed to input topic: {self.input_topic}")
        else:
            logger.error(f"Connection failed with code {rc}")

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(f"Unexpected disconnect with code {rc}")
        else:
            logger.info("Disconnected from MQTT broker")

    def on_message(self, client, userdata, msg):
        try:
            # Increment total message counter
            self.stats['total'] += 1
            msg_num = self.stats['total']

            # Parse the Meshtastic ServiceEnvelope
            envelope = mqtt_pb2.ServiceEnvelope()
            envelope.ParseFromString(msg.payload)

            # Check if the message has the 'Ok to MQTT' flag set
            # In Meshtastic, this is the PKI_ENCRYPTED flag or channel_id indicating public channel
            packet = envelope.packet

            # Debug logging: log full message details
            from_id = getattr(packet, 'from', 0)
            to_id = getattr(packet, 'to', 0)

            logger.debug("=" * 80)
            logger.debug(f"Message #{msg_num}")
            logger.debug(f"Raw MQTT Topic: {msg.topic}")
            logger.debug(f"Payload size: {len(msg.payload)} bytes")
            logger.debug(f"ServiceEnvelope: channel_id={envelope.channel_id}, gateway_id={envelope.gateway_id}")
            logger.debug(f"MeshPacket: from=0x{from_id:08x}, to=0x{to_id:08x}, channel={packet.channel}, id={packet.id}")

            if packet.HasField('decoded'):
                logger.debug(f"Decoded: portnum={packet.decoded.portnum}, bitfield=0x{packet.decoded.bitfield:02x if packet.decoded.HasField('bitfield') else 0}")
            else:
                logger.debug("Decoded: NOT PRESENT (encrypted)")

            # Try to decrypt if packet is encrypted
            if not packet.HasField('decoded') and packet.HasField('encrypted'):
                logger.debug(f"Packet has encrypted data, attempting decryption with {len(self.keys)} key(s)")
                if self.keys:
                    # Get channel name from envelope for key derivation
                    channel_name = envelope.channel_id if envelope.channel_id else ""
                    decrypted = self._decrypt_packet(packet, channel_name)
                    if decrypted:
                        logger.debug(f"Decrypted packet from 0x{from_id:08x}")
                    else:
                        logger.debug(f"Failed to decrypt packet from 0x{from_id:08x}")
                else:
                    logger.debug("No decryption keys available")

            # Check if message should be forwarded to MQTT
            # Messages are ok to MQTT if they're on a public channel (channel_id == 0 or PKI_ENCRYPTED not set)
            # Or if they explicitly have want_response which indicates public sharing
            is_ok_to_mqtt = self._check_ok_to_mqtt(envelope, packet)

            if is_ok_to_mqtt:
                self.stats['forwarded'] += 1
                logger.debug(f"FORWARD: 0x{from_id:08x} -> {envelope.channel_id}")
                # Publish the original payload to output topic
                # Replace the input topic prefix with output topic prefix
                output_topic = msg.topic.replace(self.input_topic.rstrip('/#'), self.output_topic.rstrip('/#'), 1)
                client.publish(output_topic, msg.payload)
            else:
                logger.debug(f"DISCARD: 0x{from_id:08x} (no ok_to_mqtt)")

            # Print periodic statistics every 10 messages
            if msg_num % 10 == 0:
                self._print_stats()

            # Print timed statistics if show_stats is enabled
            if self.show_stats:
                current_time = time.time()
                if current_time - self.last_stats_time >= 30:
                    self._print_stats()
                    self.last_stats_time = current_time

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    def _print_stats(self):
        """Print statistics summary"""
        total = self.stats['total']
        if total == 0:
            return

        forwarded = self.stats['forwarded']
        rejected = total - forwarded

        logger.info("=" * 60)
        logger.info("MESSAGE STATISTICS:")
        logger.info(f"  Total messages: {total}")
        logger.info(f"  Forwarded: {forwarded} ({100*forwarded/total:.1f}%)")
        logger.info(f"  Rejected: {rejected} ({100*rejected/total:.1f}%)")
        if self.stats['decrypted'] > 0:
            logger.info(f"  Decrypted: {self.stats['decrypted']}")
            logger.info(f"  Decryption failed: {self.stats['decryption_failed']}")
        logger.info("  Rejection reasons:")
        logger.info(f"    - Encrypted (no decoded data): {self.stats['rejected_encrypted']}")
        logger.info(f"    - No bitfield (older firmware): {self.stats['rejected_no_bitfield']}")
        logger.info(f"    - Bitfield disabled by user: {self.stats['rejected_bitfield_disabled']}")
        logger.info("=" * 60)

    def _derive_key(self, base_key: bytes, channel_name: str) -> bytes:
        """
        Derive encryption key from channel name and base key.
        This follows Meshtastic's key derivation algorithm.

        Args:
            base_key: Base encryption key
            channel_name: Channel name for key derivation (empty for primary channel)

        Returns:
            32-byte encryption key
        """
        # If channel name is provided and not empty, derive key using SHA256
        if channel_name and channel_name != "":
            # Convert channel name to bytes
            channel_bytes = channel_name.encode("utf-8")
            # Create SHA256 hash of base key + channel name
            hasher = hashlib.sha256()
            hasher.update(base_key)
            hasher.update(channel_bytes)
            derived_key = hasher.digest()
            return derived_key
        else:
            # For primary channel, use the key as-is
            return base_key

    def _decrypt_packet(self, packet, channel_name: str = "") -> bool:
        """
        Attempt to decrypt an encrypted packet using available keys.

        Args:
            packet: The MeshPacket to decrypt
            channel_name: Channel name for key derivation

        Returns:
            True if decryption succeeded, False otherwise
        """
        if not packet.HasField('encrypted') or len(packet.encrypted) == 0:
            logger.debug("Packet has no encrypted field or empty encrypted data")
            return False

        from_id = getattr(packet, 'from', 0)
        packet_id = packet.id

        logger.debug(f"Attempting decryption: packet_id={packet_id}, from=0x{from_id:08x}, encrypted_len={len(packet.encrypted)}, channel={channel_name}")

        # Try each key
        for key_name, base_key in self.keys:
            try:
                logger.debug(f"Trying key '{key_name}'")

                # Derive the actual encryption key from base key + channel name
                # BUT: Don't derive for LongFast - it uses the base key directly
                if channel_name and channel_name not in ["LongFast", ""]:
                    key = self._derive_key(base_key, channel_name)
                    logger.debug(f"Derived key from channel '{channel_name}': {len(key)} bytes")
                else:
                    key = base_key
                    logger.debug(f"Using base key directly (channel='{channel_name}'): {len(key)} bytes")

                # Meshtastic uses packet ID and from address as nonce
                # Nonce = packet_id (8 bytes LE) + from_node (8 bytes LE) = 16 bytes total
                packet_id_bytes = packet_id.to_bytes(8, byteorder='little')
                sender_id_bytes = from_id.to_bytes(8, byteorder='little')
                nonce = packet_id_bytes + sender_id_bytes

                if len(nonce) != 16:
                    logger.warning(f"Invalid nonce length: {len(nonce)}, expected 16 bytes")
                    continue

                # Use the derived key (already 32 bytes from SHA256)
                key_bytes = key

                # Create AES-CTR cipher using cryptography library
                cipher = Cipher(
                    algorithms.AES(key_bytes),
                    modes.CTR(nonce),
                    backend=default_backend()
                )
                decryptor = cipher.decryptor()

                # Decrypt the payload
                decrypted = decryptor.update(packet.encrypted) + decryptor.finalize()

                logger.debug(f"Decrypted {len(decrypted)} bytes: {decrypted[:min(32, len(decrypted))].hex()}")

                # Try to parse as Data protobuf
                data = mesh_pb2.Data()
                data.ParseFromString(decrypted)

                # Validate that we actually got valid data
                if data.portnum == 0:
                    logger.debug("Decrypted data has portnum=0 (UNKNOWN), likely wrong key")
                    raise ValueError("Invalid portnum")

                # If we got here, decryption succeeded
                packet.decoded.CopyFrom(data)
                packet.ClearField('encrypted')

                self.stats['decrypted'] += 1
                logger.debug(f"Successfully decrypted packet from 0x{from_id:08x} using key '{key_name}'")
                return True

            except Exception as e:
                # Decryption failed with this key, try next
                logger.debug(f"Decryption failed with key '{key_name}': {e}")
                continue

        # None of the keys worked
        self.stats['decryption_failed'] += 1
        logger.debug(f"Failed to decrypt packet from 0x{from_id:08x} with any available key")
        return False

    def _check_ok_to_mqtt(self, envelope: mqtt_pb2.ServiceEnvelope, packet) -> bool:
        """
        Check if the message is marked as 'Ok to MQTT'

        Returns:
            True if message should be forwarded, False otherwise
        """
        from_id = getattr(packet, 'from', 0)

        # Check if the packet has decoded data
        if not packet.HasField('decoded'):
            self.stats['rejected_encrypted'] += 1
            logger.debug(f"REJECT 0x{from_id:08x}: encrypted")
            return False

        # Check the bitfield in the decoded data
        # Bit 0 (0x01) indicates "ok to MQTT"
        if packet.decoded.HasField('bitfield'):
            is_ok = bool(packet.decoded.bitfield & 0x01)
            if not is_ok:
                self.stats['rejected_bitfield_disabled'] += 1
                logger.debug(f"REJECT 0x{from_id:08x}: bitfield disabled")
            return is_ok
        else:
            # No bitfield set means not approved for MQTT
            self.stats['rejected_no_bitfield'] += 1
            logger.debug(f"REJECT 0x{from_id:08x}: no bitfield")
            return False

    def start(self):
        """Start the MQTT filter service"""
        try:
            logger.info(f"Connecting to MQTT broker {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)
            logger.info("Starting MQTT loop...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Filter Meshtastic MQTT messages based on "Ok to MQTT" flag'
    )
    parser.add_argument(
        '--broker',
        required=True,
        help='MQTT broker hostname or IP'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=1883,
        help='MQTT broker port (default: 1883)'
    )
    parser.add_argument(
        '--username',
        help='MQTT username (optional)'
    )
    parser.add_argument(
        '--password',
        help='MQTT password (optional)'
    )
    parser.add_argument(
        '--input-topic',
        required=True,
        help='Input topic to subscribe to (e.g., msh/US/2/json/#)'
    )
    parser.add_argument(
        '--output-topic',
        required=True,
        help='Output topic to publish filtered messages (e.g., filtered/meshtastic)'
    )
    parser.add_argument(
        '--client-id',
        default='meshtastic_filter',
        help='MQTT client ID (default: meshtastic_filter)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--show-stats',
        action='store_true',
        help='Print statistics summary every 30 seconds'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon in background'
    )
    parser.add_argument(
        '--no-decrypt-default',
        action='store_true',
        help='Disable decryption with default LongFast key'
    )
    parser.add_argument(
        '--channel-key',
        action='append',
        dest='channel_keys',
        help='Add custom channel encryption key (base64). Can be specified multiple times.'
    )

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Daemonize if requested
    if args.daemon:
        import os
        import sys

        # Fork once
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process - print PID and exit
                print(f"Daemon started with PID: {pid}")
                sys.exit(0)
        except OSError as e:
            logger.error(f"Fork failed: {e}")
            sys.exit(1)

        # Decouple from parent environment
        os.chdir('/')
        os.setsid()
        os.umask(0)

        # Fork again to prevent zombie
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            logger.error(f"Second fork failed: {e}")
            sys.exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        with open('/dev/null', 'r') as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open('/dev/null', 'a+') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
        with open('/dev/null', 'a+') as f:
            os.dup2(f.fileno(), sys.stderr.fileno())

    filter_service = MeshtasticMQTTFilter(
        broker=args.broker,
        port=args.port,
        input_topic=args.input_topic,
        output_topic=args.output_topic,
        username=args.username,
        password=args.password,
        client_id=args.client_id,
        show_stats=args.show_stats,
        decrypt_default=not args.no_decrypt_default,
        channel_keys=args.channel_keys
    )

    filter_service.start()


if __name__ == '__main__':
    main()