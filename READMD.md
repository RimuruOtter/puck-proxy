# Overview
The system works in two parts:
1. Intercepting the websocket call to `http://puck1.nasejevs.com:8080` on server registration.
2. A middleman script which allows or blocks users from passing to the server.

## Intercepting the server registration packet
When the server starts up, it connects to the central server, `http://puck1.nasejevs.com:8080`, to allow players to discover the server.

The central server is a simple `socket.io` server thankfully which means its just a websocket.

When the server registers, the packet looks like this:
```json
{"token": null, "port": 7770, "ping_port": 7771, "name": "...", "max_players": 12, "password": "", "launched_by_steam_id": null}
```

It's here that we intercept this packet from the server and change the `port` and `ping_port` to `7777` and `7778`.

Thus this allows the middleman script to take over the packets being sent to the server.

## Banning / Blocking
Pretty simiply, we just use scapy to allow or block players from joining based on SteamID. The middleman script also acts as a server console with commands like `ban` and `unban`. Etc.
```
ban Otter
ban 76561198318540661
ban 127.0.0.1 (Client IP)
```
No matter which one you input, it will translate it to the user's SteamID.

# Setup
```bash
# Backup IPTables before modifying
sudo iptables-save > iptables-backup

sudo useradd -r proxy_user # This prevents the script from being blocked from the ip_tables rules

sudo iptables -t nat -A OUTPUT -p tcp -d puck1.nasejevs.com --dport 8080 -m owner ! --uid-owner $(id -u proxy_user) -j REDIRECT --to-port 8081
sudo iptables -t nat -A PREROUTING -p tcp -d puck1.nasejevs.com --dport 8080 -j REDIRECT --to-port 8081

pip install -r requirements.txt

# YOU HAVE TO RUN THIS BEFORE THE SERVER STARTS
sudo -u proxy_user python3 proxy.py
python3 middleman.py

# Once the proxy and middleman is running, you can restart the server as much as you want without having to reload the scripts.

# Now you can start you server, make sure to change the port to 7770.
./Puck.x86_64 --port 7770 --name "..." --max_players 12 --voip "true"
```

#### Funny Note
Puck can run on `ARM64` servers using `FEXEmu`

# Restore / Stop Redirect
```bash
sudo iptables-restore < iptables-backup

# OR

# Same commands as before but with -D flag instead of -A for delete.
sudo iptables -t nat -D OUTPUT -p tcp -d puck1.nasejevs.com --dport 8080 -m owner ! --uid-owner $(id -u proxy_user) -j REDIRECT --to-port 8081
sudo iptables -t nat -D PREROUTING -p tcp -d puck1.nasejevs.com --dport 8080 -j REDIRECT --to-port 8081
```