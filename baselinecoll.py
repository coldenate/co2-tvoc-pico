"""
This file is the main file that will collect air quality samples in the background, do nothing with them.
After 48 hours, the baseline will be written to the JSON, and the Light will be turned on.
"""
import gc
import sys

import dht
import network
import uasyncio as asyncio
import ujson as json
from machine import I2C, Pin, Timer
from utime import sleep


import secrets as secrets

import urequests
from sgp30 import Adafruit_SGP30

sys.path.append("/libs")
sys.path.append("..")


DEBUG_MODE = True
activity = True

gc.enable()


MAIN_LED = Pin("LED", Pin.OUT)
server_out = False  # pylint: disable=invalid-name
sensor = dht.DHT22(Pin(2, Pin.IN, Pin.PULL_UP))
sdaPIN = Pin(0)
sclPIN = Pin(1)
RETRY_LIMIT = 10
URL = "https://measure.up.railway.app/entry/entry"
i2c = I2C(0, sda=sdaPIN, scl=sclPIN, freq=400000)
devices = i2c.scan()

# start 48 hour timer using utime


def log(
    log_type: str, message: str, log_type_icon: str, status_icon: str | None = None
):
    """Log a message using the following scheme:
    __{log_type} {log_type_icon}: | {message} {status_icon}
    for example,
    __uploader 📤: | uploaded 3 samples ✅
    """
    if DEBUG_MODE is False or DEBUG_MODE is None:
        return
    if status_icon is None:
        print(f"__{log_type} {log_type_icon}: | {message}")
    elif status_icon is not None:
        print(f"__{log_type} {log_type_icon}: | {message} {status_icon}")


# log a basic message with a checkmark status icon and a pencil log type message stating that the timer is now running
log(log_type="timer", message="Timer started", log_type_icon="📝", status_icon="✅")


if len(devices) == 0:
    log(
        log_type="i2c",
        message="No i2c device found",
        status_icon="🚨",
        log_type_icon="💨",
    )
else:
    log(log_type="i2c", message=f"{len(devices)} i2c devices found", log_type_icon="📝")
for device in devices:
    log(
        log_type="i2c",
        message=f"Device found at address: {hex(device)}",
        log_type_icon="📝",
    )

# Initialize the SGP30
sgp_sensor = Adafruit_SGP30(i2c)

sensor.measure()
sgp_sensor.set_iaq_rel_humidity(sensor.humidity(), sensor.temperature())

sleep(3)


def read_from_baselines():
    """Read from the baselines.json file.
    Return each baseline.
    example json:
    {
        "co2eq_baseline": 0,
        "co2eq_baseline_unit": "ppm",
        "tvoc_baseline": 0,
        "tvoc_baseline_unit": "ppb"
    }
    """
    with open("baselines.json", "r", encoding="utf-8") as file:
        data = json.load(file)
        file.close()
    if data == {}:
        log(
            log_type="read_from_baselines",
            message="baselines.json is empty",
            log_type_icon="📝",
            status_icon="🚨",
        )
        return None
    sgp_sensor.set_iaq_baseline(data["co2eq_baseline"], data["tvoc_baseline"])
    return data["co2eq_baseline"], data["tvoc_baseline"]


def write_to_baselines():
    """Write to the baselines.json file."""
    co2eq_baseline = sgp_sensor.baseline_co2eq
    tvoc_baseline = sgp_sensor.baseline_tvoc

    data = {
        "co2eq_baseline": co2eq_baseline,
        "co2eq_baseline_unit": "ppm",
        "tvoc_baseline": tvoc_baseline,
        "tvoc_baseline_unit": "ppb",
    }
    with open("baselines.json", "w", encoding="utf-8") as file:
        json.dump(data, file)
        file.close()
        log(
            log_type="write_to_baselines",
            message="baselines.json written to successfully",
            log_type_icon="📝",
            status_icon="✅",
        )
    return file


read_from_baselines()

# I HATE i2C I HATE I2C I HATE I2C I HATE I2C I HATE I2C ITS SO USEFUL
# BUT AHHHAHDBJSKAHDFBNKSJHFBDJKSHFBDJKASHFBNASDJK,LFHBASDJKHB
# Wait 15 seconds for the SGP30 to properly initialize
# sleep(15)

MAIN_LED.value(0)


def generate_baseline(timer):
    global activity
    activity = False
    MAIN_LED.value(1)
    print("writing to baseline...")
    write_to_baselines()
    timer.deinit()


timer = Timer(-1)
timer.init(
    period=172800000,
    # period=10000,
    mode=Timer.PERIODIC,
    callback=lambda t: generate_baseline(timer),
)  # initializing the time


def write_to_queue(data):
    """Write to the upload_queue.json file."""
    if isinstance(data, list):
        log(log_type="write_to_queue", message="data is a list", log_type_icon="📝")
        # iterate through the list and add each item to a dict. overwrite the data with the dict
        # and proceed (usiong enumerate)) and an expanedd for loop
        data_new = {}
        for index, item in enumerate(data):
            # log(
            #     log_type="write_to_queue",
            #     message=f"item {index} is {item}",
            #     log_type_icon="📝",
            # )
            data_new[index] = item
        data = data_new
    with open("upload_queue.json", "w", encoding="utf-8") as file:
        json.dump(data, file)
        file.close()
        log(
            log_type="write_to_queue",
            message="upload_queue.json written to successfully",
            log_type_icon="📝",
            status_icon="✅",
        )
    return file


def read_from_queue():
    """Read from the upload_queue.json file."""
    with open("upload_queue.json", "r", encoding="utf-8") as file:
        data = json.load(file)
        file.close()
    # turn the dict into a list. this is because the json file is a dict,
    # but the upload_queue is a list.
    # it is safe to throw away the keys
    # because they are just the index of the item in the list.
    data_new = []
    for key in data:
        data_new.append(data[key])
    data = data_new
    return data


def sgp_read():
    """Read the SGP30 sensor and return the values."""
    co2eq, tvoc = sgp_sensor.iaq_measure()  # type: ignore
    return co2eq, tvoc


async def blink_led(times=2):
    """Blink the onboard LED a certain number of times.
    Will always result in the LED being off at the end.
    Defaults to 2 times."""
    for _i in range(times):
        MAIN_LED.value(1)
        asyncio.sleep(1)
        MAIN_LED.value(0)
        asyncio.sleep(1)
    MAIN_LED.value(0)


async def repeat(interval, func):
    """Run func every interval seconds.

    If func has not finished before *interval*, will run again
    immediately when the previous iteration finished.

    *args and **kwargs are passed as the arguments to func.
    """
    while True:
        await func()
        await asyncio.sleep(interval)


async def collect_sample():
    """Collect a sample from the air quality sensor and blink the led twice."""
    log(log_type="collect_sample", message="collecting a sample", log_type_icon="📝")

    if activity:
        MAIN_LED.value(0)
        MAIN_LED.value(1)
        MAIN_LED.value(0)

    # collect dht sampling (humidity and temp)
    sensor.measure()
    temperature = sensor.temperature()
    humidity = sensor.humidity()

    # collect sgp sampling (co2eq and tvoc)
    # sleep(5)
    co2eq, tvoc = sgp_read()

    upload_queue = read_from_queue()

    # print("CO2eq = %d ppm \t TVOC = %d ppb" % (co2eq, tvoc))

    sample = {
        "tvoc": tvoc,
        "co2": co2eq,
        "temperature": temperature,
        "humidity": humidity,
    }
    upload_queue.append(sample)
    log(log_type="collect_sample", message=f"{sample}", log_type_icon="📝")
    # write_to_queue(upload_queue)


# async def upload_sample():
#     """Upload a sample to the API and blink the led four times."""
#     global server_out  # pylint: disable=global-statement, invalid-name
#     upload_queue = read_from_queue()
#     await blink_led(4)
#     log(
#         log_type="uploader",
#         message=f"there are {len(upload_queue)} samples in the queue",
#         log_type_icon="📤",
#     )
#     if len(upload_queue) == 0:
#         log(
#             log_type="uploader",
#             message="no samples to upload",
#             log_type_icon="📤",
#             status_icon="🤷‍♂️",
#         )
#     elif len(upload_queue) > 0:
#         samples_uploaded = 0
#         log(log_type="uploader", message="beginning uploader", log_type_icon="📤")
#         log(
#             log_type="uploader",
#             message=f"beginning with {len(upload_queue)}:",
#             log_type_icon="📤",
#         )
#         log(log_type="uploader-report", message=f"{upload_queue}", log_type_icon="📤")
#         server_outage_count = 0
#         if not server_out:
#             for sample in upload_queue:
#                 upload_queue_copy = upload_queue.copy()
#                 log(
#                     log_type="uploader",
#                     message=f"uploading sample with room_num: {sample['room_num']}",
#                     log_type_icon="📤",
#                 )
#                 retry_count_u = 0
#                 while retry_count_u < 3:
#                     request = urequests.post(URL, json=sample, http_version="1.1")
#                     if request is not None:
#                         request.close()
#                     if request.status_code == 201:
#                         log(
#                             log_type="uploader",
#                             message="upload successful",
#                             log_type_icon="📤",
#                             status_icon="✅",
#                         )
#                         samples_uploaded += 1
#                         upload_queue_copy.remove(sample)
#                         log(
#                             log_type="uploader",
#                             message=f"removed {sample} from queue",
#                             log_type_icon="📤",
#                             status_icon="✅",
#                         )
#                         retry_count_u = 10
#                         server_out = False
#                     elif request.status_code == 400:
#                         log(
#                             log_type="uploader",
#                             message="upload failed",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         log(
#                             log_type="uploader",
#                             message="bad request",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         log(
#                             log_type="uploader-report",
#                             message=f"{request.text}",
#                             log_type_icon="📤",
#                         )
#                         retry_count_u += 1
#                     elif request.status_code == 500:
#                         log(
#                             log_type="uploader",
#                             message="upload failed",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         log(
#                             log_type="uploader",
#                             message="internal server error",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         log(
#                             log_type="uploader-report",
#                             message=f"{request.text}",
#                             log_type_icon="📤",
#                         )
#                         retry_count_u += 1
#                     else:
#                         log(
#                             log_type="uploader",
#                             message="upload failed (something berry berry bad happened)",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         log(
#                             log_type="uploader",
#                             message="unknown error",
#                             log_type_icon="📤",
#                             status_icon="❌",
#                         )
#                         retry_count_u += 1
#                         server_outage_count += 1
#                 if server_outage_count > 2:
#                     log(
#                         log_type="uploader",
#                         message="server outage",
#                         log_type_icon="📤",
#                         status_icon="❌⚠️",
#                     )
#                     server_out = True

#                 upload_queue = upload_queue_copy

#         log(
#             log_type="uploader",
#             message=f"uploaded {samples_uploaded} samples",
#             log_type_icon="📤",
#             status_icon="✅",
#         )
#         log(log_type="uploader", message="saving ... ", log_type_icon="📤")
#         write_to_queue(upload_queue)
#         log(log_type="uploader", message="saved", log_type_icon="📤", status_icon="✅")


async def main():
    """Main runner for the air quality sensor."""
    task_one = asyncio.create_task(repeat(3, collect_sample))
    # task_two = asyncio.create_task(repeat(5, upload_sample))
    await asyncio.gather(task_one)


# event_loop = asyncio.get_event_loop()
# event_loop.create_task(collect_sample())
# event_loop.create_task(upload_sample())
# event_loop.run_forever()

asyncio.run(main())
