import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 1. Định nghĩa đường dẫn file PNG gốc
input_file_path = "/home/thomas/Pictures/Screenshots/meaning-of-saigon-2_1702214121.jpeg"


def run_prepare_image_bytes_jpeg():
    from tests.test_ai_prediction import prepare_image_bytes

    img_bytes, meta = prepare_image_bytes(input_file_path)
    assert meta["converted"] is False
    assert len(img_bytes) > 0


def run_extract_json_from_image():
    from tests.test_ai_prediction import extract_geolocation_from_image

    output = extract_geolocation_from_image(
        input_file_path,
        "Extract hourly raw data and convert to JSON"
    )
    print(output)
    assert output["result"]["city"] == "Ho Chi Minh City"
    assert output["result"]["location_name"] == "Notre Dame Cathedral Basilica of Saigon"


def run_extract_weather_info_from_text(lat: float, lon: float):
    from test_poc.test_windy_scraper import process_weather_data

    asyncio.run(process_weather_data(lat, lon, 2))


def test_direct_execution_help(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "latitude" in result.stdout
    assert "longitude" in result.stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the live weather crawl.")
    parser.add_argument("--latitude", type=float, default=10.7594258)
    parser.add_argument("--longitude", type=float, default=106.6233823)
    args = parser.parse_args()

    from main_config import setup_logging

    setup_logging()
    # run_prepare_image_bytes_jpeg()
    # run_extract_json_from_image()
    run_extract_weather_info_from_text(args.latitude, args.longitude)
    print("All unit tasks finished.")
