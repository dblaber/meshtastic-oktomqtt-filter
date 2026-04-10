#!/usr/bin/env python3
"""
Meshtastic MQTT Filter
Filters Meshtastic MQTT messages based on 'Ok to MQTT' flag
"""

import argparse
import base64
import hashlib
import logging
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

# Default Meshtastic LongFast channel key (base64)
DEFAULT_KEY_B64 = "1PG7OiApB1nwvP+rz05pAQ=="


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
        channel_keys: Optional[List[str]] = None,
        reject_log_file: Optional[str] = None,
        allow_no_bitfield: bool = False
    ):
        self.broker = broker
        self.port = port
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.username = username
        self.password = password
        self.show_stats = show_stats
        self.reject_log_file = reject_log_file
        self.allow_no_bitfield = allow_no_bitfield

        # Set up reject logger if file specified
        self.reject_logger = None
        if reject_log_file:
            self.reject_logger = logging.getLogger('reject_logger')
            self.reject_logger.setLevel(logging.INFO)
            # Remove any existing handlers
            self.reject_logger.handlers = []
            # Create file handler
            fh = logging.FileHandler(reject_log_file)
            fh.setLevel(logging.INFO)
            # Create formatter
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            fh.setFormatter(formatter)
            self.reject_logger.addHandler(fh)
            # Don't propagate to root logger
            self.reject_logger.propagate = False
            logger.info(f"Reject logging enabled: {reject_log_file}")

        # Encryption keys (stored as base64 strings, decoded at decryption time)
        self.keys = []
        if decrypt_default:
            self.keys.append(('default', DEFAULT_KEY_B64))
            logger.info("Encryption: Using default LongFast key")

        if channel_keys:
            for i, key_b64 in enumerate(channel_keys):
                try:
                    base64.b64decode(key_b64)  # validate
                    self.keys.append((f'custom-{i}', key_b64))
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
                bitfield_str = f"0x{packet.decoded.bitfield:02x}" if packet.decoded.HasField('bitfield') else "None"
                logger.debug(f"Decoded: portnum={packet.decoded.portnum}, bitfield={bitfield_str}")
            else:
                logger.debug("Decoded: NOT PRESENT (encrypted)")

            # Try to decrypt if packet is encrypted
            if packet.decoded.portnum == portnums_pb2.PortNum.UNKNOWN_APP and packet.encrypted:
                logger.debug(f"Packet has encrypted data, attempting decryption with {len(self.keys)} key(s)")
                if self.keys:
                    decrypted = self._attempt_decryption(packet, msg.topic)
                    if decrypted:
                        logger.debug(f"Decrypted packet from 0x{from_id:08x}")
                    else:
                        logger.debug(f"Failed to decrypt packet from 0x{from_id:08x}")
                else:
                    logger.debug("No decryption keys available")

            # Check if message should be forwarded to MQTT
            # Messages are ok to MQTT if they're on a public channel (channel_id == 0 or PKI_ENCRYPTED not set)
            # Or if they explicitly have want_response which indicates public sharing
            is_ok_to_mqtt = self._check_ok_to_mqtt(envelope, packet, msg.topic)

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

    @staticmethod
    def _extract_channel_name_from_topic(topic: str) -> str:
        """Extract channel name from MQTT topic for key derivation.

        Topic format: msh/region/gateway_id/message_type/channel_name/gateway_hex
        """
        try:
            parts = topic.split("/")
            if len(parts) >= 5:
                candidate = parts[4]
                if candidate not in ("e", "c") and not candidate.startswith("!"):
                    return candidate
        except Exception:
            pass
        return ""

    @staticmethod
    def _derive_key(key_base64: str, channel_name: str) -> bytes:
        """Derive encryption key from channel name and base64 key.

        Follows Meshtastic's key derivation:
        - Named channels: SHA256(key_bytes + channel_name_bytes)
        - Primary channel (empty name): raw key bytes
        """
        try:
            key_bytes = base64.b64decode(key_base64)
            if channel_name:
                hasher = hashlib.sha256()
                hasher.update(key_bytes)
                hasher.update(channel_name.encode("utf-8"))
                return hasher.digest()
            return key_bytes
        except Exception as e:
            logger.warning(f"Error deriving key: {e}")
            return b"\x00" * 32

    @staticmethod
    def _decrypt_payload(encrypted_payload: bytes, packet_id: int, sender_id: int, key: bytes) -> bytes:
        """Decrypt a Meshtastic packet payload using AES-CTR.

        Returns decrypted bytes, or empty bytes on failure.
        """
        try:
            if not encrypted_payload:
                return b""
            nonce = packet_id.to_bytes(8, byteorder='little') + sender_id.to_bytes(8, byteorder='little')
            cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
            decryptor = cipher.decryptor()
            return decryptor.update(encrypted_payload) + decryptor.finalize()
        except Exception as e:
            logger.debug(f"Decryption failed: {e}")
            return b""

    def _try_decrypt_with_key(self, packet, key_base64: str, channel_name: str = "") -> bool:
        """Try to decrypt a packet with a single key and channel name.

        Matches the pattern from mesh-mqtt-pg-collector/malla.
        """
        # Already decoded?
        if packet.decoded.portnum != portnums_pb2.PortNum.UNKNOWN_APP:
            return False
        if not packet.encrypted:
            return False

        encrypted_payload = packet.encrypted
        packet_id = packet.id
        sender_id = getattr(packet, 'from', 0)

        key = self._derive_key(key_base64, channel_name)
        decrypted_payload = self._decrypt_payload(encrypted_payload, packet_id, sender_id, key)
        if not decrypted_payload:
            return False

        try:
            decoded_data = mesh_pb2.Data()
            decoded_data.ParseFromString(decrypted_payload)

            if decoded_data.portnum == portnums_pb2.PortNum.UNKNOWN_APP:
                return False

            packet.decoded.CopyFrom(decoded_data)

            portnum_name = portnums_pb2.PortNum.Name(decoded_data.portnum)
            logger.debug(f"Decrypted packet {packet_id} from 0x{sender_id:08x}: {portnum_name}")
            return True
        except Exception as e:
            logger.debug(f"Failed to parse decrypted payload: {e}")
            return False

    def _attempt_decryption(self, packet, topic: str) -> bool:
        """Try all available keys to decrypt a packet.

        Strategy (matching mesh-mqtt-pg-collector/malla):
        1. Try each key with no channel derivation (primary channel).
        2. Try each key with channel name derivation (from topic).
        """
        channel_name = self._extract_channel_name_from_topic(topic)

        # Phase 1: try each key with no derivation (primary/preset channels)
        for key_name, key_b64 in self.keys:
            if self._try_decrypt_with_key(packet, key_b64, channel_name=""):
                self.stats['decrypted'] += 1
                logger.debug(f"Decrypted with key '{key_name}' (no derivation)")
                return True

        # Phase 2: try each key with channel name derivation
        if channel_name:
            for key_name, key_b64 in self.keys:
                if self._try_decrypt_with_key(packet, key_b64, channel_name=channel_name):
                    self.stats['decrypted'] += 1
                    logger.debug(f"Decrypted with key '{key_name}' (derived from '{channel_name}')")
                    return True

        self.stats['decryption_failed'] += 1
        logger.debug(f"Failed to decrypt packet with any available key")
        return False

    def _log_rejected_packet(self, reason: str, envelope: mqtt_pb2.ServiceEnvelope, packet, topic: str):
        """Log details of rejected packets to file"""
        if not self.reject_logger:
            return

        from_id = getattr(packet, 'from', 0)
        to_id = getattr(packet, 'to', 0)

        # Build log entry
        log_parts = [
            f"REJECTED - Reason: {reason}",
            f"From: !{from_id:08x}",
            f"To: !{to_id:08x}",
            f"Topic: {topic}",
            f"Channel: {envelope.channel_id}",
            f"Gateway: {envelope.gateway_id}",
            f"Packet ID: {packet.id}",
        ]

        # Add decoded information if available
        if packet.HasField('decoded'):
            portnum_name = portnums_pb2.PortNum.Name(packet.decoded.portnum) if packet.decoded.portnum else "UNKNOWN"
            log_parts.append(f"PortNum: {portnum_name}")

            if packet.decoded.HasField('bitfield'):
                log_parts.append(f"Bitfield: 0x{packet.decoded.bitfield:02x}")

            # Try to extract text payload
            if packet.decoded.portnum == portnums_pb2.PortNum.TEXT_MESSAGE_APP:
                try:
                    text = packet.decoded.payload.decode('utf-8')
                    log_parts.append(f"Text: {text}")
                except:
                    pass

            # Try to extract telemetry data
            if packet.decoded.portnum == portnums_pb2.PortNum.TELEMETRY_APP:
                try:
                    telemetry = telemetry_pb2.Telemetry()
                    telemetry.ParseFromString(packet.decoded.payload)
                    log_parts.append(f"Telemetry: {telemetry}")
                except:
                    pass
        else:
            log_parts.append("Status: Still encrypted (decryption failed)")

        self.reject_logger.info(" | ".join(log_parts))

    def _check_ok_to_mqtt(self, envelope: mqtt_pb2.ServiceEnvelope, packet, topic: str = "") -> bool:
        """
        Check if the message is marked as 'Ok to MQTT'

        Returns:
            True if message should be forwarded, False otherwise
        """
        from_id = getattr(packet, 'from', 0)

        # Check if the packet has decoded data (portnum UNKNOWN_APP means still encrypted)
        if packet.decoded.portnum == portnums_pb2.PortNum.UNKNOWN_APP:
            self.stats['rejected_encrypted'] += 1
            logger.debug(f"REJECT 0x{from_id:08x}: encrypted")
            self._log_rejected_packet("Still encrypted after decryption attempts", envelope, packet, topic)
            return False

        # Check the bitfield in the decoded data
        # Bit 0 (0x01) indicates "ok to MQTT"
        if packet.decoded.HasField('bitfield'):
            is_ok = bool(packet.decoded.bitfield & 0x01)
            if not is_ok:
                self.stats['rejected_bitfield_disabled'] += 1
                logger.debug(f"REJECT 0x{from_id:08x}: bitfield disabled")
                self._log_rejected_packet("Bitfield bit 0 (Ok to MQTT) not set", envelope, packet, topic)
            return is_ok
        else:
            # No bitfield set - behavior depends on allow_no_bitfield flag
            if self.allow_no_bitfield:
                logger.debug(f"ALLOW 0x{from_id:08x}: no bitfield (allow_no_bitfield=True)")
                return True
            else:
                self.stats['rejected_no_bitfield'] += 1
                logger.debug(f"REJECT 0x{from_id:08x}: no bitfield")
                self._log_rejected_packet("No bitfield present (firmware < 2.5)", envelope, packet, topic)
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
    parser.add_argument(
        '--reject-log',
        dest='reject_log_file',
        help='Log file for rejected packets (optional, enables detailed rejection logging)'
    )
    parser.add_argument(
        '--allow-no-bitfield',
        action='store_true',
        help='Allow packets without bitfield (for older firmware or backwards compatibility)'
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
        channel_keys=args.channel_keys,
        reject_log_file=args.reject_log_file,
        allow_no_bitfield=args.allow_no_bitfield
    )

    filter_service.start()


if __name__ == '__main__':
    main()