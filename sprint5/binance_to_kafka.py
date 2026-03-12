# -*- coding: utf-8 -*-

import json
from datetime import datetime, timezone

from binance import Client, ThreadedWebsocketManager
from kafka import KafkaProducer

# =========================
# CONFIGURACION
# =========================
BOOTSTRAP_SERVERS = "51.49.235.244:9092"
USERNAME = "kafka_client"
PASSWORD = "88b8a35dca1a04da57dc5f3e"
TOPIC = "imat3a-AVAX"

SYMBOL = "AVAXUSDT"
INTERVAL = Client.KLINE_INTERVAL_1MINUTE


# =========================
# KAFKA PRODUCER
# =========================
producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    security_protocol="SASL_PLAINTEXT",
    sasl_mechanism="PLAIN",
    sasl_plain_username=USERNAME,
    sasl_plain_password=PASSWORD,
    key_serializer=lambda v: v.encode("utf-8"),
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)


def ms_to_utc_z(ms: int) -> str:
    """
    Convierte milisegundos epoch a formato:
    2026-03-09T11:21:00Z
    """
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_kline(msg):
    """
    Estructura del mensaje Binance:
    msg['k'] -> datos de la vela
    """
    if "k" not in msg:
        return

    k = msg["k"]

    # x == True => la vela ha cerrado
    is_closed = k["x"]
    if not is_closed:
        return

    symbol = k["s"]               # simbolo
    close_price = float(k["c"])   # cierre
    volume = float(k["v"])        # volumen
    close_time_ms = int(k["T"])   # timestamp en ms proporcionado por Binance

    payload = {
        "symbol": symbol,
        "@timestamp": ms_to_utc_z(close_time_ms),
        "close": close_price,
        "volume": volume,
        "timestamp_ms": close_time_ms
    }

    print("Enviando a Kafka...")
    print(f"key={symbol} value={payload}")

    producer.send(
        topic=TOPIC,
        key=symbol,   # clave = simbolo de la criptomoneda
        value=payload
    )
    producer.flush()


def main():
    twm = ThreadedWebsocketManager()
    twm.start()

    twm.start_kline_socket(
        symbol=SYMBOL,
        interval=INTERVAL,
        callback=handle_kline
    )

    print(f"Escuchando Binance para {SYMBOL} y publicando en {TOPIC}")
    input("Pulsa ENTER para salir...\n")

    twm.stop()
    producer.close()


if __name__ == "__main__":
    main()