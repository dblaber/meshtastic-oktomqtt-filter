"""Pytest configuration and shared fixtures"""
import base64
import pytest
from unittest.mock import Mock, MagicMock
from meshtastic.protobuf import mesh_pb2, mqtt_pb2


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client"""
    client = Mock()
    client.connect = Mock(return_value=0)
    client.subscribe = Mock()
    client.publish = Mock()
    client.disconnect = Mock()
    client.loop_forever = Mock()
    client.username_pw_set = Mock()
    return client


@pytest.fixture
def sample_mesh_packet():
    """Create a sample MeshPacket with decoded data"""
    packet = mesh_pb2.MeshPacket()
    packet.id = 123456
    packet.channel = 0
    setattr(packet, 'from', 0x12345678)
    setattr(packet, 'to', 0xFFFFFFFF)

    # Add decoded data with bitfield
    packet.decoded.portnum = 1  # TEXT_MESSAGE_APP
    packet.decoded.payload = b"Test message"
    packet.decoded.bitfield = 0x01  # Ok to MQTT enabled

    return packet


@pytest.fixture
def sample_encrypted_packet():
    """Create a sample encrypted MeshPacket"""
    packet = mesh_pb2.MeshPacket()
    packet.id = 123456
    packet.channel = 0
    setattr(packet, 'from', 0x12345678)
    setattr(packet, 'to', 0xFFFFFFFF)

    # Add encrypted data (not decoded)
    packet.encrypted = b"\x01\x02\x03\x04\x05"  # Dummy encrypted data

    return packet


@pytest.fixture
def sample_service_envelope(sample_mesh_packet):
    """Create a sample ServiceEnvelope"""
    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.channel_id = "LongFast"
    envelope.gateway_id = "!87654321"
    envelope.packet.CopyFrom(sample_mesh_packet)

    return envelope


@pytest.fixture
def default_longfast_key():
    """Return the default LongFast key"""
    return base64.b64decode("1PG7OiApB1nwvP+rz05pAQ==")
