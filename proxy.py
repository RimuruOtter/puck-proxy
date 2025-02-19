import socketio
import asyncio
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Socket.IO server and client instances
sio_server = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
sio_client = socketio.AsyncClient()

# Create web application
from aiohttp import web
app = web.Application()
sio_server.attach(app)

# Store client session IDs
clients = {}

@sio_client.event
async def connect():
    logger.info("Connected to target server")

@sio_client.event
async def disconnect():
    logger.info("Disconnected from target server")

@sio_server.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    if not sio_client.connected:
        await sio_client.connect('http://puck1.nasejevs.com:8080')
    clients[sid] = True

@sio_server.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    clients.pop(sid, None)
    if not clients:
        await sio_client.disconnect()

@sio_server.event
async def server_authenticate(sid, data):
    logger.info("Intercepted server_authenticate")
    logger.info(f"Original data: {data}")
    
    # Modify the ports
    if isinstance(data, dict):
        data['port'] = 7777
        data['ping_port'] = 7778
    
    logger.info(f"Modified data: {data}")
    
    # Forward to target server
    await sio_client.emit('server_authenticate', data)

# Catch all other events
@sio_server.event
async def catch_all(event, sid, *args):
    if event not in ['connect', 'disconnect', 'server_authenticate']:
        logger.info(f"Forwarding event: {event}")
        await sio_client.emit(event, *args)

@sio_client.event
def catch_all(event, *args):
    if event not in ['connect', 'disconnect']:
        logger.info(f"Received from server: {event}")
        asyncio.create_task(sio_server.emit(event, *args))

async def init_app():
    return app

if __name__ == '__main__':
    logger.info("Starting Socket.IO proxy server...")
    web.run_app(init_app(), host='0.0.0.0', port=8081)