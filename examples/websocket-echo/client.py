#!/usr/bin/env python3
import asyncio
import websockets
import json
import time

async def test_websocket():
    uri = "ws://localhost:8765"

    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        # Test 1: Send plain text echo
        print("\n1. Testing plain text echo...")
        await websocket.send("Hello WebSocket!")
        response = await websocket.recv()
        print(f"Response: {response}")

        # Test 2: Send JSON echo
        print("\n2. Testing JSON echo...")
        echo_msg = {"type": "echo", "message": "Hello from JSON"}
        await websocket.send(json.dumps(echo_msg))
        response = await websocket.recv()
        print(f"Response: {response}")

        # Test 3: Send ping
        print("\n3. Testing ping/pong...")
        ping_msg = {"type": "ping", "timestamp": int(time.time())}
        await websocket.send(json.dumps(ping_msg))
        response = await websocket.recv()
        print(f"Response: {response}")

        # Test 4: Send unknown type
        print("\n4. Testing error handling...")
        unknown_msg = {"type": "unknown", "data": "test"}
        await websocket.send(json.dumps(unknown_msg))
        response = await websocket.recv()
        print(f"Response: {response}")

        print("\nAll tests completed!")

if __name__ == "__main__":
    asyncio.run(test_websocket())