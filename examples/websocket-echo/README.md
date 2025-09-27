# WebSocket Echo Service

Simple WebSocket service that supports:
- Plain text echo
- JSON-based ping/pong
- JSON message echo

## Installation

```bash
pip install -r requirements.txt
```

## Running the Server

```bash
python3 server.py
```

Server listens on port 8765.

## Testing with Client

```bash
python3 client.py
```

## Message Format

### Plain Text
Send any plain text and receive "Echo: {message}"

### JSON Messages

**Echo:**
```json
{"type": "echo", "message": "your message"}
```

**Ping/Pong:**
```json
{"type": "ping", "timestamp": 1234567890}
```

Response:
```json
{"type": "pong", "timestamp": 1234567890}
```