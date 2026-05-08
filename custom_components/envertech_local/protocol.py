"""Envertech EVT local TCP protocol implementation."""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

FRAME_START = 0x68
FRAME_END = 0x16
CS_SEED = 0x55

TCP_PORT = 14889
CONNECT_TIMEOUT = 10
RESPONSE_TIMEOUT_LIVE = 8
RESPONSE_TIMEOUT_STATUS = 15
RETRY_DELAY = 5
MAX_RETRIES_LIVE = 5
MAX_RECONNECTS_LIVE = 3
MAX_RETRIES_STATUS = 7
STATUS_RETRY_DELAY = 8

CMD_LIVE_DATA_REQ = 0x1077
CMD_LIVE_DATA_RESP = 0x1051
CMD_STATUS_REQ = 0x1041
CMD_STATUS_RESP = 0x1006
CMD_POWER_LIMIT_SET = 0x1137
CMD_SKIP_1 = 0x1004
CMD_SKIP_2 = 0x1006

# EVT2000SE watt codes: watt -> code
WATT_CODES_2000: dict[int, int] = {
    600: 0x09,
    800: 0x0A,
    1200: 0x01,
    1400: 0x0B,
    1440: 0x02,
    1600: 0x06,
    1640: 0x0C,
    1800: 0x07,
    2000: 0x00,
}

# Reverse mapping: code -> watt
CODE_TO_WATTS_2000: dict[int, int] = {v: k for k, v in WATT_CODES_2000.items()}


@dataclass
class MicroinverterData:
    """Data from one micro-inverter channel."""

    uid: int
    dc_voltage: float
    ac_power: float
    total_energy: float
    temperature: float
    ac_voltage: float
    frequency: float


@dataclass
class LiveData:
    """Complete live data response from the inverter."""

    firmware_main: int
    firmware_sub: int
    emeter_type: int
    mi_phase: int
    anti_backfeed: bool
    channels: list[MicroinverterData]

    @property
    def total_ac_power(self) -> float:
        """Total AC power across all channels."""
        return sum(ch.ac_power for ch in self.channels)

    @property
    def total_energy(self) -> float:
        """Total energy across all channels."""
        return sum(ch.total_energy for ch in self.channels)


def _checksum(data: bytes) -> int:
    """Calculate frame checksum."""
    return (sum(data) + CS_SEED) & 0xFF


def _build_frame(cmd: int, serial: int, payload: bytes = b"") -> bytes:
    """Build a binary frame."""
    total_len = 12 + len(payload)
    body = (
        bytes([FRAME_START])
        + struct.pack(">H", total_len)
        + bytes([FRAME_START])
        + struct.pack(">H", cmd)
        + struct.pack(">I", serial)
        + payload
    )
    return body + bytes([_checksum(body), FRAME_END])


def _encode_tx(frame: bytes) -> bytes:
    """ASCII-Hex encode a frame for transmission."""
    return frame.hex().upper().encode("ascii")


def _parse_channel(block: bytes) -> MicroinverterData:
    """Parse a 32-byte micro-inverter channel block."""
    uid = struct.unpack(">I", block[0:4])[0]
    dc_v = struct.unpack(">H", block[6:8])[0] * 64 / 32768.0
    ac_w = struct.unpack(">H", block[8:10])[0] * 512 / 32768.0
    kwh = struct.unpack(">I", block[10:14])[0] * 4 / 32768.0
    temp = struct.unpack(">H", block[14:16])[0] * 256 / 32768.0 - 40.0
    ac_v = struct.unpack(">H", block[16:18])[0] * 512 / 32768.0
    freq = struct.unpack(">H", block[18:20])[0] * 128 / 32768.0
    return MicroinverterData(
        uid=uid,
        dc_voltage=round(dc_v, 1),
        ac_power=round(ac_w, 1),
        total_energy=round(kwh, 2),
        temperature=round(temp, 1),
        ac_voltage=round(ac_v, 1),
        frequency=round(freq, 2),
    )


def _parse_live_data(frame: bytes) -> LiveData:
    """Parse a 0x1051 live data response frame."""
    firmware_main = frame[10]
    firmware_sub = frame[12]
    emeter_type = frame[14]
    mi_phase = frame[15]
    anti_backfeed = frame[16] == 1

    channels: list[MicroinverterData] = []
    for i in range(4):
        offset = 20 + i * 32
        block = frame[offset : offset + 32]
        if len(block) >= 20:
            channels.append(_parse_channel(block))

    return LiveData(
        firmware_main=firmware_main,
        firmware_sub=firmware_sub,
        emeter_type=emeter_type,
        mi_phase=mi_phase,
        anti_backfeed=anti_backfeed,
        channels=channels,
    )


class EnvertechConnection:
    """Persistent TCP connection to an Envertech inverter."""

    def __init__(self, host: str, serial: int) -> None:
        """Initialize the connection."""
        self._host = host
        self._serial = serial
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Establish TCP connection."""
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, TCP_PORT),
                timeout=CONNECT_TIMEOUT,
            )
            _LOGGER.debug("Connected to %s:%d", self._host, TCP_PORT)
        except (OSError, asyncio.TimeoutError) as err:
            self._reader = None
            self._writer = None
            raise ConnectionError(
                f"Cannot connect to {self._host}:{TCP_PORT}"
            ) from err

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._writer = None
                self._reader = None
            _LOGGER.debug("Disconnected from %s", self._host)

    async def _receive_frame(self, timeout: float) -> bytes | None:
        """Receive a single binary frame from the inverter."""
        if self._reader is None:
            return None
        try:
            # Find start byte
            while True:
                b = await asyncio.wait_for(
                    self._reader.read(1), timeout=timeout
                )
                if not b:
                    return None
                if b[0] == FRAME_START:
                    break

            # Read length
            len_bytes = await asyncio.wait_for(
                self._reader.readexactly(2), timeout=timeout
            )
            total_length = struct.unpack(">H", len_bytes)[0]

            # Read rest of frame
            rest = await asyncio.wait_for(
                self._reader.readexactly(total_length - 3), timeout=timeout
            )
            return bytes([FRAME_START]) + len_bytes + rest

        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError):
            return None

    async def _send_and_receive(
        self,
        cmd: int,
        payload: bytes,
        expected_cmd: int,
        timeout: float,
        skip_cmds: tuple[int, ...] = (),
    ) -> bytes | None:
        """Send a command and wait for the expected response."""
        if self._writer is None:
            return None

        frame = _build_frame(cmd, self._serial, payload)
        tx_data = _encode_tx(frame)

        self._writer.write(tx_data)
        await self._writer.drain()

        while True:
            resp = await self._receive_frame(timeout)
            if resp is None:
                return None

            resp_cmd = struct.unpack(">H", resp[4:6])[0]
            if resp_cmd == expected_cmd:
                return resp
            if resp_cmd in skip_cmds:
                continue
            _LOGGER.debug(
                "Unexpected command 0x%04X (expected 0x%04X)", resp_cmd, expected_cmd
            )
            return resp

    async def get_live_data(self) -> LiveData:
        """Fetch live data with two-level retry: retries on same connection, then reconnect."""
        async with self._lock:
            last_err: Exception | None = None

            for reconnect in range(MAX_RECONNECTS_LIVE):
                # On reconnect attempts (not the first), disconnect cleanly first
                if reconnect > 0:
                    _LOGGER.debug(
                        "Reconnect attempt %d/%d – closing and re-opening connection",
                        reconnect + 1,
                        MAX_RECONNECTS_LIVE,
                    )
                    await self.disconnect()
                    await asyncio.sleep(RETRY_DELAY)

                try:
                    await self.connect()
                except (OSError, asyncio.TimeoutError) as err:
                    last_err = err
                    _LOGGER.debug("Connect failed on reconnect %d: %s", reconnect + 1, err)
                    continue

                # Inner loop: retry on same connection
                for attempt in range(MAX_RETRIES_LIVE):
                    try:
                        resp = await self._send_and_receive(
                            CMD_LIVE_DATA_REQ,
                            bytes(20),
                            CMD_LIVE_DATA_RESP,
                            RESPONSE_TIMEOUT_LIVE,
                            skip_cmds=(CMD_SKIP_1, CMD_SKIP_2),
                        )
                        if resp is None:
                            last_err = ConnectionError("No response from inverter")
                            _LOGGER.debug(
                                "Live data attempt %d/%d (reconnect %d) timed out",
                                attempt + 1,
                                MAX_RETRIES_LIVE,
                                reconnect + 1,
                            )
                            if attempt < MAX_RETRIES_LIVE - 1:
                                await asyncio.sleep(RETRY_DELAY)
                            continue

                        resp_cmd = struct.unpack(">H", resp[4:6])[0]
                        if resp_cmd != CMD_LIVE_DATA_RESP:
                            raise ConnectionError(
                                f"Unexpected response 0x{resp_cmd:04X}"
                            )

                        return _parse_live_data(resp)

                    except (ConnectionError, OSError) as err:
                        last_err = err
                        _LOGGER.debug(
                            "Live data attempt %d/%d (reconnect %d) error: %s",
                            attempt + 1,
                            MAX_RETRIES_LIVE,
                            reconnect + 1,
                            err,
                        )
                        # Connection broken – break inner loop to trigger reconnect
                        break

            raise ConnectionError(
                f"Failed to get live data after {MAX_RECONNECTS_LIVE} reconnects "
                f"x {MAX_RETRIES_LIVE} retries"
            ) from last_err

    async def get_power_limit(self) -> int | None:
        """Read current power limit watt code.

        Opens a dedicated connection per attempt (separate from the persistent
        live-data connection), matching the reference implementation.
        Returns watts or None on failure.
        """
        req = _build_frame(CMD_STATUS_REQ, self._serial, bytes(10))
        tx_data = _encode_tx(req)

        for attempt in range(MAX_RETRIES_STATUS):
            if attempt > 0:
                await asyncio.sleep(STATUS_RETRY_DELAY)
            sock_reader: asyncio.StreamReader | None = None
            sock_writer: asyncio.StreamWriter | None = None
            try:
                sock_reader, sock_writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, TCP_PORT),
                    timeout=CONNECT_TIMEOUT,
                )
                sock_writer.write(tx_data)
                await sock_writer.drain()

                deadline = asyncio.get_event_loop().time() + RESPONSE_TIMEOUT_STATUS
                while asyncio.get_event_loop().time() < deadline:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    # Read one frame manually using a temporary reader
                    try:
                        b = await asyncio.wait_for(sock_reader.read(1), timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    if not b or b[0] != FRAME_START:
                        continue
                    try:
                        len_bytes = await asyncio.wait_for(
                            sock_reader.readexactly(2), timeout=remaining
                        )
                        total_length = struct.unpack(">H", len_bytes)[0]
                        rest = await asyncio.wait_for(
                            sock_reader.readexactly(total_length - 3), timeout=remaining
                        )
                    except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                        break
                    frame = bytes([FRAME_START]) + len_bytes + rest
                    resp_cmd = struct.unpack(">H", frame[4:6])[0]
                    if resp_cmd == CMD_STATUS_RESP and len(frame) >= 15:
                        watt_code = frame[14]
                        return CODE_TO_WATTS_2000.get(watt_code)

            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "Power limit read attempt %d failed: %s", attempt + 1, err
                )
            finally:
                if sock_writer is not None:
                    try:
                        sock_writer.close()
                        await sock_writer.wait_closed()
                    except OSError:
                        pass

        _LOGGER.warning("Failed to read power limit after %d attempts", MAX_RETRIES_STATUS)
        return None

    async def set_power_limit(self, watts: int) -> bool:
        """Set power limit. Returns True on success."""
        if watts not in WATT_CODES_2000:
            _LOGGER.error("Invalid power limit: %dW", watts)
            return False

        watt_code = WATT_CODES_2000[watts]

        async with self._lock:
            try:
                await self.connect()
                resp = await self._send_and_receive(
                    CMD_POWER_LIMIT_SET,
                    bytes([watt_code]),
                    CMD_POWER_LIMIT_SET,
                    RESPONSE_TIMEOUT_STATUS,
                )
                if resp is not None and len(resp) >= 11:
                    confirmed_code = resp[10]
                    if confirmed_code == watt_code:
                        _LOGGER.info("Power limit set to %dW (code 0x%02X)", watts, watt_code)
                        return True
                    _LOGGER.warning(
                        "Power limit mismatch: sent 0x%02X, got 0x%02X",
                        watt_code,
                        confirmed_code,
                    )
                return False
            except (ConnectionError, OSError) as err:
                _LOGGER.error("Failed to set power limit: %s", err)
                await self.disconnect()
                return False
