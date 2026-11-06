"""
Connection test script - run this on the Raspberry Pi to verify
that it can reach the MQTT broker before starting the full rover client.

Usage:
    python3 test_connection.py --broker 192.168.0.109
"""
import sys, json, time, argparse
import paho.mqtt.client as mqtt

parser = argparse.ArgumentParser(description="Test MQTT connectivity to AgriTech backend")
parser.add_argument("--broker", default="192.168.0.109", help="Backend server LAN IP")
parser.add_argument("--port", type=int, default=1883)
parser.add_argument("--rover-id", default="ROVER-4WD-01")
args = parser.parse_args()

connected = False
received  = False

def on_connect(c, u, f, rc):
    global connected
    if rc == 0:
        connected = True
        print(f"[OK] Connected to MQTT broker at {args.broker}:{args.port}")
        topic = f"agritech/rover/{args.rover_id}/command"
        c.subscribe(topic, qos=1)
        print(f"[OK] Subscribed to: {topic}")
        tel_topic = f"agritech/rover/{args.rover_id}/telemetry"
        c.publish(tel_topic, json.dumps({
            "rover_id": args.rover_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": {
                "rover_id": args.rover_id,
                "rover_status": "TEST",
                "battery_pct": 99.0,
                "speed_kmh": 0.0,
                "latitude": 17.385,
                "longitude": 78.4867,
            }
        }))
        print(f"[OK] Test telemetry published to: {tel_topic}")
        print("\nWaiting 5 seconds for any incoming commands...")
    else:
        print(f"[FAIL] Connection refused: rc={rc}")
        sys.exit(1)

def on_message(c, u, msg):
    global received
    received = True
    payload = json.loads(msg.payload.decode())
    print(f"[OK] Received command: {payload}")

def on_disconnect(c, u, rc):
    print(f"[INFO] Disconnected rc={rc}")

client = mqtt.Client(client_id="AgriTechConnectionTest")
client.on_connect    = on_connect
client.on_message    = on_message
client.on_disconnect = on_disconnect

print(f"Connecting to {args.broker}:{args.port} ...")
try:
    client.connect(args.broker, args.port, keepalive=10)
except Exception as e:
    print(f"[FAIL] Cannot connect: {e}")
    sys.exit(1)

client.loop_start()
time.sleep(6)
client.loop_stop()
client.disconnect()

print()
if connected:
    print("[PASS] MQTT connectivity test PASSED.")
    print("[INFO] You are ready to run: python3 pi_rover.py")
else:
    print("[FAIL] Connection was not established.")