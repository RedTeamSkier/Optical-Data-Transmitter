// Optical Data Transfer Concept - receiver STREAMING firmware (production)
// Board: Arduino Uno R4 (Minima or WiFi)
//
// Samples A0 at a steady 600 Hz and streams each reading as 2 raw bytes,
// little-endian (low byte first). All decoding happens on the host in
// decoder/optical_rx.py.
//
// Do NOT open the Serial Monitor/Plotter with this loaded - the output is
// raw binary and looks like garbage. Use test/check.py or the decoder.
//
// Interface contract:
//   raw, little-endian, unsigned 16-bit samples, 2 bytes/sample,
//   low byte first, no delimiters, 600 samples/sec, 115200 baud.
//   Unpack with struct '<H'. Values 0..16383 (14-bit).
//
// Timing uses a micros() schedule rather than a hardware-timer ISR. At 600 Hz
// with an otherwise-empty loop the jitter is a few microseconds out of
// ~1667 us (<0.5%). The (int32_t)(now - nextT) comparison is rollover-safe
// (micros() wraps about every 71 minutes). For much higher rates, switch to a
// hardware timer (FspTimer on the R4).

const uint32_t SAMPLE_HZ = 600;
const uint32_t PERIOD_US = 1000000UL / SAMPLE_HZ;  // ~1666 us
uint32_t nextT;

void setup() {
  Serial.begin(115200);
  analogReadResolution(14);   // Uno R4: 14-bit ADC -> 0..16383
  nextT = micros();
}

void loop() {
  uint32_t now = micros();
  if ((int32_t)(now - nextT) >= 0) {
    nextT += PERIOD_US;
    uint16_t s = analogRead(A0);
    Serial.write((uint8_t)(s & 0xFF));   // low byte first
    Serial.write((uint8_t)(s >> 8));     // then high byte
  }
}
