# -*- coding: utf-8 -*-

import json
from kafka import KafkaConsumer

# =========================
# CONFIGURACION
# =========================
BOOTSTRAP_SERVERS = "51.49.235.244:9092"
USERNAME = "kafka_client"
PASSWORD = "88b8a35dca1a04da57dc5f3e"
TOPIC = "imat3a-AVAX"
GROUP_ID = "imat3a_group03"


def main() -> None:
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        security_protocol="SASL_PLAINTEXT",
        sasl_mechanism="PLAIN",
        sasl_plain_username=USERNAME,
        sasl_plain_password=PASSWORD,
        group_id=GROUP_ID,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        key_deserializer=lambda v: v.decode("utf-8") if v else None,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None,
    )

    print(f"Escuchando mensajes en tiempo real del topic: {TOPIC}\n")

    try:
        for message in consumer:
            print("Nuevo mensaje recibido")
            print(f"topic:      {message.topic}")
            print(f"partition:  {message.partition}")
            print(f"offset:     {message.offset}")
            print(f"key:        {message.key}")
            print(f"value:      {message.value}")
            print(f"timestamp:  {message.timestamp}")
            print("-" * 50)
    except KeyboardInterrupt:
        print("\nCerrando consumer...")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()