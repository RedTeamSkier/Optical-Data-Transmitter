# Lessons learned

These are the failure modes hit while bringing the link up and packaging it,
roughly in the order they appeared. Each is a real, reproducible gotcha, and together they
make a good tour of what goes wrong in practical communications systems.

## 1. The sensor is visible-light, not infrared

Early on, the weak screen signal was blamed on a spectral mismatch, on the theory
that the TEPT4400 was a near-infrared part and an LCD emits little IR. The
datasheet says otherwise: its sensitivity peaks at 570 nm, matched to the human
eye. Measured on the same rig, a flashlight on the dome read about 16,000
counts, daylight about 5,700, and a laptop screen at near-contact only about 300
(with a 2 kΩ load).

The real reason is that an LCD is a dim, diffuse source, while a flashlight puts
far more light into the sensor's narrow acceptance cone. The correct diagnosis
changes the fix: improve brightness and coupling (a brighter screen, a flush
seal, a larger load resistor), not the sensor.

## 2. A brightness test can't see a speed problem

The load resistor and filter capacitor form an RC low-pass filter. A very large
resistor gives a huge static swing on the min/max test but responds too slowly,
so the bits smear together. Always check `R × C` against the half-bit period,
not just the swing. See [HARDWARE.md](HARDWARE.md#speed-the-resistor-and-capacitor-form-a-low-pass-filter).

## 3. Test one layer at a time

Jumpering A0 to GND cleanly separates "board problem" from "circuit problem." A
healthy board reads a flat zero; if the real circuit then swings wildly, the fault
is in the sense node, not the Arduino. This single test saves hours. The same
principle drives the whole [build and test guide](TESTING.md): prove each layer
before adding the next.

## 4. A bare sensor is supposed to wander

An unshrouded sensor sees the whole room, and its reading swings with every
shadow and every flicker. That isn't noise to fix in the circuit; it's why the
shroud exists. Don't chase a quiet resting line from a bare sensor.

## 5. Room light is in-band

Because the sensor responds to visible light, fluorescent and LED room lighting
competes directly with the signal, and mains-powered lighting flickers at 100 or
120 Hz, right in the signal band. The shroud must seal and the sensor must sit
flush against the screen so that "dark" is truly dark. The decoder's adaptive
threshold and anti-flicker filter handle what remains.

## 6. Backlight behavior dominates a weak screen signal

LCD backlights are often dimmed by PWM (chopping them on and off), and adaptive
or local-dimming displays, such as mini-LED panels, adjust the backlight based on
what's on screen. That behaves like an automatic gain control fighting the
transmitter patch. The telltale sign is a *static* white screen producing a large
swing. The fix is maximum brightness (which often switches the backlight to
steady DC), a conventional panel, and turning off auto-brightness and color
temperature features.

## 7. The brightest screen wins

Across the screens tried, the bright/dark swing at 47 kΩ ranged from about 2,900
to 4,500 counts. When a screen has to drive the demo, measure several and use the
brightest one.

## 8. Match the test conditions to the demo

Tune the resistor against the real source, at the real distance, under the real
room lighting. A flashlight proxy is so much brighter than a screen that it will
send you to the wrong resistor.

## 9. Browser animation throttling smears symbols

When a tab is unfocused or covered, or the laptop is in battery saver, browsers
throttle `requestAnimationFrame`, and the page flashes much slower than 60 frames
per second (an irregular rate of about 8 Hz was observed). Keep the transmitter
tab full screen and focused, on AC power.

## 10. Aliasing can't be fixed in software

Sampling at 600 Hz puts the Nyquist limit at 300 Hz. Any flicker above 300 Hz
folds down into the signal band *before* it is digitized, and no software can
separate it out afterward. Only the analog capacitor ahead of the ADC helps there;
a larger capacitor lowers the corner frequency, within the speed limit from
lesson 2. The software low-pass filter only removes flicker below Nyquist.

## 11. Clock recovery must start on the mid-bit grid and re-anchor every bit

Manchester's reliable transitions are the mid-bit ones, so the decoder has to
find that grid first. It must also re-anchor to the actual mid-bit edge on every
bit: a sampler that assumes a fixed rate walks off the end of a long frame within
a few hundred bits.

## 12. The live buffer must be longer than the frame

A 127-byte image takes about 72 s at 15 bps. An early version of the decoder kept
only a 30-second rolling buffer, so it discarded the start of a long frame before
the end arrived: long payloads decoded on `--replay` but never live. The fix was
a 5-minute live buffer and throttled decode attempts.

## 13. With no error correction, binary fails hard

A single flipped bit fails the CRC. For text, a corrupted character is still
readable; for a binary file, one bad bit usually means the file won't open at
all. Keeping payloads small and looping the transmitter, so the decoder can wait
for a clean copy, is what makes file transfer practical at these rates.

## 14. A tiny file can hide a lot of bytes

The 16×16 demo smiley is 127 bytes of actual image. One copy of it turned out to
be 5,897 bytes, because an app had embedded about 5.7 KB of content-credential
(C2PA) metadata in it. Nothing about the picture looked different, but at 15 bps
that is the difference between about 72 seconds and about 52 minutes. Always
check a demo file's size in bytes, not just its dimensions, and strip metadata
before sending it. It's also a good classroom illustration of the project's
point: a file is just bytes, including the ones you can't see.

## 15. Join a transmission cleanly

These two issues turned up while testing the decoder against simulated looping
transmissions:

- **Starting to listen mid-frame can fool clock recovery.** A run of repeated
  bits in the payload produces evenly spaced edges half a bit apart, which looks
  like a preamble at double speed. The decoder now recognizes that pattern (see
  [PROTOCOL.md](PROTOCOL.md#how-the-decoder-reads-it)), but the most reliable
  habit is still to start the decoder before the transmitter, and to restart it
  for each new message or file.
- **The gap between looped frames must be a whole number of bits.** There are no
  edges during the gap, so the decoder coasts across it on its bit clock. A gap
  of 20 display frames is a whole number of bits at 15 and 30 bps but not at
  10 bps, where it left the decoder half a bit out of step with the next frame.
  The transmitter now rounds the gap up to whole bits, and the default is 24
  frames.
