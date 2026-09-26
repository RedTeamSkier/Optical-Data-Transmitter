# Hardware

The receiver is a single phototransistor, one resistor, and one capacitor on a
breadboard, read by an Arduino Uno R4. This page covers what to buy, how to wire
it, and why the component values are what they are. To build and test it step by
step, follow [TESTING.md](TESTING.md).

## Parts list

| Item | Detail | Notes |
|---|---|---|
| Arduino Uno R4 | Minima or WiFi (compatible R4 clones work) | The firmware uses the R4's 14-bit ADC via `analogReadResolution(14)`. An Uno R3 is not supported. |
| Vishay TEPT4400 | 3 mm, 2-lead, water-clear phototransistor | A visible-light ambient light sensor. See [About the sensor](#about-the-sensor). |
| Load resistor | **47 kΩ** (validated for screens) | Also have a few other values on hand for tuning, for example 10 kΩ, 22 kΩ, and 100 kΩ. |
| Capacitor | 10 nF ceramic, marked "103" | Non-polarized. Sits in parallel with the load resistor. |
| Breadboard and jumper wires | Half-size is plenty | |
| USB-C cable | Must carry data | A charge-only cable is a classic trap: the board powers up but no port appears. |
| Black heat-shrink tubing | Small enough to slip over a 3 mm part | Used **unshrunk** as a light shroud. |
| Foam pad, tape, or a clip | | Holds the shrouded sensor flush against the screen. |
| Host computer | macOS, Windows, or Linux | Runs the Arduino IDE and Python 3. |
| Transmitter computer | Any computer with a modern browser and a bright screen | See [Choosing a screen](../README.md#choosing-a-screen). |

Total cost is about $30, almost all of it the Arduino. The TEPT4400 itself costs
under a dollar.

## The circuit

```
   5V ─────────────┐
                   │ collector
               TEPT4400
                   │ emitter
   A0 ◄────────────● row X   (the sense node)
                   │
             ┌─────┴─────┐
             │           │
           47 kΩ       10 nF
             │           │
             └─────┬─────┘
                   │
   GND ────────────┘
```

Breadboard connections:

1. TEPT4400 collector leg → **5V** rail
2. TEPT4400 emitter leg → **row X**
3. Load resistor: **row X** → **GND** rail
4. 10 nF capacitor: **row X** → **GND** rail (in parallel with the resistor)
5. Jumper wire: **row X** → **A0**

**Row X is the heart of the circuit.** The sensor's emitter, one leg of the
resistor, one leg of the capacitor, and the wire to A0 must all sit in the same
connected breadboard column. If any one of them is in a neighboring column, the
circuit reads nothing useful.

**Sensor orientation.** The TEPT4400 has two leads and no base pin, and the leads
are hard to tell apart by eye. Find the orientation by trial: the load resistor
limits the current, so a brief reversal while testing is very unlikely to harm
it. If the reading stays flat near 0 no matter how much light you shine on it,
flip the sensor.

**Polarity matters for decoding.** The decoder expects *more light → higher
numbers*. If brighter light gives *lower* numbers, the sensor and resistor are
swapped (sensor on the GND side, resistor on the 5V side). Rewire so the sensor
is on the 5V side.

## How it works electrically

The phototransistor passes a current roughly proportional to the light falling
on it. That current flows through the load resistor to ground, so the voltage at
row X is the current times the resistance. The Arduino's ADC converts 0–5 V into
a number from 0 to 16,383. More light means more current, a higher voltage at
A0, and a bigger number.

## Choosing the load resistor

The load resistor sets how many volts you get per unit of light. A bigger
resistor gives a bigger swing but clips at the ADC ceiling (16,383) sooner; a
smaller one gives less swing but more headroom. The right value depends on how
bright your source is, and you find it by measurement rather than by formula
(Phase 5 of [TESTING.md](TESTING.md)).

The goal is the largest bright/dark swing whose bright level stays comfortably
below the ceiling, under about 15,500.

A laptop screen is a surprisingly weak source for this sensor, so it needs a
**large** resistor. In testing, a screen at near-contact produced only about 300
counts of signal with a 2 kΩ load, while 47 kΩ produced swings of roughly 2,900
to 4,500 counts depending on the screen. A bright LED or flashlight needs a
**small** resistor instead, in the range of hundreds of ohms to about 2 kΩ.

## Speed: the resistor and capacitor form a low-pass filter

The load resistor and the 10 nF capacitor make an RC low-pass filter with time
constant `τ = R × C` and corner frequency `f = 1 / (2π·R·C)`. The filter sets how
fast the voltage at A0 can follow the light.

Manchester encoding switches the light at the **half-bit** (symbol) rate, so the
rule of thumb is to keep `τ` at least 10× shorter than one half-bit period. A
half-bit lasts 33.3 ms at 15 bps and 16.7 ms at 30 bps, so `τ` must be at most
about 3.3 ms at 15 bps and about 1.7 ms at 30 bps.

| R (with 10 nF) | τ | Corner frequency | OK at 15 bps? | OK at 30 bps? |
|---|---|---|---|---|
| 2 kΩ | 0.02 ms | 8 kHz | Yes | Yes |
| 10 kΩ | 0.1 ms | 1.6 kHz | Yes | Yes |
| **47 kΩ (validated)** | **0.47 ms** | **340 Hz** | **Yes** | **Yes** |
| 100 kΩ | 1 ms | 160 Hz | Yes | Yes |
| 1 MΩ | 10 ms | 16 Hz | **No: bits smear** | **No** |

**A huge swing at a very high resistance is a trap.** A brightness test measures
range, not speed. At 1 MΩ the min/max test shows an impressive swing, but the
filter is slower than the symbols, so the signal can't carry data.

## The filter capacitor

The 10 nF capacitor does three jobs:

1. It removes high-frequency electrical noise from the sense node.
2. It acts as a partial **anti-aliasing filter**. The Arduino samples at 600 Hz,
   so anything flickering faster than 300 Hz, such as a screen backlight's PWM,
   folds down into the signal band before it is digitized. Software cannot remove
   aliased flicker after the fact; only an analog filter ahead of the ADC helps.
3. It gives the ADC a low-impedance charge reservoir to sample from, which
   matters with a source as high-impedance as 47 kΩ.

The validated value is 10 nF. If aliased backlight flicker is a problem with
your screen, a larger capacitor lowers the corner and filters more of it: for
example, 22 nF with 47 kΩ gives `τ ≈ 1.0 ms` (about 150 Hz), which still passes
the speed rule at 30 bps. Always recheck `τ` against your bit rate after changing
either part.

Room-light flicker at 100/120 Hz is handled by the shroud and by the decoder's
software low-pass filter, not by this capacitor.

## The shroud

Slip a short piece of black heat-shrink tubing over the sensor as an open-ended
tube. It should cover the body and sides and extend about 3–5 mm past the front
dome, leaving the dome itself open to the front. **Do not heat it.** It only
needs to block side light, not grip.

Press the open end flush against the screen, gently, and hold it there with foam,
tape, or a clip. Sealed this way, the sensor sees only the transmitter patch and
not the room. This is the single biggest improvement to signal quality.

## About the sensor

The TEPT4400 is a **visible-light** ambient light sensor, not a near-infrared
part. Its sensitivity peaks at 570 nm and covers roughly 440–800 nm, matched to
the human eye. It was designed as an ambient light sensor for display backlight
control. Its lens accepts
light within about ±30° of its axis.

A screen reads weaker than a flashlight for a physical reason, not a spectral
one: an LCD is a dim, diffuse emitter, while a flashlight pushes far more light
into the sensor's narrow acceptance cone. The fix for a weak screen is
brightness and coupling (a brighter screen, maximum brightness, a flush seal, a
larger load resistor), not a different sensor.

The sensor itself responds far faster than this link needs. The RC filter above
is what sets the speed limit.

## Alternative light sources

The transmitter in this repo drives a laptop screen, but any light source that
can be switched on and off under software control can carry the same frames. An
LED, such as a development board's onboard LED or a discrete LED on a
microcontroller pin, is a physically stronger source: a bright point source,
very fast switching, high contrast, easy to shroud, and no refresh-rate ceiling.

To use one, the source must emit the frame format in [PROTOCOL.md](PROTOCOL.md),
and the receiver will need a much smaller load resistor (re-run Phase 5 of
[TESTING.md](TESTING.md)). Rates well above the screen's ceiling would also need
a higher sample rate in both the firmware and the decoder.
