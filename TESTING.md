# Testing Guide for Meshtastic MQTT Filter

## Overview

This document provides a comprehensive guide to the test suite for the Meshtastic MQTT Filter application.

## Test Coverage

The test suite covers the following areas:

### 1. Initialization & Configuration
- Basic filter initialization with default settings
- Initialization with MQTT credentials
- Custom encryption key handling
- Reject logging configuration

### 2. Exempt Node Functionality
- **Multiple Format Support**: Tests parsing of node IDs in various formats
  - Hex with prefix: `0x12345678`, `0xABCDEF01`
  - Meshtastic format: `!12345678`, `!abcdef01`
  - Decimal format: `305419896`
- **Invalid Format Handling**: Gracefully handles invalid node ID formats
- **Exemption Logic**: Verifies exempt nodes bypass all filtering rules
- **Statistics Tracking**: Ensures exempt forwards are counted separately

### 3. Message Filtering Logic
- **Bitfield Checking**:
  - Messages with "Ok to MQTT" bitfield (0x01) are forwarded
  - Messages without bitfield are rejected
  - `allow_no_bitfield` flag allows legacy firmware support
- **Encryption Handling**: Encrypted packets without decoded data are rejected
- **Exempt Node Bypass**: Exempt nodes are forwarded regardless of bitfield status

### 4. Message Processing Pipeline
- **End-to-End Processing**: Full message flow from MQTT input to filtered output
- **Topic Mapping**: Input topic prefix correctly replaced with output prefix
- **Statistics Tracking**: All message outcomes properly tracked
- **Error Handling**: Malformed messages handled gracefully

### 5. MQTT Connection Management
- **Connection Success**: Proper subscription on successful connection
- **Connection Failure**: Graceful handling of connection failures
- **Disconnection**: Both expected and unexpected disconnects handled

## Test Structure

```
tests/
├── __init__.py                   # Package init
├── conftest.py                   # Shared fixtures
│   ├── mock_mqtt_client()       # Mock MQTT client
│   ├── sample_mesh_packet()     # Sample decoded packet
│   ├── sample_encrypted_packet() # Sample encrypted packet
│   ├── sample_service_envelope() # Sample ServiceEnvelope
│   └── default_longfast_key()   # Default encryption key
├── test_mqtt_filter.py          # Unit tests (200+ lines)
│   ├── TestMeshtasticMQTTFilterInit
│   ├── TestExemptNodes
│   ├── TestCheckOkToMQTT
│   ├── TestStatistics
│   ├── TestCustomEncryptionKeys
│   └── TestRejectLogging
└── test_message_processing.py  # Integration tests (150+ lines)
    ├── TestMessageProcessing
    ├── TestConnectionHandling
    └── TestErrorHandling
```

## Running Tests

### Quick Start

```bash
# From project root
cd /path/to/meshtastic-oktomqtt-filter

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=mqtt_filter --cov-report=term-missing
```

### Specific Test Execution

```bash
# Run only unit tests
pytest tests/test_mqtt_filter.py

# Run only integration tests
pytest tests/test_message_processing.py

# Run a specific test class
pytest tests/test_mqtt_filter.py::TestExemptNodes

# Run a specific test
pytest tests/test_mqtt_filter.py::TestExemptNodes::test_exempt_node_hex_format

# Run tests matching a pattern
pytest -k "exempt"
```

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=mqtt_filter --cov-report=html

# Open in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Test Scenarios

### Scenario 1: Exempt Node Message Forwarding

**Test**: `test_forward_exempt_node_message`

**Setup**:
- Filter configured with exempt node `0x12345678`
- Message from exempt node with bitfield disabled (0x00)

**Expected**:
- Message IS forwarded despite disabled bitfield
- `forwarded_exempt` counter incremented
- `forwarded` counter incremented

### Scenario 2: Standard Message Filtering

**Test**: `test_forward_valid_message`

**Setup**:
- Message with "Ok to MQTT" bitfield enabled (0x01)

**Expected**:
- Message forwarded to output topic
- Topic prefix correctly replaced
- `forwarded` counter incremented

### Scenario 3: Rejection Tracking

**Test**: `test_statistics_tracking`

**Setup**:
- Process 4 messages with different outcomes

**Expected**:
- `total`: 4
- `forwarded`: 3 (2 valid + 1 exempt)
- `forwarded_exempt`: 1
- `rejected_bitfield_disabled`: 1

## Continuous Integration

### GitHub Actions Workflow

The project includes a GitHub Actions workflow (`.github/workflows/test.yml`) that:

1. **Runs tests on multiple Python versions** (3.9, 3.10, 3.11)
2. **Generates coverage reports**
3. **Uploads to Codecov** (optional)
4. **Runs linting** with flake8

The workflow triggers on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

### Local CI Simulation

```bash
# Test on multiple Python versions locally (requires pyenv or similar)
for version in 3.9 3.10 3.11; do
    python$version -m pytest
done

# Run linting
flake8 mqtt_filter.py --max-line-length=120
```

## Writing New Tests

### Test Template

```python
@patch('mqtt_filter.mqtt.Client')
def test_new_feature(self, mock_client_class):
    """Test description"""
    # Arrange
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    filter_service = MeshtasticMQTTFilter(
        broker="test.mqtt.com",
        port=1883,
        input_topic="msh/test/#",
        output_topic="filtered/test",
        # Add feature-specific config
    )

    # Act
    result = filter_service.method_to_test()

    # Assert
    assert result == expected
```

### Best Practices

1. **Use descriptive test names** that explain the scenario
2. **Follow Arrange-Act-Assert** pattern
3. **Mock external dependencies** (MQTT client, file I/O)
4. **Test both success and failure paths**
5. **Keep tests independent** - no shared state between tests
6. **Use fixtures** for common test data

## Test Maintenance

### When to Update Tests

- **Adding new features**: Add corresponding tests
- **Fixing bugs**: Add regression test
- **Changing behavior**: Update affected tests
- **Refactoring**: Ensure tests still pass

### Coverage Goals

- **Target**: >80% code coverage
- **Critical paths**: 100% coverage for filtering logic
- **Edge cases**: All error paths tested

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure you're in the project root
cd /path/to/meshtastic-oktomqtt-filter
pytest
```

**Mock Not Working**:
```python
# Patch at the point of use, not definition
@patch('mqtt_filter.mqtt.Client')  # Correct
# Not: @patch('paho.mqtt.client.Client')
```

**Fixture Not Found**:
```bash
# Ensure conftest.py is in tests/ directory
ls tests/conftest.py
```

## Future Test Additions

Consider adding tests for:

1. **Decryption Testing**
   - Test with actual encrypted packets
   - Verify key derivation for different channels
   - Test multi-key decryption attempts

2. **Performance Testing**
   - High-volume message processing
   - Memory usage under load
   - Decryption performance

3. **End-to-End Testing**
   - Real MQTT broker integration
   - Actual Meshtastic device messages
   - Full Docker container testing

4. **Security Testing**
   - Invalid/malicious protobuf data
   - Very large messages
   - Resource exhaustion scenarios

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Meshtastic Protobuf Definitions](https://github.com/meshtastic/protobufs)
- [Project README](README.md)
- [Test Suite README](tests/README.md)
