"""Integration tests for message processing pipeline"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call
import base64
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meshtastic.protobuf import mesh_pb2, mqtt_pb2


# Import inside fixture to avoid coverage warning
@pytest.fixture
def mqtt_filter_class():
    """Import MeshtasticMQTTFilter class"""
    from mqtt_filter import MeshtasticMQTTFilter
    return MeshtasticMQTTFilter


class TestMessageProcessing:
    """Test end-to-end message processing"""

    @patch('mqtt_filter.mqtt.Client')
    def test_forward_valid_message(self, mock_client_class, mqtt_filter_class):
        """Test forwarding a valid message with Ok to MQTT bitfield"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        # Create a valid ServiceEnvelope with Ok to MQTT bitfield
        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.channel_id = "LongFast"
        envelope.gateway_id = "!87654321"

        packet = mesh_pb2.MeshPacket()
        packet.id = 123456
        setattr(packet, 'from', 0x12345678)
        setattr(packet, 'to', 0xFFFFFFFF)
        packet.decoded.portnum = 1
        packet.decoded.payload = b"Test message"
        packet.decoded.bitfield = 0x01  # Ok to MQTT enabled

        envelope.packet.CopyFrom(packet)

        # Create mock MQTT message
        mock_msg = Mock()
        mock_msg.topic = "msh/test/2/e/LongFast/!12345678"
        mock_msg.payload = envelope.SerializeToString()

        # Process message
        filter_service.on_message(mock_client, None, mock_msg)

        # Verify message was published
        assert mock_client.publish.called
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "filtered/test/2/e/LongFast/!12345678"
        assert filter_service.stats['forwarded'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_reject_message_no_bitfield(self, mock_client_class, mqtt_filter_class):
        """Test rejecting a message without Ok to MQTT bitfield"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        # Create envelope without bitfield
        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        packet.decoded.bitfield = 0x00  # Ok to MQTT disabled

        envelope.packet.CopyFrom(packet)

        mock_msg = Mock()
        mock_msg.topic = "msh/test/2/e/LongFast/!12345678"
        mock_msg.payload = envelope.SerializeToString()

        filter_service.on_message(mock_client, None, mock_msg)

        # Verify message was NOT published
        assert not mock_client.publish.called
        assert filter_service.stats['rejected_bitfield_disabled'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_forward_exempt_node_message(self, mock_client_class, mqtt_filter_class):
        """Test forwarding message from exempt node regardless of bitfield"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["0x12345678"]
        )

        # Create envelope from exempt node with bitfield disabled
        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        packet.decoded.bitfield = 0x00  # Ok to MQTT disabled, but node is exempt

        envelope.packet.CopyFrom(packet)

        mock_msg = Mock()
        mock_msg.topic = "msh/test/2/e/LongFast/!12345678"
        mock_msg.payload = envelope.SerializeToString()

        filter_service.on_message(mock_client, None, mock_msg)

        # Verify message WAS published despite disabled bitfield
        assert mock_client.publish.called
        assert filter_service.stats['forwarded_exempt'] == 1
        assert filter_service.stats['forwarded'] == 1

    @patch('mqtt_filter.mqtt.Client')
    def test_topic_mapping(self, mock_client_class, mqtt_filter_class):
        """Test that input topic prefix is correctly replaced with output prefix"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/US/NY/#",
            output_topic="filtered/msh/US/NY"
        )

        envelope = mqtt_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()
        setattr(packet, 'from', 0x12345678)
        packet.decoded.portnum = 1
        packet.decoded.bitfield = 0x01

        envelope.packet.CopyFrom(packet)

        mock_msg = Mock()
        mock_msg.topic = "msh/US/NY/2/e/LongFast/!12345678"
        mock_msg.payload = envelope.SerializeToString()

        filter_service.on_message(mock_client, None, mock_msg)

        # Verify topic mapping
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "filtered/msh/US/NY/2/e/LongFast/!12345678"

    @patch('mqtt_filter.mqtt.Client')
    def test_statistics_tracking(self, mock_client_class, mqtt_filter_class):
        """Test that statistics are tracked correctly during processing"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test",
            exempt_nodes=["0xAAAAAAAA"]
        )

        # Process multiple messages with different outcomes
        messages = [
            # Valid message
            (0x11111111, 0x01, True),
            # Disabled bitfield
            (0x22222222, 0x00, False),
            # Exempt node
            (0xAAAAAAAA, 0x00, True),
            # Valid message
            (0x33333333, 0x01, True),
        ]

        for from_id, bitfield, should_forward in messages:
            envelope = mqtt_pb2.ServiceEnvelope()
            packet = mesh_pb2.MeshPacket()
            setattr(packet, 'from', from_id)
            packet.decoded.portnum = 1
            packet.decoded.bitfield = bitfield

            envelope.packet.CopyFrom(packet)

            mock_msg = Mock()
            mock_msg.topic = f"msh/test/!{from_id:08x}"
            mock_msg.payload = envelope.SerializeToString()

            filter_service.on_message(mock_client, None, mock_msg)

        # Verify statistics
        assert filter_service.stats['total'] == 4
        assert filter_service.stats['forwarded'] == 3
        assert filter_service.stats['forwarded_exempt'] == 1
        assert filter_service.stats['rejected_bitfield_disabled'] == 1


class TestConnectionHandling:
    """Test MQTT connection handling"""

    @patch('mqtt_filter.mqtt.Client')
    def test_on_connect_success(self, mock_client_class, mqtt_filter_class):
        """Test successful MQTT connection"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        # Simulate successful connection
        filter_service.on_connect(mock_client, None, None, 0)

        # Verify subscription
        mock_client.subscribe.assert_called_once_with("msh/test/#")

    @patch('mqtt_filter.mqtt.Client')
    def test_on_connect_failure(self, mock_client_class, mqtt_filter_class):
        """Test failed MQTT connection"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        # Simulate failed connection (rc != 0)
        filter_service.on_connect(mock_client, None, None, 5)

        # Verify no subscription was made
        assert not mock_client.subscribe.called

    @patch('mqtt_filter.mqtt.Client')
    def test_on_disconnect(self, mock_client_class, mqtt_filter_class):
        """Test handling of disconnect"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        # Test both expected (rc=0) and unexpected (rc!=0) disconnects
        filter_service.on_disconnect(mock_client, None, 0)
        filter_service.on_disconnect(mock_client, None, 1)

        # Should not raise exceptions


class TestErrorHandling:
    """Test error handling in message processing"""

    @patch('mqtt_filter.mqtt.Client')
    def test_malformed_protobuf(self, mock_client_class, mqtt_filter_class):
        """Test handling of malformed protobuf message"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        filter_service = mqtt_filter_class(
            broker="test.mqtt.com",
            port=1883,
            input_topic="msh/test/#",
            output_topic="filtered/test"
        )

        mock_msg = Mock()
        mock_msg.topic = "msh/test/invalid"
        mock_msg.payload = b"This is not valid protobuf data"

        # Should not raise exception
        filter_service.on_message(mock_client, None, mock_msg)

        # Message should not be published
        assert not mock_client.publish.called
