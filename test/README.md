# Test tools

Diagnostic sketches and scripts used to bring up the receiver one layer at a
time. None of these are needed to run the finished link; they exist so that when
something doesn't work, you can find out which layer is at fault. The full
step-by-step procedure that uses them is in [docs/TESTING.md](../docs/TESTING.md).

| Tool | Runs on | What it tells you | Used in |
|---|---|---|---|
| [`sensor_test/sensor_test.ino`](sensor_test/sensor_test.ino) | Arduino | Live light level as a plotted line (Serial Plotter, 115200) | Phase 3, Phase 6 |
| [`sensor_minmax/sensor_minmax.ino`](sensor_minmax/sensor_minmax.ino) | Arduino | Record LOW and HIGH readings, for picking a screen and load resistor (Serial Monitor, 115200) | Phase 5 |
| [`check.py`](check.py) | Host | Confirms the streaming firmware's raw samples reach Python and track the light | Phase 7 |
| `optical_rx.py --selftest` | Host | Decodes a synthetic noisy signal with no hardware; expect `5/5 cases passed` | Phase 0 |
| `optical_rx.py --replay FILE` | Host | Re-decodes a capture saved with `--record`, with no hardware | Phase 10 |

The two sketches print human-readable text, so they are meant for the Arduino
IDE's Serial Plotter/Monitor. The production firmware in
[`firmware/`](../firmware/optical_receiver_stream/optical_receiver_stream.ino)
streams raw binary instead; after uploading it, use `check.py` or the decoder
and keep the Serial Monitor closed.

Each sketch lives in a folder with the same name because the Arduino IDE
requires it. Open the `.ino` file directly with **File → Open**.

## Running `check.py`

```bash
python3 test/check.py              # no argument: shows help and lists serial ports
python3 test/check.py <PORT>       # e.g. /dev/cu.usbmodem1101, /dev/ttyACM0, COM5
```

It prints about 10 lines per second showing the average light level, the min
and max in that 0.1 s window, and a bar. Put a white screen on the sensor and the
level should rise; show black or cover it and the level should fall toward 0.
Press Ctrl-C to stop, which also frees the port for the decoder.
