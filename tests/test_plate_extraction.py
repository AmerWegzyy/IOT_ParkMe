import unittest

from Backend.parking_logic import extract_plate_from_ocr_text, is_valid_plate_number


class PlateExtractionTests(unittest.TestCase):
    def test_clean_seven_digit_plate(self):
        self.assertEqual(extract_plate_from_ocr_text("1234567"), "1234567")

    def test_clean_eight_digit_plate(self):
        self.assertEqual(extract_plate_from_ocr_text("12345678"), "12345678")

    def test_dashed_israeli_format_seven_digits(self):
        self.assertEqual(extract_plate_from_ocr_text("12-345-67"), "1234567")

    def test_dashed_israeli_format_eight_digits(self):
        self.assertEqual(extract_plate_from_ocr_text("123-45-678"), "12345678")

    def test_plate_with_surrounding_noise_lines(self):
        raw = "IL\n12-345-67\nPermit No. 4521"
        self.assertEqual(extract_plate_from_ocr_text(raw), "1234567")

    def test_does_not_concatenate_digits_across_lines(self):
        # Old behavior would merge these into "4521123" and report a phantom
        # plate; new behavior treats the image as unreadable instead.
        raw = "Permit 4521\n123"
        self.assertEqual(extract_plate_from_ocr_text(raw), "")

    def test_short_fragment_rejected(self):
        self.assertEqual(extract_plate_from_ocr_text("123"), "")

    def test_ten_digit_phone_number_rejected(self):
        self.assertEqual(extract_plate_from_ocr_text("054-565-4307"), "")

    def test_spaces_as_separators_within_one_line(self):
        self.assertEqual(extract_plate_from_ocr_text("12 345 67"), "1234567")

    def test_plate_next_to_extra_digit_token_on_same_text(self):
        # The tight token pass finds the plate without merging the lone digit.
        raw = "1234567 8"
        self.assertEqual(extract_plate_from_ocr_text(raw), "1234567")

    def test_empty_and_no_text(self):
        self.assertEqual(extract_plate_from_ocr_text(""), "")
        self.assertEqual(extract_plate_from_ocr_text("NO PARKING"), "")

    def test_is_valid_plate_number_bounds(self):
        self.assertTrue(is_valid_plate_number("1234567"))
        self.assertTrue(is_valid_plate_number("12345678"))
        self.assertFalse(is_valid_plate_number("123456"))
        self.assertFalse(is_valid_plate_number("123456789"))
        self.assertFalse(is_valid_plate_number("12A4567"))


if __name__ == "__main__":
    unittest.main()
