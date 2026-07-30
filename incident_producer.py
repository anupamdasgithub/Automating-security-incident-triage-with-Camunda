"""
Simulated SOC event source. Publishes a structured incident event to the
Kafka topic that the Camunda inbound connector subscribes to. Each message
starts one process instance with incident_topic already populated.

This stands in for a real SIEM/normalizer. Topics here are synthetic labels;
the downstream stub returns synthetic fixtures regardless.

Usage:
  pip install kafka-python --break-system-packages
  python3 incident_producer.py                 # sends one default event
  python3 incident_producer.py ISO_GDPR         # sends a specific scenario
  python3 incident_producer.py --list           # show scenario keys
"""
import json
import sys
import uuid
from datetime import datetime, timezone

try:
    from kafka import KafkaProducer
except ImportError:
    sys.exit("Missing dependency. Run: pip install kafka-python --break-system-packages")

BOOTSTRAP = "localhost:9092"   # EXTERNAL listener exposed to the Mac
TOPIC = "security-events"

# Synthetic scenario labels -> incident_topic string.
# These mirror the scenario_type choices the form used, so the same
# downstream routing applies. Values are plain labels; the stub returns
# TEST FIXTURE alerts keyed off them.
SCENARIOS = {
    "ISO":            "Verdaechtige Scanaktivitaet aus externem Netzwerk erkannt",
    "ISO_IGNORE":     "Geplanter externer Security Scan, vorab genehmigt und dokumentiert",
    "ISO_THREAT":     "Verdacht auf Proxy/VPN-Traffic von externer IP 198.51.100.45",
    "ISO_GDPR":       "Unbefugter Zugriff auf eine Kundendatenbank mit personenbezogenen Daten",
    "ISO_GDPR_Asset": "Verdacht auf Datenabfluss aus CRM-System TEST-CRM-02",
    "ISO_THREAT_ASSET": "Mehrere Verbindungen von 198.51.100.46 gegen mehrere interne Systeme",
    "ISO_ASSET":      "Authentifizierungsserver TEST-AUTH-01 zeigt ungewoehnliche CPU-Spitzen",
    "FULL":           "Wiederholte Zugriffe von 198.51.100.46 auf TEST-DB-02, Injection-Muster",
}


def build_event(scenario_key: str) -> dict:
    topic_text = SCENARIOS.get(scenario_key, SCENARIOS["FULL"])
    return {
        "eventId": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_type": scenario_key,
        "incident_topic": topic_text,
        "source": "synthetic-producer",
    }


def main():
    args = [a for a in sys.argv[1:]]
    if "--list" in args:
        print("Available scenario keys:")
        for k in SCENARIOS:
            print("  ", k)
        return

    scenario = args[0] if args else "FULL"
    event = build_event(scenario)

    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    future = producer.send(TOPIC, event)
    meta = future.get(timeout=10)
    producer.flush()
    print(f"Published to {meta.topic} [partition {meta.partition}] offset {meta.offset}")
    print(json.dumps(event, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
