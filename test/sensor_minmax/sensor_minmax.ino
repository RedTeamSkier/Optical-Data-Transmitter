// Optical Data Transfer Concept - sensor_minmax (screen / resistor sweep)
// Board: Arduino Uno R4 (Minima or WiFi)
//
// Prints a line only when a new record LOW or HIGH appears, so the output
// settles on the dynamic range of whatever the sensor is looking at.
// Open Tools > Serial Monitor at 115200 baud.
//
// To clear the records between tests: press RESET on the board, or type any
// character in the Serial Monitor and press Enter.
//
// Used in docs/TESTING.md Phase 5 (choose the screen, tune the load resistor).

uint16_t lo = 16383, hi = 0;

void clearRecords() {
  lo = 16383;
  hi = 0;
  Serial.println("-- records cleared --");
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(14);   // Uno R4: 14-bit ADC -> 0..16383
}

void loop() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    clearRecords();
  }

  uint16_t s = analogRead(A0);
  if (s < lo) { lo = s; Serial.print("new LOW  "); Serial.println(lo); }
  if (s > hi) { hi = s; Serial.print("new HIGH "); Serial.println(hi); }
  delay(2);
}
