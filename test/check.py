#!/usr/bin/env python3
"""
check.py - sanity reader for the optical receiver.

Reads the raw sample stream from firmware/optical_receiver_stream and prints
about 10 lines per second: the average light level in that window, the min
and max, and a bar so you can watch it move. Bright light -> high numbers.

Usage:
    python3 test/check.py PORT     e.g. /dev/cu.usbmodem1101, /dev/ttyACM0, COM5
    python3 test/check.py          (no port: prints this help and lists ports)

Stop with Ctrl-C. Close the Arduino Serial Monitor/Plotter first - only one
program can hold the serial port at a time.
"""

import struct
import sys

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is not installed. Run: pip install -r requirements.txt")

BAUD = 115200
FULL_SCALE = 16383   # 14-bit ADC
WINDOW = 60          # samples per printed line (600 samples/s / 60 = 10 lines/s)
BAR_WIDTH = 40


def print_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("  (none found - is the board plugged in with a data cable?)")
    for p in ports:
        print(f"  {p.device:<30} {p.description}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        print("\nAvailable ports:")
        print_ports()
        return 1

    port_name = sys.argv[1]
    try:
        port = serial.Serial(port_name, BAUD, timeout=1)
    except serial.SerialException as exc:
        print(f"Could not open {port_name}: {exc}")
        print("Is the Serial Monitor/Plotter or the decoder still holding the port?")
        return 1

    print(f"Reading {port_name} - one line per 0.1 s (average, min, max). Ctrl-C to stop.")
    window = []
    try:
        while True:
            data = port.read(2)
            if len(data) < 2:
                print("(no data - is the streaming firmware loaded?)")
                continue
            if data[1] > 0x3F:
                # A 14-bit sample never sets the top two bits of its high byte,
                # so we started reading mid-sample. Drop one byte to re-align.
                port.read(1)
                window.clear()
                continue
            window.append(struct.unpack("<H", data)[0])   # little-endian uint16
            if len(window) == WINDOW:
                avg = sum(window) // WINDOW
                bar = "#" * round(avg * BAR_WIDTH / FULL_SCALE)
                print(f"{avg:6d}   min {min(window):5d}   max {max(window):5d}"
                      f"   |{bar:<{BAR_WIDTH}}|")
                window.clear()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
