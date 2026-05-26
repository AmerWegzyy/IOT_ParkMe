import cv2
import numpy as np
import easyocr
import re

# Initialize the EasyOCR reader into memory once when the server boots.
# We set gpu=False to ensure it runs smoothly on a standard WSL CPU setup.
print("[SYSTEM] Loading EasyOCR AI models into memory... (This may take a moment)")
reader = easyocr.Reader(['en'], gpu=False)
print("[SYSTEM] AI Model loaded successfully!")
aaaaaaaaaaaaaaaaaaaaaa
def extract_license_plate(image_bytes: bytes) -> str:
    """
    Takes raw image bytes received from the ESP32-CAM, applies image processing,
    and extracts the license plate text string. Returns an empty string if unreadable.
    """
    try:
        # 1. Convert raw bytes into a numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        
        # 2. Decode the numpy array into an OpenCV image format
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            print("[OCR ERROR] Failed to decode image bytes from ESP32.")
            return ""

        # 3. Image Pre-processing (Crucial for ESP32-CAM quality)
        # Convert to Grayscale to remove color distraction
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply a Bilateral Filter to reduce noise while keeping the edges of the numbers sharp
        bfilter = cv2.bilateralFilter(gray, 11, 17, 17)

        # 4. Run the EasyOCR detection matrix
        # detail=0 forces the library to return just the text strings, omitting bounding box coordinates
        results = reader.readtext(bfilter, detail=0)
        
        if not results:
            print("[OCR WARNING] No text detected in the image frame.")
            return ""

        print(f"[OCR RAW DETECTIONS] {results}")

        # 5. Clean and format the extracted text
        # Combine everything found into one uppercase string
        combined_text = "".join(results).upper()
        
        # Regex filter: Keep ONLY letters (A-Z), numbers (0-9), and hyphens (-)
        cleaned_plate = re.sub(r'[^A-Z0-9-]', '', combined_text)

        # Basic validation to ensure it didn't just read a random speck of dirt as a letter
        if len(cleaned_plate) < 4:
            print(f"[OCR WARNING] Extracted text '{cleaned_plate}' is too short to be a valid plate.")
            return ""

        print(f"[OCR SUCCESS] Final Validated Plate: '{cleaned_plate}'")
        return cleaned_plate

    except Exception as e:
        print(f"[OCR FATAL ERROR] An unexpected exception occurred during processing: {e}")
        return ""

# --- Local Testing Block ---
# If you run this file directly (python3 analyze_photo.py), it will test itself.
if __name__ == "__main__":
    print("\n--- Running Local AI Test ---")
    # To test this locally, place a sample car image named 'test_car.jpg' in your folder
    try:
        with open("test_car.jpg", "rb") as image_file:
            test_bytes = image_file.read()
            result = extract_license_plate(test_bytes)
            if result:
                print(f"Test Passed! Plate: {result}")
            else:
                print("Test Failed: Could not read plate from test_car.jpg")
    except FileNotFoundError:
        print("Skipping local test: 'test_car.jpg' not found in directory.")