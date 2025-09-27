#!/usr/bin/env python3
import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_websocket(websocket, path):
    client_addr = websocket.remote_address
    logger.info(f"New WebSocket connection from {client_addr}")

    try:
        async for message in websocket:
            logger.info(f"Received: {message}")

            try:
                data = json.loads(message)
                msg_type = data.get("type", "echo")

                if msg_type == "ping":
                    response = {"type": "pong", "timestamp": data.get("timestamp", 0)}
                    await websocket.send(json.dumps(response))
                    logger.info(f"Sent pong response")

                elif msg_type == "echo":
                    response = {"type": "echo", "message": data.get("message", "")}
                    await websocket.send(json.dumps(response))
                    logger.info(f"Echoed message: {data.get('message', '')}")

                else:
                    response = {"type": "error", "message": f"Unknown type: {msg_type}"}
                    await websocket.send(json.dumps(response))

            except json.JSONDecodeError:
                # Plain text echo
                await websocket.send(f"Echo: {message}")
                logger.info(f"Echoed plain text: {message}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Connection closed from {client_addr}")
    except Exception as e:
        logger.error(f"Error handling connection from {client_addr}: {e}")

async def main():
    port = 8765
    logger.info(f"Starting WebSocket server on port {port}")

    async with websockets.serve(handle_websocket, "0.0.0.0", port):
        logger.info(f"Server listening on ws://0.0.0.0:{port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())