"""
Based on https://github.com/pimoroni/inky-frame/blob/main/examples/inkylauncher/inky_helper.py with some modifications of my own.
"""
import os
import gc
import math
import time
import network
import socket
from pcf85063a import PCF85063A
from machine import Pin, PWM, Timer
from pimoroni_i2c import PimoroniI2C

import inky_frame
WIFI_STATUS_CODES = {-3: "STAT_WRONG_PASSWORD - Wrong password",
                     -2: "STAT_NO_AP_FOUND - No access point replied",
                     -1: "STAT_CONNECT_FAIL - Connection failed",
                     0: "STAT_IDLE - Idle state",
                     1: "STAT_CONNECTING - Connecting",
                     2: "STAT_NO_IP - Connected, waiting for IP",
                     3: "STAT_GOT_IP - Connection successful (has IP address)"}


# Pin setup for VSYS_HOLD needed to sleep and wake.
HOLD_VSYS_EN_PIN = 2
hold_vsys_en_pin = Pin(HOLD_VSYS_EN_PIN, Pin.OUT)

# initialise the pcf85063a real time clock chip
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
i2c = PimoroniI2C(I2C_SDA_PIN, I2C_SCL_PIN, 100000)
rtc = PCF85063A(i2c)

led_warn = Pin(6, Pin.OUT)

# set up for the network LED
network_led_pwm = PWM(Pin(7))
network_led_pwm.freq(1000)
network_led_pwm.duty_u16(0)

network_led_timer = Timer(-1)
network_led_pulse_speed_hz = 1

# set the brightness of the network led
def network_led(brightness):
    brightness = max(0, min(100, brightness))  # clamp to range
    # gamma correct the brightness (gamma 2.8)
    value = int(pow(brightness / 100.0, 2.8) * 65535.0 + 0.5)
    network_led_pwm.duty_u16(value)


def network_led_callback(t):
    # updates the network led brightness based on a sinusoid seeded by the current time
    brightness = (math.sin(time.ticks_ms() * math.pi * 2 / (1000 / network_led_pulse_speed_hz)) * 40) + 60
    value = int(pow(brightness / 100.0, 2.8) * 65535.0 + 0.5)
    network_led_pwm.duty_u16(value)


# set the network led into pulsing mode
def pulse_network_led(speed_hz=1):
    global network_led_timer, network_led_pulse_speed_hz
    network_led_pulse_speed_hz = speed_hz
    network_led_timer.deinit()
    network_led_timer.init(period=50, mode=Timer.PERIODIC, callback=network_led_callback)


# turn off the network led and disable any pulsing animation that's running
def stop_network_led():
    global network_led_timer
    network_led_timer.deinit()
    network_led_pwm.duty_u16(0)


def sleep(t):
    # Time to have a little nap until the next update
    print('Sleeping for {} minutes'.format(t))
    rtc.clear_timer_flag()
    rtc.set_timer(t, ttp=rtc.TIMER_TICK_1_OVER_60HZ)
    rtc.enable_timer_interrupt(True)

    # Set the HOLD VSYS pin to an input
    # this allows the device to go into sleep mode when on battery power.
    hold_vsys_en_pin.init(Pin.IN)

    # Regular time.sleep for those powering from USB
    # time.sleep(60 * t)


# Turns off the button LEDs
def clear_button_leds():
    inky_frame.button_a.led_off()
    inky_frame.button_b.led_off()
    inky_frame.button_c.led_off()
    inky_frame.button_d.led_off()
    inky_frame.button_e.led_off()


def is_internet_connected(host="8.8.8.8", port=53, timeout=3, max_attempts=3):
    """Test internet connectivity by attempting to connect to Google's DNS.

    Args:
        host (str): IP to test against (default: Google DNS)
        port (int): Port to connect to (default: 53/DNS)
        timeout (int): Connection timeout in seconds, default 3
        max_attempts (int): Number of attempts to connect, default 3

    Returns:
        bool: True if connected, False otherwise
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        try:
            print('[{}/{}] Attempting to connect to {}:{}'.format(attempt, max_attempts, host, port))
            sock.connect((host, port))
            print('Connected!')
            sock.close()
            gc.collect()
            return True
        except OSError:
            pass

    print('Unable to connect to {}:{}'.format(host, port))
    sock.close()
    gc.collect()
    return False


def network_connect(ssid, psk, max_attempts=100):
    """Connect to the wifi network with an exponential backoff starting at 1 second and increasing up to 10 seconds.

    Args:
        ssid (str): The SSID of the network
        psk (str): The password for the network
        max_attempts (int): The number of attempts to connect, default 100

    Returns:
        bool: True if successful, False otherwise
    """
    print('Connecting to network "{}" with password "{}"'.format(ssid, psk))
    # Check if already connected
    wlan = network.WLAN(network.STA_IF)
    if wlan.status() == 3:
        print("✓ Already Connected! IP:", wlan.ifconfig()[0])
        return True

    # Enable wlan
    wlan.active(True)
    # wlan.config(pm=0xa11140)  # Turn WiFi power saving off for some slow APs

    # Sets the Wireless LED pulsing and attempts to connect to your local network.
    try:
        pulse_network_led()
        led_warn.on()
        wlan.connect(ssid, psk)

        for i in range(max_attempts):
            i += 1
            status = wlan.status()
            if status == 3:  # Connected successfully
                print(f"[{i}/{max_attempts}] ✓ Connected! IP: {wlan.ifconfig()[0]}")
                break
            # I've tested different sleep times and 10 seems to be the sweet spot for all errors
            elif status < 0:
                sleep_time = 10
            else:
                sleep_time = 10

            print(f'[{i}/{max_attempts}] ✗ Connection failed with status: {status} "{WIFI_STATUS_CODES.get(status, 'Unknown')}", waiting {sleep_time} seconds')

            if status <= 0:
                wlan.connect(ssid, psk)

            time.sleep(sleep_time)
    finally:
        stop_network_led()
        led_warn.off()

    if wlan.status() == 3:
        return True
    else:
        led_warn.on()
        return False


def file_exists(filename):
    """Check if a file exists.

    Args:
        filename (str): The name of the file to check

    Returns:
        bool: True if the file exists, False otherwise
    """
    try:
        return (os.stat(filename)[0] & 0x4000) == 0
    except OSError:
        return False
