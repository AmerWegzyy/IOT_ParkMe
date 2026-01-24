/*
 * FSR Sensor Comparison Test
 * 
 * Purpose: Compare raw signal strength between two FSR sensors
 * 
 * Usage:
 * 1. Upload this sketch to ESP32
 * 2. Open Serial Monitor (115200 baud)
 * 3. Follow on-screen instructions:
 *    - Test 1: No pressure (baseline noise)
 *    - Test 2: Light pressure (standing normally)
 *    - Test 3: Heavy pressure (shifting weight)
 *    - Test 4: Step simulation (lift and press repeatedly)
 * 4. Copy results and send to developer
 * 
 * The test will show min/max/average for both sensors in each test
 */

// Pin definitions
const int RIGHT_PIN = 33;
const int LEFT_PIN = 32;

// Test configuration
const uint16_t SAMPLES_PER_TEST = 1000;
const uint8_t DELAY_MS = 10;

// Statistics structure
struct SensorStats {
  int minVal = 4095;
  int maxVal = 0;
  long sumVal = 0;
  int avgVal = 0;
  int rangeVal = 0;
  
  void reset() {
    minVal = 4095;
    maxVal = 0;
    sumVal = 0;
    avgVal = 0;
    rangeVal = 0;
  }
  
  void update(int reading) {
    if (reading < minVal) minVal = reading;
    if (reading > maxVal) maxVal = reading;
    sumVal += reading;
  }
  
  void calculate(int samples) {
    avgVal = sumVal / samples;
    rangeVal = maxVal - minVal;
  }
};

SensorStats rightStats;
SensorStats leftStats;

// Test number
int currentTest = 0;

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  // Configure pins
  pinMode(RIGHT_PIN, INPUT);
  pinMode(LEFT_PIN, INPUT);
  
  Serial.println("\n\n========================================");
  Serial.println("   FSR SENSOR COMPARISON TEST");
  Serial.println("========================================\n");
  Serial.println("This test will compare the raw output of both FSR sensors.");
  Serial.println("We'll run 4 tests to measure signal strength differences.\n");
  Serial.println("Hardware Info:");
  Serial.print("  - Right FSR: GPIO ");
  Serial.println(RIGHT_PIN);
  Serial.print("  - Left FSR:  GPIO ");
  Serial.println(LEFT_PIN);
  Serial.print("  - ADC Range: 0-4095 (12-bit)");
  Serial.println("\n");
  
  delay(3000);
  
  Serial.println("Ready to start tests!\n");
  Serial.println("Commands:");
  Serial.println("  Type '1' - Test 1: No Pressure (Baseline)");
  Serial.println("  Type '2' - Test 2: Standing Normally");
  Serial.println("  Type '3' - Test 3: Heavy Pressure");
  Serial.println("  Type '4' - Test 4: Step Simulation (10 steps)");
  Serial.println("  Type 'r' - Show Results Summary");
  Serial.println("  Type 'c' - Continuous Live Readings");
  Serial.println();
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    switch (cmd) {
      case '1':
        runTest1_Baseline();
        break;
      case '2':
        runTest2_Standing();
        break;
      case '3':
        runTest3_HeavyPressure();
        break;
      case '4':
        runTest4_StepSimulation();
        break;
      case 'r':
      case 'R':
        showResultsSummary();
        break;
      case 'c':
      case 'C':
        continuousReadings();
        break;
    }
  }
}

// ===========================================
// TEST 1: Baseline (No Pressure)
// ===========================================
void runTest1_Baseline() {
  Serial.println("\n========================================");
  Serial.println("TEST 1: BASELINE (NO PRESSURE)");
  Serial.println("========================================");
  Serial.println("Instructions: DO NOT stand on sensors");
  Serial.println("This measures the resting/idle state");
  Serial.println();
  Serial.println("Starting in 3 seconds...");
  delay(3000);
  
  runSamplingTest("Baseline");
  
  Serial.println("\n✓ Test 1 Complete");
  Serial.println("Type '2' for next test or 'r' for results\n");
}

// ===========================================
// TEST 2: Standing Normally
// ===========================================
void runTest2_Standing() {
  Serial.println("\n========================================");
  Serial.println("TEST 2: STANDING NORMALLY");
  Serial.println("========================================");
  Serial.println("Instructions: Stand normally on BOTH sensors");
  Serial.println("Distribute weight evenly, don't move");
  Serial.println();
  Serial.println("Starting in 5 seconds... Get ready!");
  delay(5000);
  
  runSamplingTest("Standing");
  
  Serial.println("\n✓ Test 2 Complete");
  Serial.println("Type '3' for next test or 'r' for results\n");
}

// ===========================================
// TEST 3: Heavy Pressure
// ===========================================
void runTest3_HeavyPressure() {
  Serial.println("\n========================================");
  Serial.println("TEST 3: HEAVY PRESSURE");
  Serial.println("========================================");
  Serial.println("Instructions: Shift ALL weight to RIGHT foot first,");
  Serial.println("              then shift ALL weight to LEFT foot");
  Serial.println();
  Serial.println("Starting in 5 seconds... Get ready!");
  delay(5000);
  
  Serial.println("Sampling... (shift weight during this time)");
  runSamplingTest("Heavy Pressure");
  
  Serial.println("\n✓ Test 3 Complete");
  Serial.println("Type '4' for next test or 'r' for results\n");
}

// ===========================================
// TEST 4: Step Simulation
// ===========================================
void runTest4_StepSimulation() {
  Serial.println("\n========================================");
  Serial.println("TEST 4: STEP SIMULATION");
  Serial.println("========================================");
  Serial.println("Instructions: Perform 10 steps in place");
  Serial.println("              Alternate feet naturally");
  Serial.println();
  Serial.println("Starting in 5 seconds... Get ready!");
  delay(5000);
  
  Serial.println("START STEPPING NOW!");
  Serial.println();
  
  // Track individual steps
  int stepCount = 0;
  int lastRightMax = 0;
  int lastLeftMax = 0;
  bool rightActive = false;
  bool leftActive = false;
  
  rightStats.reset();
  leftStats.reset();
  
  unsigned long startTime = millis();
  unsigned long duration = 15000; // 15 seconds
  
  while (millis() - startTime < duration) {
    int rightRaw = analogRead(RIGHT_PIN);
    int leftRaw = analogRead(LEFT_PIN);
    
    rightStats.update(rightRaw);
    leftStats.update(leftRaw);
    
    // Detect step peaks (simplified)
    if (rightRaw > 800 && !rightActive) {
      rightActive = true;
      stepCount++;
      Serial.print("  Step ");
      Serial.print(stepCount);
      Serial.print(" - RIGHT: ");
      Serial.println(rightRaw);
    }
    if (rightRaw < 400) rightActive = false;
    
    if (leftRaw > 800 && !leftActive) {
      leftActive = true;
      stepCount++;
      Serial.print("  Step ");
      Serial.print(stepCount);
      Serial.print(" - LEFT: ");
      Serial.println(leftRaw);
    }
    if (leftRaw < 400) leftActive = false;
    
    delay(10);
  }
  
  rightStats.calculate(duration / DELAY_MS);
  leftStats.calculate(duration / DELAY_MS);
  
  Serial.println("\nTest 4 Results:");
  Serial.print("  Steps detected: ");
  Serial.println(stepCount);
  printComparison("Step Simulation");
  
  Serial.println("\n✓ Test 4 Complete");
  Serial.println("Type 'r' to see full results summary\n");
}

// ===========================================
// Core Sampling Function
// ===========================================
void runSamplingTest(const char* testName) {
  rightStats.reset();
  leftStats.reset();
  
  Serial.print("Collecting ");
  Serial.print(SAMPLES_PER_TEST);
  Serial.println(" samples...");
  
  // Progress bar
  int progressMarks = 50;
  int samplesPerMark = SAMPLES_PER_TEST / progressMarks;
  
  Serial.print("[");
  for (int i = 0; i < progressMarks; i++) Serial.print(" ");
  Serial.print("]");
  Serial.print("\r[");
  
  for (uint16_t i = 0; i < SAMPLES_PER_TEST; i++) {
    int rightRaw = analogRead(RIGHT_PIN);
    int leftRaw = analogRead(LEFT_PIN);
    
    rightStats.update(rightRaw);
    leftStats.update(leftRaw);
    
    // Update progress bar
    if (i % samplesPerMark == 0) {
      Serial.print("=");
    }
    
    delay(DELAY_MS);
  }
  
  Serial.println("] Done!");
  
  rightStats.calculate(SAMPLES_PER_TEST);
  leftStats.calculate(SAMPLES_PER_TEST);
  
  printComparison(testName);
}

// ===========================================
// Print Comparison Results
// ===========================================
void printComparison(const char* testName) {
  Serial.println();
  Serial.println("------------------------------------------");
  Serial.print("  ");
  Serial.println(testName);
  Serial.println("------------------------------------------");
  
  Serial.println("                 RIGHT    LEFT    DIFF");
  Serial.println("------------------------------------------");
  
  // Minimum
  Serial.print("  Min:         ");
  Serial.print(rightStats.minVal);
  printSpaces(rightStats.minVal);
  Serial.print(leftStats.minVal);
  printSpaces(leftStats.minVal);
  Serial.println(rightStats.minVal - leftStats.minVal);
  
  // Maximum
  Serial.print("  Max:         ");
  Serial.print(rightStats.maxVal);
  printSpaces(rightStats.maxVal);
  Serial.print(leftStats.maxVal);
  printSpaces(leftStats.maxVal);
  Serial.println(rightStats.maxVal - leftStats.maxVal);
  
  // Average
  Serial.print("  Average:     ");
  Serial.print(rightStats.avgVal);
  printSpaces(rightStats.avgVal);
  Serial.print(leftStats.avgVal);
  printSpaces(leftStats.avgVal);
  Serial.println(rightStats.avgVal - leftStats.avgVal);
  
  // Range
  Serial.print("  Range:       ");
  Serial.print(rightStats.rangeVal);
  printSpaces(rightStats.rangeVal);
  Serial.print(leftStats.rangeVal);
  printSpaces(leftStats.rangeVal);
  Serial.println(rightStats.rangeVal - leftStats.rangeVal);
  
  Serial.println("------------------------------------------");
  
  // Analysis
  float ratioAvg = (float)rightStats.avgVal / (float)leftStats.avgVal;
  float ratioMax = (float)rightStats.maxVal / (float)leftStats.maxVal;
  
  Serial.println("\n  Analysis:");
  Serial.print("    Average ratio (R/L): ");
  Serial.println(ratioAvg, 2);
  Serial.print("    Max ratio (R/L):     ");
  Serial.println(ratioMax, 2);
  
  if (abs(ratioAvg - 1.0) > 0.3) {
    Serial.println("    ⚠ WARNING: >30% difference detected!");
    Serial.println("    Sensors have significantly different sensitivity.");
  } else if (abs(ratioAvg - 1.0) > 0.15) {
    Serial.println("    ⚠ CAUTION: 15-30% difference detected.");
    Serial.println("    Per-sensor calibration recommended.");
  } else {
    Serial.println("    ✓ Sensors are well-matched (<15% difference).");
  }
  
  Serial.println();
}

// Helper: Print spacing for alignment
void printSpaces(int val) {
  int digits = 1;
  int temp = val;
  while (temp >= 10) { digits++; temp /= 10; }
  
  for (int i = digits; i < 9; i++) {
    Serial.print(" ");
  }
}

// ===========================================
// Continuous Live Readings
// ===========================================
void continuousReadings() {
  Serial.println("\n========================================");
  Serial.println("CONTINUOUS LIVE READINGS");
  Serial.println("========================================");
  Serial.println("Press any key to stop");
  Serial.println();
  Serial.println("Time(ms)  RIGHT   LEFT   DIFF");
  Serial.println("----------------------------------");
  
  unsigned long startTime = millis();
  
  while (!Serial.available()) {
    int rightRaw = analogRead(RIGHT_PIN);
    int leftRaw = analogRead(LEFT_PIN);
    int diff = rightRaw - leftRaw;
    
    Serial.print(millis() - startTime);
    Serial.print("\t");
    Serial.print(rightRaw);
    Serial.print("\t");
    Serial.print(leftRaw);
    Serial.print("\t");
    Serial.println(diff);
    
    delay(100);
  }
  
  // Clear serial buffer
  while (Serial.available()) Serial.read();
  
  Serial.println("\nStopped.");
  Serial.println("Type a command to continue\n");
}

// ===========================================
// Results Summary
// ===========================================
void showResultsSummary() {
  Serial.println("\n========================================");
  Serial.println("  RESULTS SUMMARY");
  Serial.println("========================================");
  Serial.println("\nIf you completed all tests, the results above show:");
  Serial.println("  - Test 1: Baseline noise (should be very low, <100)");
  Serial.println("  - Test 2: Normal standing pressure");
  Serial.println("  - Test 3: Maximum pressure each sensor can read");
  Serial.println("  - Test 4: Dynamic stepping behavior");
  Serial.println();
  Serial.println("Key metrics to look at:");
  Serial.println("  1. Average ratio (R/L) in Test 2");
  Serial.println("     - Should be close to 1.0 for matched sensors");
  Serial.println("     - If >1.3 or <0.7, sensors are very different");
  Serial.println();
  Serial.println("  2. Max values in Test 3");
  Serial.println("     - Shows maximum signal each sensor can produce");
  Serial.println("     - Used to set individual thresholds");
  Serial.println();
  Serial.println("  3. Range in Test 4");
  Serial.println("     - Shows signal variation during stepping");
  Serial.println("     - Helps tune pressure buffer values");
  Serial.println();
  Serial.println("========================================\n");
}
