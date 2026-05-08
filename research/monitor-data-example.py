#!/usr/bin/env python3
"""EVT2000SE Live-Monitor – liest alle 30s die aktuellen Werte."""

import socket
import struct
import time
import sys
from datetime import datetime

IP = "192.168.1.100"
PORT = 14889
SERIAL_STR = "A1B2C3D4"   # Seriennummer wie auf dem Gerät aufgedruckt (Hex-Ziffern)
SERIAL = int(SERIAL_STR, 16)
POLL_INTERVAL = 30

FRAME_START = 0x68
CS_SEED = 0x55

WATT_CODE_TO_WATT = {
    0x00: 2000, 0x01: 1200, 0x02: 1440, 0x06: 1600,
    0x07: 1800, 0x09: 600,  0x0A: 800,  0x0B: 1400, 0x0C: 1640,
}


def checksum(data):
    return (sum(data) + CS_SEED) & 0xFF


def build_frame(cmd, serial, payload=b""):
    total_len = 12 + len(payload)
    body = (bytes([FRAME_START])
            + struct.pack(">H", total_len)
            + bytes([FRAME_START])
            + struct.pack(">H", cmd)
            + struct.pack(">I", serial)
            + payload)
    return body + bytes([checksum(body), 0x16])


def encode_tx(frame):
    return frame.hex().upper().encode("ascii")


def recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Verbindung unterbrochen")
        data += chunk
    return data


def receive_frame(sock, timeout=5):
    sock.settimeout(timeout)
    while True:
        b = sock.recv(1)
        if not b:
            return None
        if b[0] == FRAME_START:
            break
    len_bytes = recv_exact(sock, 2)
    total_length = struct.unpack(">H", len_bytes)[0]
    rest = recv_exact(sock, total_length - 3)
    return bytes([FRAME_START]) + len_bytes + rest


def get_cmd(frame):
    return struct.unpack(">H", frame[4:6])[0]


def connect():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((IP, PORT))
    return sock


def read_power_limit():
    """Liest den aktuellen Watt-Code via 0x1041 → 0x1006.
    Öffnet eine eigene Verbindung, bis zu 5 Versuche mit 5s Delay.
    Gibt die Watt-Zahl zurück oder None bei Fehlschlag.
    """
    req = build_frame(0x1041, SERIAL, bytes(10))
    for attempt in range(5):
        if attempt > 0:
            time.sleep(5)
        try:
            sock = connect()
            sock.sendall(encode_tx(req))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                frame = receive_frame(sock, timeout=remaining)
                if frame is None:
                    break
                if get_cmd(frame) == 0x1006 and len(frame) >= 15:
                    sock.close()
                    return WATT_CODE_TO_WATT.get(frame[14])
            sock.close()
        except (ConnectionError, OSError, socket.timeout):
            pass
    return None


def read_live_data(sock):
    """Sendet 0x1077 und wartet auf 0x1051. Gibt Frame zurück oder None."""
    req = build_frame(0x1077, SERIAL, bytes(20))
    sock.sendall(encode_tx(req))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        frame = receive_frame(sock, timeout=remaining)
        if frame is None:
            return None
        cmd = get_cmd(frame)
        if cmd == 0x1051:
            return frame
        # 0x1004 / 0x1006 überspringen
    return None


def parse_frame(frame):
    """Parst 0x1051 und gibt Liste von MI-Dicts zurück."""
    channels = []
    for i in range(4):
        block = frame[20 + i * 32: 20 + (i + 1) * 32]
        uid = struct.unpack(">I", block[0:4])[0]
        dc_v = struct.unpack(">H", block[6:8])[0] * 64 / 32768.0
        ac_w = struct.unpack(">H", block[8:10])[0] * 512 / 32768.0
        kwh = struct.unpack(">I", block[10:14])[0] * 4 / 32768.0
        temp = struct.unpack(">H", block[14:16])[0] * 256 / 32768.0 - 40.0
        ac_v = struct.unpack(">H", block[16:18])[0] * 512 / 32768.0
        freq = struct.unpack(">H", block[18:20])[0] * 128 / 32768.0
        channels.append({
            "mi": i + 1, "uid": uid, "dc_v": dc_v, "ac_w": ac_w,
            "kwh": kwh, "temp": temp, "ac_v": ac_v, "freq": freq
        })
    return channels


def print_data(channels, limit_w=None):
    now = datetime.now().strftime("%H:%M:%S")
    total_w = sum(ch["ac_w"] for ch in channels)
    total_kwh = sum(ch["kwh"] for ch in channels)
    limit_str = f"  │  Limit: {limit_w} W" if limit_w is not None else "  │  Limit: ?"

    print(f"\n{'─'*60}")
    print(f" {now}  │  Gesamt: {total_w:.0f} W  │  Ertrag: {total_kwh:.2f} kWh{limit_str}")
    print(f"{'─'*60}")
    print(f" {'MI':<4} {'Seriennummer':<12} {'DC-V':>6} {'AC-W':>7} {'AC-V':>6} {'Hz':>6} {'Temp':>6} {'kWh':>8}")
    for ch in channels:
        print(f"  {ch['mi']:<4} {ch['uid']:08X}     {ch['dc_v']:>6.1f} {ch['ac_w']:>7.1f} "
              f"{ch['ac_v']:>6.1f} {ch['freq']:>6.2f} {ch['temp']:>5.1f}° "
              f"{ch['kwh']:>7.2f}")


def main():
    print(f"EVT2000SE Monitor – {IP}:{PORT} – alle {POLL_INTERVAL}s")
    print("Strg+C zum Beenden")

    sock = None
    limit_w = None
    limit_poll_counter = 0
    while True:
        try:
            # Leistungsgrenze beim Start und alle 20 Zyklen (~10min) neu abfragen
            if limit_poll_counter == 0:
                limit_w = read_power_limit()
            limit_poll_counter = (limit_poll_counter + 1) % 20

            # Verbindung aufbauen falls nötig
            if sock is None:
                sock = connect()

            frame = read_live_data(sock)
            if frame:
                channels = parse_frame(frame)
                print_data(channels, limit_w)
            else:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Timeout – versuche neu...")
                sock.close()
                sock = None
                continue

            time.sleep(POLL_INTERVAL)

        except (ConnectionError, OSError, socket.timeout) as e:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fehler: {e} – reconnect in 3s...")
            if sock:
                sock.close()
                sock = None
            time.sleep(3)

        except KeyboardInterrupt:
            print("\nBeendet.")
            if sock:
                sock.close()
            sys.exit(0)


if __name__ == "__main__":
    main()
