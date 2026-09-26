// Optical Data Transfer Concept - sensor_test (human-readable)
// Board: Arduino Uno R4 (Minima or WiFi)
//
// Prints one 14-bit light reading (0..16383) per line, roughly 500 lines/s.
// Open Tools > Serial Plotter (or Serial Monitor) at 115200 baud.
// More light -> higher number. Cover the sensor and the line should drop;
// shine a light on it and the line should jump.
//
// Used in docs/TESTING.md Phase 3 (see the light) and Phase 6 (seal check).

void setup() {
  Serial.begin(115200);
  analogReadResolution(14);   // Uno R4: 14-bit ADC -> 0..16383
}

void loop() {
  Serial.println(analogRead(A0));
  delay(2);
}
