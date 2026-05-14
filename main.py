from machine import Pin
from time import sleep, ticks_ms, ticks_diff
import network
from umqtt.simple import MQTTClient
import config
import ujson

# Initialize RELAY pin array (GPIO 26~31)
RELAYS = [Pin(pin, Pin.OUT) for pin in range(26, 32)]

# Initialize all relays to the closed state (low level)
def init_relays():
    for relay in RELAYS:
        relay.value(0)  # 0 = OFF, 1 = ON
    print("Relays initialized (OFF)")
    
# Control one relay
def set_relay(relay_num, state):
    if 1 <= relay_num <= len(RELAYS):
        RELAYS[relay_num - 1].value(state)  
        print(f"CH{relay_num} set to {'ON' if state else 'OFF'}")
    else:
        print(f"Error: CH number must be 1~{len(RELAYS)}")

# Control all relays
def set_all_relays(state):
    for i in range(len(RELAYS)):
        RELAYS[i].value(state)
    print(f"ALL CH set to {'ON' if state else 'OFF'}")

# Build relay status snapshot payload
def get_relay_states():
    states = {}
    for i in range(len(RELAYS)):
        states[f"CH{i + 1}"] = RELAYS[i].value()
    return states

# Constants for MQTT Topics
MQTT_SUB_TOPIC = 'rp2350/relay6ch/yuanximing/set'
MQTT_PUB_TOPIC = 'rp2350/relay6ch/yuanximing/state'

# MQTT status payloads
MQTT_STATUS_ONLINE = '{"status":"online"}'
MQTT_STATUS_OFFLINE = '{"status":"offline"}'

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = config.mqtt_port
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = config.mqtt_client_id
MQTT_KEEPALIVE = config.mqtt_keepalive
MQTT_SSL = False  
MQTT_SSL_PARAMS = None
MQTT_SUB_QOS = 1
MQTT_PUB_QOS = 1
MQTT_PING_INTERVAL_MS = (MQTT_KEEPALIVE * 1000) // 2
MQTT_ONLINE_HEARTBEAT_MS = 60000
WIFI_CONNECT_TIMEOUT_S = 10
WIFI_RETRY_ATTEMPTS = 5
WIFI_RETRY_DELAY_MS = 5000
MQTT_RECONNECT_BASE_DELAY_MS = 2000
MQTT_RECONNECT_MAX_DELAY_MS = 30000
last_recv_ms = ticks_ms()

MQTT_ERROR_CODES = {
    1: "unacceptable protocol version",
    2: "identifier rejected",
    3: "server unavailable",
    4: "bad username or password",
    5: "not authorized",
}

def is_no_pending_mqtt_message(error):
    code = error.args[0] if hasattr(error, "args") and error.args else None
    return code == -1 or str(error) == "-1"

# Init Wi-Fi Interface
def initialize_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    for attempt in range(1, WIFI_RETRY_ATTEMPTS + 1):
        # Connect to the network
        wlan.connect(ssid, password)

        # Wait for Wi-Fi connection
        connection_timeout = WIFI_CONNECT_TIMEOUT_S
        while connection_timeout > 0:
            if wlan.status() >= 3:
                print(f'Wi-Fi connected (attempt {attempt})')
                network_info = wlan.ifconfig()
                print('IP address:', network_info[0])
                return True
            connection_timeout -= 1
            print('Waiting for Wi-Fi connection...')
            sleep(1)

        print(f"Wi-Fi attempt {attempt}/{WIFI_RETRY_ATTEMPTS} failed (status {wlan.status()})")
        if attempt < WIFI_RETRY_ATTEMPTS:
            print(f'Retrying Wi-Fi in {WIFI_RETRY_DELAY_MS / 1000:.1f}s')
            wlan.disconnect()
            sleep(WIFI_RETRY_DELAY_MS / 1000)

    print('Error: Wi-Fi connection failed after retries')
    return False

# Connect to MQTT Broker
def mqtt_connect():
    try:
        client = MQTTClient(client_id=MQTT_CLIENT_ID,
                            server=MQTT_SERVER,
                            port=MQTT_PORT,
                            user=MQTT_USER,
                            password=MQTT_PASSWORD,
                            keepalive=MQTT_KEEPALIVE,
                            ssl=MQTT_SSL,
                            ssl_params=MQTT_SSL_PARAMS)
        client.set_last_will(MQTT_PUB_TOPIC, MQTT_STATUS_OFFLINE, retain=True, qos=MQTT_PUB_QOS)
        client.connect()
        print("MQTT connection successful!")
        return client
    except Exception as e:
        code = e.args[0] if hasattr(e, "args") and e.args else None
        if code in MQTT_ERROR_CODES:
            print("Error connecting to MQTT:", code, MQTT_ERROR_CODES[code])
        else:
            print("Error connecting to MQTT:", e)
        return None

# Subcribe to MQTT topics
def mqtt_subscribe(client, topic):
    client.subscribe(topic, qos=MQTT_SUB_QOS)
    print('Subscribe to topic:', topic)

def mqtt_start():
    client = mqtt_connect()
    if client is None:
        raise RuntimeError("MQTT connection failed")
    client.set_callback(mqtt_recv_callback)
    mqtt_subscribe(client, MQTT_SUB_TOPIC)
    mqtt_publish_online(client, "startup")
    if not mqtt_publish_state_snapshot(client, "startup"):
        raise RuntimeError("Failed to publish startup states")
    return client

def mqtt_reconnect(old_client=None):
    print("MQTT reconnecting...")
    backoff_ms = MQTT_RECONNECT_BASE_DELAY_MS
    reconnect_attempt = 0
    if old_client is not None:
        try:
            old_client.disconnect()
        except Exception:
            pass

    while True:
        reconnect_attempt += 1
        print(f"MQTT reconnect attempt #{reconnect_attempt}...")
        try:
            client = mqtt_start()
            print(f"MQTT reconnected successfully (attempt #{reconnect_attempt})")
            return client
        except Exception as e:
            print(f"MQTT reconnect failed (attempt #{reconnect_attempt}):", e)
            sleep(backoff_ms / 1000)
            backoff_ms = min(MQTT_RECONNECT_MAX_DELAY_MS, backoff_ms * 2)
    
# Publish MQTT message
def mqtt_publish(client, topic, message, retain=False, qos=0):
    try:
        client.publish(topic, message, retain=retain, qos=qos)
        print(f"Published: {message} -> {topic}")
        return True
    except Exception as e:
        print("Publish error:", e)
        return False

def mqtt_publish_online(client, reason="heartbeat"):
    print("Online heartbeat:", reason)
    return mqtt_publish(client, MQTT_PUB_TOPIC, MQTT_STATUS_ONLINE, retain=False, qos=MQTT_PUB_QOS)

def mqtt_publish_state_snapshot(client, reason="state"):
    print("State snapshot:", reason)
    payload = ujson.dumps({"data": get_relay_states()})
    return mqtt_publish(client, MQTT_PUB_TOPIC, payload, retain=True, qos=MQTT_PUB_QOS)
    
# Callback function that runs when you receive a message on subscribed topic
def mqtt_recv_callback(topic, message):
    global last_recv_ms
    last_recv_ms = ticks_ms()

    try:
        if topic != MQTT_SUB_TOPIC and topic != MQTT_SUB_TOPIC.encode():
            print(f"Ignore message on unexpected topic: {topic}")
            return

        msg = ujson.loads(message.decode('utf-8'))
        if msg.get("cmd") == "get_state":
            mqtt_publish_state_snapshot(client, "get_state")
            return

        data = msg.get("data", {})
        
        if not data or not isinstance(data, dict):
            print("Error: 'data' field missing")
            return
            
        for key, value in data.items():
            if value not in (0, 1):
                print(f"Error: Value must be 0 or 1, got {value}")
                continue
                
            if key.startswith("CH"):
                relay_num = int(key[2:])
                if 1 <= relay_num <= 6:
                    set_relay(relay_num, value)
                else:
                    print(f"Error: Relay number must be 1-6, got {relay_num}")
            elif key == "ALL":
                set_all_relays(value)
            else:
                print(f"Error: Unknown key '{key}'")

        if mqtt_publish_state_snapshot(client, "command"):
            print("Command state snapshot published")
            
    except ValueError as e:
        print("JSON decode error:", e)
    except Exception as e:
        print("Unexpected error:", e)
    
try:
    # Initialize RELAY
    init_relays()
    # Initialize Wi-Fi
    while not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print(f'Wi-Fi not ready, retrying in {WIFI_RETRY_DELAY_MS / 1000:.1f}s...')
        sleep(WIFI_RETRY_DELAY_MS / 1000)

    # Connect to MQTT broker, start MQTT client
    client = mqtt_start()
    last_ping = ticks_ms()
    last_recv_ms = ticks_ms()

    # Continuously checking for messages
    while True:
        try:
            client.check_msg()
        except OSError as e:
            if is_no_pending_mqtt_message(e):
                pass
            else:
                print("MQTT socket error:", e)
                client = mqtt_reconnect(client)
                last_ping = ticks_ms()
        except Exception as e:
            print("MQTT loop error:", e)
            client = mqtt_reconnect(client)
            last_ping = ticks_ms()

        if ticks_diff(ticks_ms(), last_ping) >= MQTT_PING_INTERVAL_MS:
            try:
                client.ping()
                last_ping = ticks_ms()
            except Exception as e:
                print("MQTT ping error:", e)
                client = mqtt_reconnect(client)
                last_ping = ticks_ms()

        if ticks_diff(ticks_ms(), last_recv_ms) >= MQTT_ONLINE_HEARTBEAT_MS:
            if mqtt_publish_online(client):
                last_recv_ms = ticks_ms()
            else:
                client = mqtt_reconnect(client)
                last_ping = ticks_ms()
                last_recv_ms = ticks_ms()
        sleep(0.1)

except Exception as e:
    print('Error:', e)
