import socket
import threading
import select
import re
import time

# Configuration for the two proxy pairs
CONFIG = [
    {"proxy_port": 7777, "app_ip": "127.0.0.1", "app_port": 7770},
    {"proxy_port": 7778, "app_ip": "127.0.0.1", "app_port": 7771},
]

BUFFER_SIZE = 4096
BANNED_IPS = set()  # Use a set for quick lookups
BANNED_IDS = set()
GAME_PORT = 7777  # Only apply bans on this port
ACTIVE_CLIENTS = set()  # Tracks active clients {ip: (addr, last_activity_time)}
PING_CLIENTS = set()
PLAYERS = {}  # {steamid: {"name": player_name, "ip": player_ip}}
NAME_TO_STEAMID = {}  # {name: steamid}
IP_TO_STEAMID = {}    # {ip: steamid}
CLIENT_TO_STEAMID = {}  # {client_addr: steamid}

# Heartbeat configuration
HEARTBEAT_TIMEOUT = 30  # Seconds before considering a client disconnected
CLIENT_ACTIVITY = {}  # {client_addr: last_activity_timestamp}

signature = bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00])

def check_signature(data):
    return signature in data

def remove_player(steamid):
    """Remove a player from all tracking dictionaries."""
    if steamid in PLAYERS:
        player_info = PLAYERS[steamid]
        player_name = player_info["name"]
        player_ip = player_info["ip"]
        
        print(f"[SERVER] Player Left: {player_name} ({steamid})")
        
        # Remove from all tracking dictionaries
        PLAYERS.pop(steamid, None)
        NAME_TO_STEAMID.pop(player_name, None)
        IP_TO_STEAMID.pop(player_ip, None)
        
        # Remove from CLIENT_TO_STEAMID (need to find and remove all instances)
        clients_to_remove = [client for client, sid in CLIENT_TO_STEAMID.items() if sid == steamid]
        for client in clients_to_remove:
            CLIENT_TO_STEAMID.pop(client, None)

def process_player(byte_array, client_ip, client_addr):
    data = byte_array[62:]
    name, steamid = clean(data)

    if not name or not steamid:
        return

    # Store player info
    PLAYERS[steamid] = {"name": name, "ip": client_ip}
    NAME_TO_STEAMID[name] = steamid  # Map name to steamid
    IP_TO_STEAMID[client_ip] = steamid  # Map IP to steamid
    CLIENT_TO_STEAMID[client_addr] = steamid  # Map client address to steamid
    
    # Check if player should be banned
    if steamid in BANNED_IDS:
        print(f"[Proxy] Blocking player {name} ({steamid}) from IP {client_ip}")
        return False  # Indicate that the player is banned
    
    print(f"[SERVER] Player Joined: {name} ({steamid})")
    
    return True  # Indicate that the player is allowed

def clean(binary_data):
    # Replace all non-printable characters with spaces
    cleaned_text = re.sub(rb'[\x00-\x1F\x7F-\x9F]', b' ', binary_data).decode(errors='ignore')
    # Normalize multiple spaces to a single space and strip leading/trailing spaces
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    # Split into an array
    text_array = cleaned_text.split(' ')
    
    # Extract the name (first element)
    name = text_array[0] if text_array else None

    # Find a 17-character-long number
    number_17_digits = next((item for item in text_array if item.isdigit() and len(item) == 17), None)

    return name, number_17_digits

def is_ip_banned(ip):
    """Check if an IP is banned."""
    try:
        user = IP_TO_STEAMID[ip]
        return user in BANNED_IDS
    except KeyError:
        return False

def check_client_timeouts():
    """Check for clients that haven't sent packets within the timeout period."""
    while True:
        current_time = time.time()
        disconnected_clients = set()

        # Check all clients for timeout
        for client in list(CLIENT_ACTIVITY.keys()):
            if current_time - CLIENT_ACTIVITY[client] > HEARTBEAT_TIMEOUT:
                print(f"[Heartbeat] Client {client} timed out after {HEARTBEAT_TIMEOUT} seconds")
                disconnected_clients.add(client)
        
        # Remove timed out clients
        for client in disconnected_clients:
            # If the client is associated with a player, remove the player
            if client in CLIENT_TO_STEAMID:
                steamid = CLIENT_TO_STEAMID[client]
                remove_player(steamid)

            CLIENT_ACTIVITY.pop(client, None)
            ACTIVE_CLIENTS.discard(client)
            if client in PING_CLIENTS:
                PING_CLIENTS.discard(client)
        
        time.sleep(3)  # Check every 5 seconds

def udp_proxy(proxy_port, app_ip, app_port):
    """Runs a UDP proxy that forwards packets, enforcing bans on the game port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', proxy_port))
    print(f"[Proxy {proxy_port}] Listening and forwarding to {app_ip}:{app_port}")

    SERVER = (app_ip, app_port)
    
    while True:
        readable, _, _ = select.select([sock], [], [])
        for s in readable:
            data, addr = s.recvfrom(BUFFER_SIZE)
            client_ip = addr[0]

            CLIENT = addr

            IS_SERVER = addr[0] == app_ip
            IS_CLIENT = addr[0] != app_ip

            # Client -> Server (ping)
            if IS_CLIENT and data == b"ping":
                PING_CLIENTS.add(CLIENT)
                sock.sendto(data, SERVER)
                continue

            # Server -> Client (ping)
            if IS_SERVER and addr[1] == 7771:
                for ping in list(PING_CLIENTS):
                    sock.sendto(data, ping)
                PING_CLIENTS.clear()
                continue

            # Update client activity timestamp for any non-ping packet from client
            if IS_CLIENT:
                CLIENT_ACTIVITY[addr] = time.time()

            # Enforce Ban Logic
            if check_signature(data):
                process_player(data, client_ip, CLIENT)

            if is_ip_banned(client_ip):
                continue

            # Client -> Server (game)
            if IS_CLIENT:
                if addr not in ACTIVE_CLIENTS:
                    ACTIVE_CLIENTS.add(addr)
                sock.sendto(data, SERVER)
                continue

            # Server -> Client (game)
            if IS_SERVER:
                for client in list(ACTIVE_CLIENTS):
                    sock.sendto(data, client)
                continue

def ban_player(identifier):
    """Ban a player by SteamID, Name, or IP."""
    if identifier in PLAYERS:
        steamid = identifier
    elif identifier in NAME_TO_STEAMID:
        steamid = NAME_TO_STEAMID[identifier]
    elif identifier in IP_TO_STEAMID:
        steamid = IP_TO_STEAMID[identifier]
    else:
        print(f"[ADMIN] {identifier} not found in player records.")
        return
    
    BANNED_IDS.add(steamid)  # Ban by SteamID
    print(f"[ADMIN] Player with identifier {identifier} (SteamID: {steamid}) has been banned.")

def unban_player(identifier):
    """Unban a player by SteamID, Name, or IP."""
    if identifier in PLAYERS:
        steamid = identifier
    elif identifier in NAME_TO_STEAMID:
        steamid = NAME_TO_STEAMID[identifier]
    elif identifier in IP_TO_STEAMID:
        steamid = IP_TO_STEAMID[identifier]
    else:
        print(f"[ADMIN] {identifier} not found in player records.")
        return
    
    BANNED_IDS.discard(steamid)  # Unban by SteamID
    print(f"[ADMIN] Player with identifier {identifier} (SteamID: {steamid}) has been unbanned.")

def command_listener():
    """Listens for admin commands to ban/unban players by Name, SteamID, or IP."""
    while True:
        command = input().strip()
        parts = command.split()

        if len(parts) < 2:
            print("Invalid command. Use 'ban <name|steamid|ip>' or 'unban <name|steamid|ip>'")
            continue

        action, identifier = parts[0].lower(), " ".join(parts[1:])

        if action == "ban":
            ban_player(identifier)

        elif action == "unban":
            unban_player(identifier)

        else:
            print("Unknown command. Use 'ban <name|steamid|ip>' or 'unban <name|steamid|ip>'")

def start_proxy_services():
    """Starts the UDP proxy threads and the command listener."""
    threads = []

    # Start UDP proxies
    for conf in CONFIG:
        t = threading.Thread(target=udp_proxy, args=(conf["proxy_port"], conf["app_ip"], conf["app_port"]), daemon=True)
        t.start()
        threads.append(t)

    # Start heartbeat checker
    heartbeat_thread = threading.Thread(target=check_client_timeouts, daemon=True)
    heartbeat_thread.start()
    threads.append(heartbeat_thread)

    # Start command listener
    cmd_thread = threading.Thread(target=command_listener, daemon=True)
    cmd_thread.start()
    threads.append(cmd_thread)

    print("UDP proxy services, heartbeat checker, and admin command listener are running...")
    
    for t in threads:
        t.join()

if __name__ == '__main__':
    start_proxy_services()