# Build and test guide

Follow these phases in order. Each one ends with a **checkpoint**; confirm it
before moving on, so that if something breaks you only have one new thing to
blame. Most of the debugging value comes from testing one layer at a time, so
don't skip the checkpoints.

The test sketches and scripts used here live in [`test/`](../test/README.md).

**Command conventions.** Commands are run from the repository root. `<PORT>` is
your Arduino's serial port (Phase 7 shows how to find it). On Windows, use
`python` or `py` wherever you see `python3`, and backslashes in paths.

---

## Phase 0: Software setup

**Arduino IDE**

1. Install the Arduino IDE 2.x from arduino.cc.
2. Open **Tools → Board → Boards Manager**, search for `UNO R4`, and install
   **Arduino UNO R4 Boards**.
3. Plug in the Uno R4 with a USB-C **data** cable.
4. Select the board under **Tools → Board** (Arduino UNO R4 Minima or Arduino
   UNO R4 WiFi; for a clone, choose whichever it copies).
5. Select the port under **Tools → Port**. It is the entry that appears and
   disappears when you unplug and replug the board.

**Python** (on the receiver host)

```bash
git clone https://github.com/RedTeamSkier/Optical-Data-Transfer-Concept.git
cd Optical-Data-Transfer-Concept
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Decoder self-test** (no hardware needed)

```bash
python3 decoder/optical_rx.py --selftest
```

> **Checkpoint:** the board and port are selected with no red errors, and the
> self-test prints `5/5 cases passed`.

## Phase 1: Prove the toolchain (Blink)

1. Open **File → Examples → 01.Basics → Blink** and click **Upload**.
2. The onboard LED should blink once per second.

> **Checkpoint:** the LED blinks. If the upload fails here, the cause is the
> cable (charge-only?) or the wrong port. Fix it now, before there is a circuit
> to blame.

## Phase 2: Build the circuit

Wire it as shown in [HARDWARE.md → The circuit](HARDWARE.md#the-circuit):
collector to 5V, emitter to row X, load resistor from row X to GND, 10 nF from
row X to GND, and a jumper from row X to A0. Use **47 kΩ** if your source is a
laptop screen. Fit the heat-shrink shroud (unshrunk) over the sensor.

> **Checkpoint:** the sensor's emitter, the resistor, the capacitor, and the A0
> wire all share one breadboard column, and nothing is warm.

## Phase 3: See the light

1. Upload [`test/sensor_test/sensor_test.ino`](../test/sensor_test/sensor_test.ino).
2. Open **Tools → Serial Plotter** at 115200 baud.
3. Cover the sensor: the line drops. Shine a light on it: the line jumps.
4. If the line stays flat near 0 regardless of light, flip the TEPT4400. If
   more light gives a *lower* line, the sensor and resistor are swapped; put the
   sensor on the 5V side.

> **Checkpoint:** a clear, repeatable up/down swing as the light changes.

## Phase 4: Verify the board itself (if anything looks wrong)

1. Move the A0 jumper from row X to the **GND** rail.
2. With `sensor_test` still running, the plot should drop to a flat line near 0.
3. Move the jumper back to row X.

> **Checkpoint:** a flat ~0 with A0 grounded means the board and ADC are
> healthy. If the real circuit then swings wildly, the fault is in the sense node
> (a loose leg or wrong column), not the Arduino.

## Phase 5: Choose the screen and tune the load resistor

This is the key measurement. Screens vary a lot for this sensor, so test every
candidate transmitter screen you have and use the brightest. Measure with your
**actual screen**, at your **actual spacing** (flush), under your **actual room
lighting**. Don't tune against a flashlight; it will point you to the wrong
resistor.

**Prepare each candidate screen** as described in
[Choosing a screen](../README.md#choosing-a-screen) (maximum brightness, adaptive
features off, on AC power). Avoid screens with adaptive or local-dimming
backlights, such as mini-LED MacBook Pro models. They adjust the backlight in
response to what's on screen and fight the signal.

**Show solid white and solid black full screen.** In Chrome or Edge, you can type
these into the address bar and then go full screen:

```
data:text/html,<body style="background:#fff">
data:text/html,<body style="background:#000">
```

**Measure:**

1. Upload [`test/sensor_minmax/sensor_minmax.ino`](../test/sensor_minmax/sensor_minmax.ino)
   and open **Tools → Serial Monitor** at 115200 baud.
2. For each screen and resistor combination:
   - Seal the shroud flush against the screen.
   - Clear the records: press **RESET**, or type any character in the Serial
     Monitor and press Enter.
   - Show white for about 3 s (sets HIGH), then black for about 3 s (sets LOW).
   - Record HIGH and LOW.

| Screen | Resistor | HIGH (white) | LOW (black) | Swing | Pegged at 16383? |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

3. **Pick the winner.** Reject any combination where HIGH pegs at 16383
   (clipping; the resistor is too large for that screen). Of the rest, take the
   one with the biggest swing whose HIGH stays under about 15,500. For reference,
   screens in testing gave swings of roughly 2,900 to 4,500 counts at 47 kΩ.
4. **Check the speed.** With the chosen resistor, confirm that `R × 10 nF` is at
   most 3.3 ms for 15 bps, or 1.7 ms for 30 bps (see the table in
   [HARDWARE.md](HARDWARE.md#speed-the-resistor-and-capacitor-form-a-low-pass-filter)).
   If it isn't, the resistor is too large regardless of the swing.

> **Checkpoint:** a chosen screen and resistor with a big, non-clipping swing and
> a fast-enough RC time constant.

## Phase 6: Seal and flicker check

1. Upload `sensor_test` again and open the **Serial Plotter**.
2. Hold the chosen screen on solid white, shroud sealed, and watch for about 10 s.

| What you see | What it means |
|---|---|
| A thin, flat line | The shroud is sealing out room light. Good. |
| A fat, regular ripple | Room light is leaking in. Reseat the shroud flush until it calms. |
| A level that drifts or "breathes" on its own | An adaptive brightness feature is still on. Turn it off, or choose another screen. |

> **Checkpoint:** a steady bright level with ripple that is small compared with
> your swing.

## Phase 7: Stream to the host

1. Upload [`firmware/optical_receiver_stream/optical_receiver_stream.ino`](../firmware/optical_receiver_stream/optical_receiver_stream.ino)
   and wait for "Done uploading."
2. **Close the Serial Monitor and Serial Plotter.** They hold the port, and this
   firmware's output is raw binary anyway.
3. Find the port:

   ```bash
   python3 -m serial.tools.list_ports
   ```

   It looks like `/dev/cu.usbmodem…` on macOS, `/dev/ttyACM0` on Linux, or
   `COM5` (some number) on Windows.
4. Run the sanity reader:

   ```bash
   python3 test/check.py <PORT>
   ```

5. Switch the screen between white and black. The level and bar should follow.
   Press Ctrl-C when done; this frees the port.

> **Checkpoint:** numbers stream into Python and track the light. The receiver
> is now proven end to end.

## Phase 8: First framed transmission (text)

The order matters: **get the transmitter ready, start the decoder, then start
the transmitter.** The decoder locks onto a transmission most reliably when it is
already listening as the first frame begins.

**1. Get the transmitter ready (don't start it yet).** On the transmitter
computer:

1. Get the repo onto it (clone it, or use **Code → Download ZIP** on GitHub).
2. Prepare the display (maximum brightness, adaptive features off, battery
   saver off, on AC power).
3. Open `transmitter/Optical_Tx.html` in the browser.
4. Leave the message as `HELLO OPTICAL WORLD`. Set **Frames / symbol = 2**
   (15 bps), leave the gap at 24, and leave **Loop continuously** checked. The
   estimate should read about 13.9 s.
5. Press the shrouded sensor flush against the screen.

**2. Start the decoder** on the receiver host:

```bash
python3 decoder/optical_rx.py --port <PORT> --record text.bin
```

**3. Start the transmitter.** Press `Space` (or click **Go fullscreen &
transmit**). Keep this tab focused for the whole run.

Wait for at least one full loop (about 15 s for this message). Success looks
like:

```
[RX] TEXT (19 B): HELLO OPTICAL WORLD
```

> **Checkpoint:** the message prints correctly.

## Phase 9: File transfer

Use the same order as Phase 8, and **restart the decoder for each new message or
file.** A decoder still holding the tail of the previous transmission may not
pick up the new one.

1. Stop the transmitter (`Esc`) and stop the decoder (Ctrl-C).
2. On the transmitter, choose `demo-assets/smiley-16.png` in the file picker
   (127 bytes; the estimate should read about 71.5 s at 15 bps). Don't start it
   yet.
3. Start the decoder with a new recording name:

   ```bash
   python3 decoder/optical_rx.py --port <PORT> --record smiley.bin
   ```

4. Start the transmitter (`Space`), with the sensor flush. After about one loop,
   success looks like:

   ```
   [RX] FILE (127 B) -> ./received_<timestamp>.png  (open it)
   ```

5. Verify the file is byte-for-byte identical, using the filename the decoder
   printed:

   ```bash
   cmp demo-assets/smiley-16.png ./received_<timestamp>.png && echo IDENTICAL
   ```

   On Windows: `fc /b demo-assets\smiley-16.png received_<timestamp>.png`

6. Repeat steps 1–5 with `demo-assets/demo.csv` (49 bytes, about 30 s per loop),
   recording to `csv.bin`, and open the received `.csv` in a spreadsheet.

> **Checkpoint:** both files compare identical and open normally.

## Phase 10: Offline replay

Decode a waveform you recorded, with no hardware attached:

```bash
python3 decoder/optical_rx.py --replay text.bin
python3 decoder/optical_rx.py --replay smiley.bin
```

Replaying a file frame saves another copy of the file, just as the live run did.

> **Checkpoint:** the replay produces the same decode as the live run. This is
> how to iterate on the decoder: record once, then replay as often as needed.

## Phase 11 (optional): Push the rate

Set **frames/symbol = 1** (30 bps) and repeat Phases 8 and 9. If frames start
failing, go back to 2. If even 2 is unreliable, try 3 (10 bps) and work through
the troubleshooting table below.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Upload fails with "No device found" | The Serial Monitor/Plotter or the decoder is holding the port; close it. If it's stubborn, double-tap RESET to force the bootloader, or unplug, replug, and reselect the port. |
| No port appears at all | Charge-only USB cable, or a bad adapter or hub. Use a direct data cable. The power LED can light on a charge-only cable, so a lit LED proves nothing. |
| Serial Monitor is blank despite the right port and baud | Change the baud dropdown to force a reconnect, or press RESET with the Monitor open. |
| Serial Monitor shows garbage characters | The streaming firmware is loaded, and its output is binary. That's expected; use `test/check.py` or the decoder. |
| `Permission denied` opening `/dev/ttyACM0` (Linux) | Add yourself to the serial group (`sudo usermod -aG dialout $USER`), then log out and back in. |
| `check.py` prints "no data" | The streaming firmware isn't loaded, or another program has the port. |
| Pasting Python code leaves a `while>` or `...` prompt | Code was pasted into the shell. Press Ctrl-C and run the script as a file instead. |
| Reading stuck at 0 | Sense node not connected (loose leg or wrong column), the sensor's 5V leg has lost power, or the sensor is reversed. |
| Reading stuck at 16383 | A0 is tied to 5V, or the resistor is far too large for the source (clipping). |
| Flat reading regardless of light | Flip the TEPT4400. |
| More light gives lower numbers | Sensor and resistor are swapped. Put the sensor on the 5V side. |
| Wild swings that don't respond to covering | Unshrouded sensor seeing the whole room, or a floating input. Fit the shroud and check row X. Confirm with the A0-to-GND test (Phase 4). |
| Regular ripple on a steady bright level | Room light leaking past the shroud (reseat it), or backlight PWM (raise to maximum brightness, which often switches the backlight to steady DC). |
| Bright level drifts on its own | Adaptive brightness, content-adaptive dimming, or local dimming. Turn it off or use a different screen. |
| Huge swing only at very high resistance | The RC filter is too slow; the swing looks great but can't carry data. Use a smaller resistor. |
| Decoder never locks, or the flashing looks uneven or slow | The browser is throttling `requestAnimationFrame`. Keep the tab full screen and focused, turn battery saver off, and plug into AC power. |
| Frames keep failing the CRC, or text arrives garbled | Improve the seal, raise brightness, try a brighter screen, or slow down (frames/symbol 3). Let the transmitter loop; the decoder keeps trying. |
| Nothing decodes after switching to a new message or file | Restart the decoder (Ctrl-C and rerun it) before starting the new transmission. |
| Nothing decodes even after a full loop | The decoder needs one complete frame from preamble to CRC. Start the decoder before the transmitter, then wait one full loop (the page shows how long). |
| The transmit-time estimate is far longer than expected for a small file | The file is bigger than it looks, often from embedded metadata. Check its size in bytes and strip the metadata (see [LESSONS.md](LESSONS.md)). |
