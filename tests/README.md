# Meshtastic MQTT Filter Test Suite

This directory contains the test suite for the Meshtastic MQTT Filter application.

## Test Structure

```
tests/
├── __init__.py                   # Test package initialization
├── conftest.py                   # Pytest fixtures and configuration
├── test_mqtt_filter.py           # Unit tests for core functionality
├── test_message_processing.py    # Integration tests for message pipeline
└── README.md                     # This file
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Run All Tests

```bash
pytest
```

### Run with Coverage Report

```bash
pytest --cov=mqtt_filter --cov-report=html
```

This will generate an HTML coverage report in `htmlcov/index.html`.

### Run Specific Test Files

```bash
# Unit tests only
pytest tests/test_mqtt_filter.py

# Integration tests only
pytest tests/test_message_processing.py
```

### Run Specific Test Classes or Functions

```bash
# Run a specific test class
pytest tests/test_mqtt_filter.py::TestExemptNodes

# Run a specific test function
pytest tests/test_mqtt_filter.py::TestExemptNodes::test_exempt_node_hex_format
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Debug Output

```bash
pytest -vv -s
```

## Test Categories

### Unit Tests (`test_mqtt_filter.py`)

- **TestMeshtasticMQTTFilterInit**: Tests for initialization and configuration
- **TestExemptNodes**: Tests for exempt node parsing and validation
- **TestCheckOkToMQTT**: Tests for the authorization check logic
- **TestStatistics**: Tests for statistics tracking
- **TestCustomEncryptionKeys**: Tests for custom encryption key handling
- **TestRejectLogging**: Tests for rejection logging functionality

### Integration Tests (`test_message_processing.py`)

- **TestMessageProcessing**: End-to-end message processing tests
- **TestConnectionHandling**: MQTT connection and disconnection tests
- **TestErrorHandling**: Error and edge case handling tests

## Key Test Scenarios

### Exempt Node Testing

Tests verify that:
- Nodes can be specified in multiple formats (0xABCD1234, !abcd1234, decimal)
- Exempt nodes bypass all filtering rules
- Invalid node IDs are handled gracefully
- Statistics track exempt node forwards separately

### Message Filtering

Tests verify that:
- Messages with "Ok to MQTT" bitfield are forwarded
- Messages without bitfield are rejected (unless allow_no_bitfield=True)
- Encrypted messages are rejected
- Topic mapping works correctly

### Statistics

Tests verify that:
- All message outcomes are tracked correctly
- Exempt node forwards are counted separately
- Rejection reasons are categorized properly

## Writing New Tests

When adding new features, follow these guidelines:

1. **Create fixtures in conftest.py** for reusable test data
2. **Use descriptive test names** that explain what is being tested
3. **Follow the Arrange-Act-Assert pattern**:
   - Arrange: Set up test data and mocks
   - Act: Execute the code being tested
   - Assert: Verify the expected outcome
4. **Mock external dependencies** (MQTT client, file I/O, etc.)
5. **Test both success and failure cases**

### Example Test Structure

```python
@patch('mqtt_filter.mqtt.Client')
def test_feature_name(self, mock_client_class):
    """Test description of what this test verifies"""
    # Arrange
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    filter_service = MeshtasticMQTTFilter(
        broker="test.mqtt.com",
        port=1883,
        input_topic="msh/test/#",
        output_topic="filtered/test"
    )

    # Act
    result = filter_service.some_method()

    # Assert
    assert result == expected_value
    assert mock_client.some_method.called
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. The pytest.ini configuration ensures:
- Coverage reporting
- Clear test output
- Proper test discovery

## Troubleshooting

### Import Errors

If you see import errors, make sure you're running pytest from the project root:

```bash
cd /path/to/meshtastic-oktomqtt-filter
pytest
```

### Mock Issues

If mocks aren't working as expected, verify:
- You're patching the correct module path
- Mocks are set up before the code under test runs
- Return values are configured correctly

### Coverage Not Showing

Make sure you have pytest-cov installed:

```bash
pip install pytest-cov
```

## Future Test Additions

Consider adding tests for:
- Decryption functionality with actual encrypted packets
- Key derivation for different channel names
- Daemon mode initialization
- Performance testing with high message volumes
