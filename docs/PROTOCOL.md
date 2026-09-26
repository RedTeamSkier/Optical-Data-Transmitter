# Protocol

This page specifies everything a transmitter must emit and a receiver must
expect. The transmitter (`transmitter/Optical_Tx.html`) and the decoder
(`decoder/optical_rx.py`) both follow it, so any new light source that emits
this format will decode with the existing decoder unchanged.

## Layers at a glance

```
payload bytes (text or file)
   │  frame: preamble · sync · type · length · payload · CRC-8
   ▼
bit stream, MSB-first
   │  Manchester: each bit → two half-bit symbols
   ▼
BRIGHT / DARK symbols, one per N display frames
   │  light through free space
   ▼
ADC samples at 600 Hz → raw uint16 over USB → host decoder
```

## Physical layer

The transmitter shows one of two levels: **BRIGHT** (white patch) or **DARK**
(black patch). At the receiver, bright means higher ADC counts. Each symbol lasts
a whole number of display frames, set by the transmitter's **frames/symbol**
control. The page is driven by `requestAnimationFrame`, so symbol edges line up
with the display's refresh.

## Line coding: Manchester

Every logical bit is sent as two half-bit symbols with a guaranteed transition in
the middle:

| Logical bit | First half | Second half |
|---|---|---|
| **1** | BRIGHT | DARK |
| **0** | DARK | BRIGHT |

This matches the original G. E. Thomas convention (IEEE 802.3 Ethernet uses the
opposite mapping). The guaranteed mid-bit transition is what makes the signal
**self-clocking**: the receiver locks onto those transitions to recover the
transmitter's timing, so the two ends never need a shared clock. The entire frame,
preamble included, is Manchester-encoded.

## Frame format

Bits are sent **MSB-first** within each byte, fields in this order:

| Field | Size | Value / meaning |
|---|---|---|
| preamble | 16 bits | Alternating, starting with 1: `1010…10`, which is bytes `0xAA 0xAA` |
| sync | 1 byte | `0x7E` |
| type | 1 byte | `0x00` = UTF-8 text, `0x01` = binary file |
| length | 2 bytes | Payload byte count, big-endian (0–65535) |
| payload | *length* bytes | The message or file, verbatim (binary-safe) |
| crc | 1 byte | CRC-8 over `[type, length_hi, length_lo, payload…]` |

The preamble and sync are **not** covered by the CRC.

**Why the preamble works.** An alternating `1010…` pattern Manchester-encodes to
`BD DB BD DB …`. The symbols at each bit boundary match, so the only transitions
are the mid-bit ones, and they are spaced exactly one bit apart. That gives the
receiver a clean square wave from which to measure the bit period and find the
mid-bit grid, and it lets the adaptive threshold settle on the bright and dark
levels before any data arrives.

### CRC-8

| Parameter | Value |
|---|---|
| Polynomial | `0x07` (x⁸ + x² + x + 1) |
| Initial value | `0x00` |
| Input/output reflection | None (MSB-first) |
| Final XOR | None |
| Check value for ASCII `"123456789"` | `0xF4` |

This is the variant cataloged as CRC-8/SMBUS. It detects every single-bit error,
but there is no error *correction*: a frame that fails the CRC is discarded.

### Worked example: the text "HI"

| Field | Bytes |
|---|---|
| preamble | `AA AA` |
| sync | `7E` |
| type | `00` (text) |
| length | `00 02` |
| payload | `48 49` ("HI") |
| crc | `DD` (CRC-8 of `00 00 02 48 49`) |

The full frame is `AA AA 7E 00 00 02 48 49 DD`: 9 bytes, 72 bits, and 144
symbols, which takes 4.8 s at 15 bps.

### Reference encoder

A minimal Python implementation, useful for building a new transmitter or for
checking a capture by hand:

```python
def crc8(data):
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def build_frame(payload, frame_type):          # frame_type: 0x00 text, 0x01 file
    body = bytes([frame_type, len(payload) >> 8, len(payload) & 0xFF]) + payload
    return bytes([0xAA, 0xAA, 0x7E]) + body + bytes([crc8(body)])

def manchester(frame):                          # returns 1 = BRIGHT, 0 = DARK
    symbols = []
    for byte in frame:
        for i in range(7, -1, -1):              # MSB first
            bit = (byte >> i) & 1
            symbols += [1, 0] if bit else [0, 1]
    return symbols

assert crc8(b"123456789") == 0xF4
assert build_frame(b"HI", 0x00).hex() == "aaaa7e0000024849dd"
```

## Rates and airtime

On a display refreshing at `R` Hz:

```
bit rate = R / (2 × frames_per_symbol)
```

| frames/symbol | Bit rate at 60 Hz | Samples per bit at 600 Hz |
|---|---|---|
| 3 | 10 bps | 60 |
| **2 (recommended start)** | **15 bps** | **40** |
| 1 | 30 bps | 20 |

A screen tops out around 15–30 bps: the refresh rate caps the symbol rate, and
LCD pixels need 10–20 ms to settle between gray levels. On a display running
faster than 60 Hz, the same setting gives a proportionally higher bit rate, so
raise frames/symbol to compensate (the transmitter's time estimate assumes
60 Hz). The decoder accepts 6 to 200 samples per bit, which is 3 to 100 bps, or
frames/symbol 1 to 10 on a 60 Hz display.

**Inter-frame gap.** Between looped frames the transmitter shows black for the
gap (default 24 display frames), rounded up to a whole number of bits (a
multiple of 2 × frames/symbol). A whole-bit gap keeps the decoder's bit clock in
phase from one frame to the next: there are no edges during the gap for it to
re-anchor to, so a fractional-bit gap would leave it half a bit out of step.

A frame carries 56 bits of overhead (preamble 16 + sync 8 + type 8 + length 16 +
CRC 8), so one frame takes:

```
airtime (s) = (56 + 8 × payload_bytes) / bit_rate
```

| Payload | Size | 15 bps | 30 bps |
|---|---|---|---|
| `HELLO OPTICAL WORLD` | 19 B | 14 s | 7 s |
| `demo-assets/smiley-16.png` | 127 B | 72 s | 36 s |
| `demo-assets/demo.csv` | 49 B | 30 s | 15 s |

That works out to about 1.9 bytes per second at 15 bps. Two minutes of airtime,
a comfortable length for a classroom demo, carries about 218 bytes at 15 bps or
443 bytes at 30 bps. A typical photo or
spreadsheet export (tens of kilobytes) would take hours and would almost
certainly be corrupted along the way, so keep payloads in the low hundreds of
bytes.

**Looping is the retransmit.** With the transmitter's loop enabled, the decoder
keeps trying until a copy passes the CRC, and it ignores repeated copies of a
frame it has already decoded. Text degrades gracefully when bits flip
(`HELL0 W0RLD` is still readable); binary files do not, which is why the CRC
matters.

## Receiver interface contract

The Arduino streams **raw, little-endian, unsigned 16-bit samples: 2 bytes per
sample, low byte first, no delimiters or newlines, at 600 samples per second**,
over serial at 115200 baud. Unpack each pair with `struct` format `'<H'`. Values
run 0–16,383 (14-bit).

Nothing frames the samples. The host reads 2 bytes at a time continuously and
finds frames itself using the preamble and sync word. The stream is 1,200 bytes
per second, about a tenth of what 115200 baud can carry, so the serial link has
plenty of headroom.

Only one program can hold the serial port at a time. Close the Arduino Serial
Monitor/Plotter before running `test/check.py` or the decoder.

## How the decoder reads it

`decoder/optical_rx.py` processes the stream in six stages:

1. **Byte alignment.** Every sample is 14-bit, so a correctly aligned high byte
   is always `≤ 0x3F`. A run of impossible high bytes means the reader started
   mid-sample, so it shifts by one byte.
2. **Anti-flicker low-pass.** A 70 Hz, 2-pole software filter strips room-light
   and backlight flicker below the 300 Hz Nyquist limit. It cannot fix flicker
   that has already aliased (see [LESSONS.md](LESSONS.md)).
3. **Adaptive threshold.** A running min/max peak tracker snaps to new extremes
   and relaxes slowly; the slice point is the midpoint, with a little hysteresis
   to reject noise. Nothing is hard-coded, so it adapts to any screen, resistor,
   and room.
4. **Clock recovery.** The preamble shows up as a run of at least 8 near-equal
   edge intervals one bit apart, which gives the bit period and a mid-bit
   anchor. A run of repeated bits in the payload (such as a `0x00` byte) also
   produces equal intervals, but half a bit apart and bordered by one-bit
   intervals; the decoder recognizes that pattern and doubles the period, so it
   still locks correctly if it starts listening partway through a frame.
5. **Manchester decode.** For each bit, the decoder compares the integrated
   brightness of the first half with the second half, which is robust to drift
   and needs no threshold. It re-anchors to the actual mid-bit edge on every bit
   so slow clock drift can't accumulate.
6. **Framing.** It searches the bit stream for `0x7E` following an alternating
   preamble, then parses type, length, payload, and CRC-8.

Text frames print inline. File frames are saved and auto-named by content: `.png`
if the PNG signature is present, `.csv` for printable ASCII containing commas and
newlines, otherwise `.bin`.

In live mode the decoder keeps a rolling 5-minute buffer (`LIVE_BUFFER_S`),
which must be longer than the longest frame, and attempts a decode about once
per second of new data (`DECODE_EVERY_S`). Frames it has already printed or saved
are ignored when the transmitter loops.

Key parameters: `SAMPLE_RATE = 600`, `SYNC = 0x7E`, samples-per-bit search range
`MIN_SPB = 6` to `MAX_SPB = 200` (100 bps down to 3 bps), `PREFILTER_HZ = 70`,
`LIVE_BUFFER_S = 300`, `DECODE_EVERY_S = 1.0`.
