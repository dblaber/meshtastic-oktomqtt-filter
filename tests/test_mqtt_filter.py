"""Tests for MeshtasticMQTTFilter core functionality"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import base64
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meshtastic.protobuf import mesh_pb2, mqtt_pb2


# Import inside fixture to avoid coverage warning
@pytest.fixture
def mqtt_filter_class():
    """Import MeshtasticMQTTFilter class"""
    from mqtt_filter import MeshtasticMQTTFilter
    return MeshtasticMQTTFilter


class TestMeshtasticMQTTFilterInit:
    """Test initialization and configuration"""

    @patch('mqtt_filter.mqtt.Client')
    def test_basic_initialization(self, mock_client_class, mqtt_filter_class):
        """Test basic filter initialization"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        assert filter_service.broker == "test.mqtt.com"
        assert filter_service.port == 1883
        assert filter_service.input_topic == "msh/test/#"
        assert filter_service.output_topic == "filtered/test"
        assert filter_service.show_stats is False
        assert len(filter_service.keys) == 1  # Default key

    @patch('mqtt_filter.mqtt.Client')
    def test_initialization_with_credentials(self, mock_client_class, mqtt_filter_class):
        """Test initialization with MQTT credentials"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            username="testuser",
            password="testpass"
        )

        mock_client.username_pw_set.assert_called_once_with("testuser", "testpass")

    @patch('mqtt_filter.mqtt.Client')
    def test_no_default_key(self, mock_client_class, mqtt_filter_class):
        """Test disabling default LongFast key"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            decrypt_default=False
        )

        assert len(filter_service.keys) == 0


class TestExemptNodes:
    """Test exempt node functionality"""

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_hex_format(self, mock_client_class, mqtt_filter_class):
        """Test parsing exempt nodes in hex format"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["0x12345678", "0xABCDEF01"]
        )

        assert 0x12345678 in filter_service.exempt_nodes
        assert 0xABCDEF01 in filter_service.exempt_nodes
        assert len(filter_service.exempt_nodes) == 2

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_meshtastic_format(self, mock_client_class, mqtt_filter_class):
        """Test parsing exempt nodes in Meshtastic format (!abcd1234)"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["!12345678", "!abcdef01"]
        )

        assert 0x12345678 in filter_service.exempt_nodes
        assert 0xABCDEF01 in filter_service.exempt_nodes

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_decimal_format(self, mock_client_class, mqtt_filter_class):
        """Test parsing exempt nodes in decimal format"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["305419896"]  # 0x12345678 in decimal
        )

        assert 0x12345678 in filter_service.exempt_nodes

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_invalid_format(self, mock_client_class, mqtt_filter_class):
        """Test handling of invalid exempt node format"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Should not raise exception, just log error
        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["invalid", "0x12345678"]
        )

        # Valid node should still be added
        assert 0x12345678 in filter_service.exempt_nodes
        assert len(filter_service.exempt_nodes) == 1


class TestCheckOkToMQTT:
    """Test the _check_ok_to_mqtt method"""

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_bypasses_filter(self, mock_client_class, mqtt_filter_class):
        """Test that exempt nodes bypass all filtering"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["0x12345678"]
        )

        # Create a packet from exempt node (even without decoded data)
        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is True
        assert filter_service.stats['forwarded_exempt'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_packet_with_ok_to_mqtt_bitfield(self, mock_client_class, mqtt_filter_class):
        """Test packet with Ok to MQTT bitfield set"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        packet.decoded.bitfield = 0x01  # Ok to MQTT enabled

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is True

    @patch('mqtt_filter.mqtt.Client')
    def test_packet_without_ok_to_mqtt_bitfield(self, mock_client_class, mqtt_filter_class):
        """Test packet without Ok to MQTT bitfield set"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        packet.decoded.bitfield = 0x00  # Ok to MQTT disabled

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is False
        assert filter_service.stats['rejected_bitfield_disabled'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_encrypted_packet_rejected(self, mock_client_class, mqtt_filter_class):
        """Test encrypted packet (no decoded data) is rejected"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.encrypted = b"\x01\x02\x03"

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is False
        assert filter_service.stats['rejected_encrypted'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_no_bitfield_with_allow_flag(self, mock_client_class, mqtt_filter_class):
        """Test packet without bitfield when allow_no_bitfield is True"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            allow_no_bitfield=True
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        # No bitfield set

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is True

    @patch('mqtt_filter.mqtt.Client')
    def test_no_bitfield_without_allow_flag(self, mock_client_class, mqtt_filter_class):
        """Test packet without bitfield when allow_no_bitfield is False"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            allow_no_bitfield=False
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        # No bitfield set

        result = filter_service._check_ok_to_mqtt(envelope, packet)

        assert result is False
        assert filter_service.stats['rejected_no_bitfield'] == 1


class TestStatistics:
    """Test statistics tracking"""

    @patch('mqtt_filter.mqtt.Client')
    def test_statistics_initialization(self, mock_client_class, mqtt_filter_class):
        """Test statistics are initialized correctly"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        assert filter_service.stats['total'] == 0
        assert filter_service.stats['forwarded'] == 0
        assert filter_service.stats['rejected_encrypted'] == 0
        assert filter_service.stats['rejected_no_bitfield'] == 0
        assert filter_service.stats['rejected_bitfield_disabled'] == 0
        assert filter_service.stats['decrypted'] == 0
        assert filter_service.stats['decryption_failed'] == 0
        assert filter_service.stats['forwarded_exempt'] == 0

    @patch('mqtt_filter.mqtt.Client')
    def test_exempt_node_statistics(self, mock_client_class, mqtt_filter_class):
        """Test exempt node statistics are tracked"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["0x12345678"]
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)

        # Check message from exempt node
        filter_service._check_ok_to_mqtt(envelope, packet)

        assert filter_service.stats['forwarded_exempt'] == 1


class TestCustomEncryptionKeys:
    """Test custom encryption key handling"""

    @patch('mqtt_filter.mqtt.Client')
    def test_add_custom_keys(self, mock_client_class, mqtt_filter_class):
        """Test adding custom encryption keys"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        custom_key = base64.b64encode(b"0123456789abcdef").decode()

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            channel_keys=[custom_key]
        )

        # Should have default key + custom key
        assert len(filter_service.keys) == 2
        assert filter_service.keys[0][0] == 'default'
        assert filter_service.keys[1][0] == 'custom-0'

    @patch('mqtt_filter.mqtt.Client')
    def test_invalid_custom_key(self, mock_client_class, mqtt_filter_class):
        """Test handling of invalid custom key"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            channel_keys=["invalid-base64!@#"]
        )

        # Should only have default key
        assert len(filter_service.keys) == 1


class TestRejectLogging:
    """Test rejection logging functionality"""

    @patch('mqtt_filter.mqtt.Client')
    def test_reject_logger_initialization(self, mock_client_class, mqtt_filter_class, tmp_path):
        """Test reject logger is initialized when file is specified"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        log_file = tmp_path / "rejected.log"

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            reject_log_file=str(log_file)
        )

        assert filter_service.reject_logger is not None

    @patch('mqtt_filter.mqtt.Client')
    def test_no_reject_logger_without_file(self, mock_client_class, mqtt_filter_class):
        """Test reject logger is not initialized without file"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        assert filter_service.reject_logger is None
