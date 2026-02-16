"""
The main loop for the Inky Frame.

References
https://forums.pimoroni.com/t/inky-frame-deep-sleep-explanation/19965/20
https://gist.github.com/jjsanderson/17cadcaba2a868596e3d4a01488955d6
https://github.com/pimoroni/inky-frame/tree/main

"""

import gc
import uos
import time
import ntptime
import machine
import jpegdec
import inky_helper as ih
import inky_frame as iframe

from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY

import sdcard
from urllib import urequest
from secrets import WIFI_SSID, WIFI_PASSWORD

FILENAME = "/sd/image.jpg"  # Where we save the image
SERVER = "http://192.168.1.200:8090/"  # The server we query
VALID_DIRECTIONS = ["next", "previous", "random"]  # Valid directions for the query

# A short delay to give USB a chance to initialize
time.sleep(0.5)
graphics = PicoGraphics(DISPLAY)
WIDTH, HEIGHT = graphics.get_bounds()
graphics.set_font("bitmap8")

# Initialize the RTC
rtc = machine.RTC()

# Initialize the SD card
sd_spi = machine.SPI(
    0,
    sck=machine.Pin(18, machine.Pin.OUT),
    mosi=machine.Pin(19, machine.Pin.OUT),
    miso=machine.Pin(16, machine.Pin.OUT),
)
sd = sdcard.SDCard(sd_spi, machine.Pin(22))
uos.mount(sd, "/sd")

# Garbage collect after initialization
gc.collect()


def minutes_until_wake() -> int:
    """Calculate the number of minutes until the next update at the top of the hour.

    Returns:
        int: The number of minutes until the next update.
    """
    # Update the RTC from the NTP server
    try:
        ntptime.settime()
    except OSError:
        print("Unable to contact NTP server")

    # Calculate the number of minutes until the next update
    dt_tuple = rtc.datetime()
    _, _, _, _, _, mm, ss, _ = dt_tuple

    # Garbage collect before returning
    gc.collect()
    return int(60 - (mm + ss / 60))


def download_image(direction: str) -> bool:
    """Download an image from the server in the given direction, save to the SD card.

    Args:
        direction (str): The query direction.

    Returns:
        bool: True if successful, False otherwise.
    """
    # Validate the direction
    if direction not in VALID_DIRECTIONS:
        print('Invalid direction: "{}"'.format(direction))
        return False

    # Build the URL
    url = SERVER + direction
    socket = None
    try:
        # Pulse the network LED and try up to 10 times to connect to the server with exponential backoff
        # This assumes we are on already connected to WiFi
        ih.pulse_network_led()
        max_tries = 10
        attempts = 0
        backoff = 0.5
        success = False
        while not success:
            attempts += 1
            if attempts > max_tries:
                print('Failed to connect to "{}" after {} tries'.format(url, max_tries))
                return False
            print('[{}/{}] Attempting to connect to "{}"'.format(attempts, max_tries, url))
            try:
                socket = urequest.urlopen(url)
                success = True
            except OSError as e:
                print('Unable to open URL "{}"'.format(url))
                print(e)
                time.sleep(backoff)
                backoff *= 2
            finally:
                if not success and socket is not None:
                    socket.close()
                gc.collect()

        # Stream the image data from the socket onto the disk in 1024 byte chunks
        # I've tried large chunk sizes but it seemed less stable so just keeping it safe
        print(f"Connection succeeded, downloading...")
        chunk_count = 0
        data = bytearray(1024)
        with open(FILENAME, "wb") as f:
            while True:
                chunk_count += 1
                print(f"Downloading image chunk {chunk_count}...")
                if socket.readinto(data) == 0:
                    break
                f.write(data)

    # Finally, stop the network LED, close the socket, and collect garbage
    finally:
        ih.stop_network_led()
        if socket is not None:
            socket.close()
        gc.collect()

    print(f"Image downloaded successfully, total {chunk_count * 1024} bytes")
    return True


def main(direction: str = "next") -> None:
    """Main function to run the application.

    Args:
        direction (str): The query direction, default "next".

    Returns:
        None
    """
    # Clear LEDs
    ih.clear_button_leds()
    ih.led_warn.off()

    # Make sure we're connected to the internet, this is surprisingly painful
    check = ih.is_internet_connected()
    if check:
        print("Internet connection is up!")
    else:
        check = ih.network_connect(WIFI_SSID, WIFI_PASSWORD)
        if not check:
            print("Unable to connect to WiFi")
            ih.led_warn.on()
            iframe.sleep_for(minutes_until_wake())
            return

    # Download the image
    try:
        result = download_image(direction)
    except Exception as e:
        result = False
        print("Error downloading image:")
        print(e)

    # If download failed, turn on the warn LED and wait for the next update
    if not result:
        print("Download failed, waiting on the next update...")
        ih.led_warn.on()
        iframe.sleep_for(minutes_until_wake())

    # Otherwise, draw the image to the screen and wait for the next update
    else:
        print("Image downloaded successfully, drawing to screen...")
        # Clear the screen
        ih.led_warn.on()
        graphics.set_pen(1)
        graphics.clear()

        # Buffer the image
        jpeg = jpegdec.JPEG(graphics)
        jpeg.open_file(FILENAME)
        jpeg.decode()

        # Draw the image
        print("Drawing image...")
        graphics.update()

        # Turn off the warn LED and wait for the next update
        ih.led_warn.off()
        gc.collect()
        iframe.sleep_for(minutes_until_wake())


# Main loop, allows the user to interrupt the sleep by pressing a button
while True:
    print("Starting main loop...")
    if ih.inky_frame.button_a.read():
        main("previous")
    elif ih.inky_frame.button_c.read():
        main("random")
    elif ih.inky_frame.button_e.read():
        main("next")
    else:
        main()
