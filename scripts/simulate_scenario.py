#!/usr/bin/env python3
"""Simulate MQTT messages for all five EaseAgent modules.

Usage
-----
    python scripts/simulate_scenario.py             # run all scenarios
    python scripts/simulate_scenario.py --scene co2  # CO2 alert only
    python scripts/simulate_scenario.py --scene toilet
    python scripts/simulate_scenario.py --scene vacancy
    python scripts/simulate_scenario.py --scene sensor
    python scripts/simulate_scenario.py --scene heartbeat
"""

from __future__ import annotations

import argparse
import json
import time

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
PREFIX = "easeagent"


def _pub(client: mqtt.Client, topic: str, payload: dict) -> None:
    msg = json.dumps(payload)
    client.publish(topic, msg)
    print(f"  -> {topic}  {msg}")


def scene_sensor(client: mqtt.Client) -> None:
    """Simulate sensor data from zone_a."""
    print("\n=== Sensor Data ===")
    _pub(client, f"{PREFIX}/zone_a/sensor/env_01/data", {
        "temperature": 26.5,
        "humidity": 55,
        "co2": 650,
        "light": 420,
    })
    time.sleep(1)
    _pub(client, f"{PREFIX}/meeting_1/sensor/env_02/data", {
        "temperature": 24.0,
        "humidity": 48,
        "co2": 520,
        "light": 300,
    })


def scene_co2(client: mqtt.Client) -> None:
    """Simulate CO2 exceeding threshold (triggers reflex fresh air)."""
    print("\n=== CO2 High Alert ===")
    _pub(client, f"{PREFIX}/zone_a/sensor/env_01/data", {
        "temperature": 27.0,
        "humidity": 60,
        "co2": 1200,
        "light": 350,
    })


def scene_toilet(client: mqtt.Client) -> None:
    """Simulate toilet door sensor state changes."""
    print("\n=== Toilet Sensors ===")
    _pub(client, f"{PREFIX}/toilet_3f_m/toilet/3F_M_01/status", {"occupied": True})
    time.sleep(0.5)
    _pub(client, f"{PREFIX}/toilet_3f_m/toilet/3F_M_02/status", {"occupied": False})
    time.sleep(0.5)
    _pub(client, f"{PREFIX}/toilet_3f_f/toilet/3F_F_01/status", {"occupied": True})
    time.sleep(2)
    print("  (stall 01 becomes vacant)")
    _pub(client, f"{PREFIX}/toilet_3f_m/toilet/3F_M_01/status", {"occupied": False})


def scene_heartbeat(client: mqtt.Client) -> None:
    """Simulate device heartbeats for various device types."""
    print("\n=== Device Heartbeats ===")
    devices = [
        ("zone_a", "light_a1", "light"),
        ("zone_a", "ac_a1", "ac"),
        ("zone_a", "fa_a1", "fresh_air"),
        ("zone_a", "curtain_a1", "curtain"),
        ("entrance", "screen_entrance", "screen"),
        ("meeting_1", "light_m1", "light"),
        ("meeting_1", "ac_m1", "ac"),
    ]
    for room_id, dev_id, dev_type in devices:
        _pub(client, f"{PREFIX}/{room_id}/{dev_id}/heartbeat", {
            "device_id": dev_id,
            "device_type": dev_type,
            "room_id": room_id,
            "status": "online",
        })
        time.sleep(0.2)


def scene_vacancy(client: mqtt.Client) -> None:
    """Simulate a person entering and then leaving (for reflex vacancy test).

    NOTE: person_entered / person_left events are normally published by
    the PerceptionPipeline via the EventBus, not MQTT.  This scenario
    publishes sensor data that could be used for testing the sensor
    collector, but the actual reflex trigger requires EventBus events.
    Use the WebSocket console or direct API calls to test reflex timers.
    """
    print("\n=== Vacancy Scenario (sensor data only) ===")
    print("  Note: reflex timers are triggered by EventBus, not MQTT.")
    print("  This sends sensor data to show the environment state.")
    _pub(client, f"{PREFIX}/zone_a/sensor/env_01/data", {
        "temperature": 25.0,
        "humidity": 50,
        "co2": 500,
        "light": 400,
    })


def scene_full(client: mqtt.Client) -> None:
    """Run all scenarios in sequence."""
    scene_heartbeat(client)
    time.sleep(1)
    scene_sensor(client)
    time.sleep(1)
    scene_co2(client)
    time.sleep(1)
    scene_toilet(client)
    time.sleep(1)
    scene_vacancy(client)


SCENES = {
    "sensor": scene_sensor,
    "co2": scene_co2,
    "toilet": scene_toilet,
    "heartbeat": scene_heartbeat,
    "vacancy": scene_vacancy,
    "all": scene_full,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="EaseAgent MQTT scenario simulator")
    parser.add_argument(
        "--scene",
        choices=list(SCENES.keys()),
        default="all",
        help="Which scenario to simulate (default: all)",
    )
    parser.add_argument("--host", default=BROKER, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=PORT, help="MQTT broker port")
    args = parser.parse_args()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="easeagent-simulator",
    )
    client.connect(args.host, args.port, 60)
    client.loop_start()

    print(f"Connected to MQTT broker at {args.host}:{args.port}")

    try:
        SCENES[args.scene](client)
    finally:
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        print("\nDone.")


if __name__ == "__main__":
    main()
