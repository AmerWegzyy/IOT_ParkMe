# Unit Tests

This folder contains validation tests for checking sensors and hardware components.

## Available Tests

### 1. fsr_comparison_test/
**Purpose**: Compare raw signal strength between the two FSR sensors

**Use when**:
- One sensor seems weaker than the other
- Steps are only detected on one foot
- You want to verify sensor calibration

**What it does**:
- Measures baseline, standing, heavy pressure, and step simulation
- Shows min/max/average/range for each sensor
- Calculates percentage difference between sensors
- Provides calibration recommendations

**Quick start**: Upload sketch, open Serial Monitor (115200 baud), follow on-screen instructions

### 2. sender_sketch/
ESP-NOW sender validation tests

### 3. receiver_sketch/
ESP-NOW receiver validation tests

### 4. fsr_testing/
Basic FSR sensor functionality tests

---

## When to Use These Tests

- **Before first use**: Run fsr_comparison_test to check sensor matching
- **After hardware changes**: Re-run tests to verify connections
- **Troubleshooting**: If one foot isn't detecting, run fsr_comparison_test
- **Calibration**: Use test results to set per-sensor thresholds
