# Optical Data Transfer Concept

A classroom demonstration of free-space optical data transfer. A laptop screen
flashes an encoded white/black patch, a phototransistor on an Arduino Uno R4
watches it, and a Python decoder on a host computer recovers the clock, checks
each frame, and prints the message or saves the file, with bits visibly
arriving in real time.

The project walks through the whole digital communications stack (line coding,
self-clocking, framing, synchronization, and error detection) using about $30 of
parts and a laptop screen. It also makes a simple idea concrete: a file is just
bytes, and bytes can travel as light.

## Results

Validated end to end over the light link:

- **Text:** `HELLO OPTICAL WORLD` sent from a laptop screen and decoded live.
- **CSV:** a small CSV file recovered byte-for-byte; it opens as a valid spreadsheet.
- **PNG:** a 127-byte 16×16 image recovered as a real, openable file.
- **Signal:** at near-contact, a bright/dark swing of about 4,500 ADC counts
  (out of 16,383), a dark floor near 0, about ±300 counts of residual noise after
  filtering, and a cleanly locked clock at 15 bps.

## How it works

```
 message or file
      │   transmitter/Optical_Tx.html: frame + CRC-8 + Manchester encoding
      ▼
 screen patch flashes white/black, synced to the display refresh
      │   free space: sensor shrouded and pressed flush to the screen
      ▼
 TEPT4400 phototransistor → 47 kΩ load → A0
      │   Arduino Uno R4: 14-bit ADC, 600 samples/s, raw uint16 over USB
      ▼
 decoder/optical_rx.py on the host
      │   align → anti-flicker filter → adaptive threshold →
      │   clock recovery → Manchester decode → frame + CRC check
      ▼
 text printed, or file saved
```

The design principle throughout is **keep the Arduino dumb and keep the
intelligence on the host.** The Arduino only samples the light level at a fixed
rate and streams raw numbers over USB. All decoding happens in Python, so the
waveform can be recorded, replayed, and plotted, and the decoder can be improved
without reflashing the board.

## Repository contents

| Path | What it is |
|---|---|
| [`firmware/optical_receiver_stream/`](firmware/optical_receiver_stream/optical_receiver_stream.ino) | Production Arduino firmware: samples A0 at 600 Hz and streams raw 16-bit samples |
| [`transmitter/Optical_Tx.html`](transmitter/Optical_Tx.html) | Screen transmitter: text or file, with a live transmit-time estimate |
| [`decoder/optical_rx.py`](decoder/optical_rx.py) | Host decoder: live, record, replay, and self-test modes |
| [`test/`](test/README.md) | Test sketches and scripts for bringing up the receiver one layer at a time |
| [`demo-assets/`](demo-assets/) | `smiley-16.png` (127 B) and `demo.csv` (49 B, synthetic data) |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Parts list, circuit, and why the component values are what they are |
| [`docs/TESTING.md`](docs/TESTING.md) | Step-by-step build and test guide with checkpoints and troubleshooting |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | Line coding, frame format, CRC-8, rates and airtime, receiver interface |
| [`docs/LESSONS.md`](docs/LESSONS.md) | The bring-up story: the gotchas actually hit, and their fixes |

## What you need

An Arduino Uno R4 (Minima or WiFi), a Vishay TEPT4400 phototransistor, a 47 kΩ
resistor, a 10 nF capacitor, a breadboard and jumpers, a USB-C data cable, a
short piece of black heat-shrink tubing, and two computers: a receiver host
running Python 3 and a transmitter with a browser and a bright screen. See
[docs/HARDWARE.md](docs/HARDWARE.md) for the full parts list and wiring.

## Quick start

Building it for the first time? Follow [docs/TESTING.md](docs/TESTING.md)
instead; it covers the same ground with a checkpoint at every step. This quick
start assumes the circuit is already built and working.

Commands run from the repository root. On Windows, use `python` or `py` in place
of `python3`.

**1. Set up Python on the receiver host.**

```bash
git clone https://github.com/RedTeamSkier/Optical-Data-Transfer-Concept.git
cd Optical-Data-Transfer-Concept
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Self-test the decoder** (no hardware needed). Expect `5/5 cases passed`.

```bash
python3 decoder/optical_rx.py --selftest
```

**3. Flash the receiver.** In the Arduino IDE 2.x, open
`firmware/optical_receiver_stream/optical_receiver_stream.ino`, select your
Uno R4 board and port, and click **Upload**. Don't open the Serial Monitor; this
firmware's output is raw binary.

**4. Find the serial port.**

```bash
python3 -m serial.tools.list_ports
```

It looks like `/dev/cu.usbmodem…` on macOS, `/dev/ttyACM0` on Linux, or `COM5`
on Windows. Use it wherever `<PORT>` appears below.

**5. Check that the sensor sees light.** Put a white screen on the shrouded
sensor, then black: the level should rise and fall. Press Ctrl-C to stop, which
frees the port.

```bash
python3 test/check.py <PORT>
```

**6. Get the transmitter ready, but don't start it yet.** On the transmitter
computer, prepare the display (see [Choosing a screen](#choosing-a-screen)) and
open `transmitter/Optical_Tx.html` in a browser. Type a message or pick a file
from `demo-assets/`, set **frames/symbol = 2**, and leave **Loop** on. Press the
shrouded sensor flush against the screen.

**7. Start the decoder first.**

```bash
python3 decoder/optical_rx.py --port <PORT> --record text.bin
```

**8. Start the transmitter.** Press `Space` (or click **Go fullscreen &
transmit**) and keep the tab focused. Wait at least one full loop; the page
shows how long one takes. Success looks like this:

```
[RX] TEXT (19 B): HELLO OPTICAL WORLD
[RX] FILE (127 B) -> ./received_<timestamp>.png  (open it)
```

**Restart the decoder for each new message or file** (Ctrl-C, then run step 7
again with a new recording name). A decoder that is still holding the tail of
the previous transmission may not pick up the new one.

**9. Verify a received file** against the original, using the filename the
decoder printed (on Windows, use `fc /b` instead of `cmp`).

```bash
cmp demo-assets/smiley-16.png ./received_<timestamp>.png && echo IDENTICAL
```

**10. Replay offline.** Decode a recorded waveform with no hardware attached.

```bash
python3 decoder/optical_rx.py --replay text.bin
```

## Final run commands

Once everything is set up, a classroom run is just this:

```bash
# Receiver host, from the repository root
source .venv/bin/activate                              # Windows: .venv\Scripts\activate
python3 decoder/optical_rx.py --selftest            # expect: 5/5 cases passed
python3 -m serial.tools.list_ports                     # find <PORT>
python3 test/check.py <PORT>                           # sensor sanity check; Ctrl-C to exit

# Transmitter computer: open transmitter/Optical_Tx.html → message or file
#   → frames/symbol 2 → Loop on → press the shrouded sensor flush to the screen

# Receiver host: start the decoder BEFORE pressing Space on the transmitter
python3 decoder/optical_rx.py --port <PORT> --record text.bin      # then press Space
# New message or file? Ctrl-C, rerun with a new --record name, then press Space.

# Afterward, no hardware needed
python3 decoder/optical_rx.py --replay text.bin
```

Only one program can hold the serial port at a time. Close the Arduino Serial
Monitor/Plotter and stop `check.py` before starting the decoder.

## Transmitter controls

`Optical_Tx.html` is a single self-contained page. It flashes a full-screen
white/black patch driven by `requestAnimationFrame`, so every symbol edge lines
up with a display refresh. It accepts a typed message **or** a file (use **Clear
file** to go back to text), and shows a live estimate of the transmit time as you
type, pick a file, or change the rate. The estimate assumes a 60 Hz display.

| Control | Effect |
|---|---|
| Frames / symbol | Display frames per half-bit. On a 60 Hz screen: 3 → 10 bps, **2 → 15 bps (start here)**, 1 → 30 bps |
| Inter-frame gap | Black frames between repeats (default 24). Rounded up to a whole number of bits so the decoder stays in step from one loop to the next. |
| Loop continuously | Repeat the frame. Leave it on: looping is the retransmit mechanism. |
| **Go fullscreen & transmit** or `Space` | Start (and `Space` again to stop) |
| `F` | Full screen |
| `Esc` | Stop and exit full screen. Leaving full screen any other way also stops the transmission. |

## Choosing a screen

The screen is the weakest part of the link, and screens differ a lot for this
sensor. **Test several and use the brightest.** Compare them with the min/max
procedure in [docs/TESTING.md, Phase 5](docs/TESTING.md#phase-5-choose-the-screen-and-tune-the-load-resistor).

**Avoid adaptive or local-dimming displays**, such as mini-LED MacBook Pro
models. They adjust the backlight in response to what's on screen, which behaves
like an automatic gain control fighting the signal. A conventional LCD with a
steady backlight works best.

Before every run, prepare the transmitter display:

1. Set brightness to maximum. This often switches the backlight from PWM
   flicker to steady DC.
2. Turn off automatic and content-adaptive brightness.
3. Turn off color-temperature features (True Tone and Night Shift on macOS,
   Night Light on Windows and ChromeOS) and HDR.
4. Turn off battery saver, plug into AC power, and disable screen dimming and
   sleep.
5. Keep the transmitter tab full screen and focused for the entire run.
   Background or covered tabs are throttled and flash unevenly.

## Airtime

The link carries about 1.9 bytes per second at 15 bps (3.8 at 30 bps), and there
is no error correction, so keep payloads small.

| Payload | 15 bps | 30 bps |
|---|---|---|
| `HELLO OPTICAL WORLD` (19 B) | 14 s | 7 s |
| `smiley-16.png` (127 B) | 72 s | 36 s |
| `demo.csv` (49 B) | 30 s | 15 s |

About two minutes of airtime, a comfortable length for a classroom, carries
roughly 218 bytes at 15 bps or 443 bytes at 30 bps. A normal photo or
spreadsheet (tens of kilobytes) would take hours. The formula and more detail are
in [docs/PROTOCOL.md](docs/PROTOCOL.md#rates-and-airtime).

## Limitations

- **Low bit rate:** about 15–30 bps from a screen, capped by the refresh rate and
  LCD pixel settling time.
- **No error correction or retransmission:** a single flipped bit fails the CRC.
  Looping the transmitter is the workaround, and binary files are far less
  forgiving than text.
- **Small payloads only:** low hundreds of bytes for a reasonable demo.
- **Sensitive to setup:** ambient light, the quality of the shroud's seal, and
  especially the display type all matter.

## Alternative light sources

Any light source that software can switch on and off can carry the same frames.
An LED, such as a development board's onboard LED or a discrete LED on a
microcontroller pin, is a physically stronger source than a screen: a bright
point source with fast switching, high contrast, and no refresh-rate ceiling. It
would need its own transmitter that emits the [frame format](docs/PROTOCOL.md), a
much smaller load resistor at the receiver, and, for rates well beyond a screen's,
a higher sample rate. See [docs/HARDWARE.md](docs/HARDWARE.md#alternative-light-sources).

## Future work

- Forward error correction, or repeat-and-vote across looped frames.
- A live waveform plot with the decoded bits annotated, as a teaching visual.
- A brighter or faster source (such as an LED) for higher rates, paired with
  hardware-timer sampling (`FspTimer` on the R4) at a higher sample rate.

## A note on demo data

Demo files get projected in class and committed to a public repository, so use
obviously synthetic data. `demo-assets/demo.csv` is synthetic; keep real names,
ID numbers, and other personal details out of anything you transmit or commit.

## License

[MIT](LICENSE) © 2026 RedTeamSkier
