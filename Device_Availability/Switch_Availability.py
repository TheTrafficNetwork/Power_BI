"""
Get communication availability statistics from LibreNMS using a listing of 
devices from NetBox.
"""

###############################################################################

# Imports

###############################################################################
import os
from multiprocessing import Pool
from typing import Callable

import pynetbox
import requests
from dotenv import find_dotenv, load_dotenv
from rich.progress import Progress
from urllib3.exceptions import InsecureRequestWarning

###############################################################################

# Base Setup

###############################################################################

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
load_dotenv(find_dotenv())

###############################################################################

# Get list of devices from NetBox

###############################################################################


def get_list_of_devices():
    """Gets a filtered list of devices from NetBox that are setup in LibrenNMS

    Returns:
        List: List of devices as pynetbox objects
    """
    NETBOX_API_KEY = os.getenv("NETBOX_API_KEY")
    NETBOX_URL = os.getenv("NETBOX_URL")
    nb = pynetbox.api(NETBOX_URL, token=NETBOX_API_KEY)
    nb.http_session.verify = False
    device_list = list(nb.dcim.devices.filter(status="active", tag=["librenms"]))
    return device_list


###############################################################################

# Get availability for a device from LibreNMS

###############################################################################


def get_availability(device):
    """Gets the availability % for the past year for a device

    Args:
        device (object): pynetbox object of a network device

    Returns:
        float: Percent of availability for the device requested across a year
    """
    LIBRENMS_URL = os.getenv("LIBRENMS_URL")
    LIBRENMS_API_KEY = os.getenv("LIBRENMS_API_KEY")
    headers = {"X-Auth-Token": LIBRENMS_API_KEY}
    device_ip = device.primary_ip4["address"].split("/")[0]
    response = requests.get(
        (LIBRENMS_URL + device_ip + "/availability"), headers=headers
    ).json()
    """
    Sample Response
    {'availability': [
        {'availability_perc': '100.000000', 'duration': 86400},
        {'availability_perc': '100.000000', 'duration': 604800},
        {'availability_perc': '100.000000', 'duration': 2592000},
        {'availability_perc': '99.999000', 'duration': 31536000}
        ],
    'status': 'ok'}
    """
    if len(response["availability"]) == 0:
        Progress().console.print(f"[red]{device.name} issue in LibreNMS")
        return None
    list_of_avails = response["availability"]
    availability = {"Name": device.name}
    availability.update(
        {avail["duration"]: avail["availability_perc"] for avail in list_of_avails}
    )
    """
    Sample availability
    {
        'Name':'Device_Name',
        86400: '100.000000', 
        604800: '100.000000', 
        2592000: '100.000000', 
        31536000: '99.999000'
    }
    """
    return availability


###############################################################################

# Multiprocess the LibreNMS requests

###############################################################################


def multi_proc(description: str, task_item: Callable, device_list: list) -> None:
    """Multiple processing of a function covering each item in the list

    Args:
        description (str): Description of the process running
        task_item (Callable): Function that will be ran
        device_list (list): List of inputs for the function to work through
    """
    max_processes = 1
    with Progress() as progress:
        task_id = progress.add_task(description, total=len(device_list))
        with Pool(processes=max_processes) as pool:
            for result in pool.imap(task_item, device_list):
                results.append(result)
                progress.advance(task_id)


###############################################################################

# Aggregate the data into a single metric

###############################################################################


def average_availability(results: list) -> list:
    """Averages individual device results into a single network wide metric

    Args:
        results (list): List of device's availability

    Returns:
        list: List of averages for different time perirods ranging from 1 day
        to 1 year.
    """
    day = [float(result[86400]) for result in results if result is not None]
    week = [float(result[604800]) for result in results if result is not None]
    month = [float(result[2592000]) for result in results if result is not None]
    year = [float(result[31536000]) for result in results if result is not None]
    average_day = sum(day) / len(day)
    average_week = sum(week) / len(week)
    average_month = sum(month) / len(month)
    average_year = sum(year) / len(year)

    return {
        "day": average_day,
        "week": average_week,
        "month": average_month,
        "year": average_year,
    }


###############################################################################

# Main Function

###############################################################################

if __name__ == "__main__":
    device_list = get_list_of_devices()
    results = []
    multi_proc(
        "[cyan]Requesting Device Availability...",
        get_availability,
        device_list,
    )
    avail = average_availability(results)
    print("****************************************")
    print("Network Device Availability.")
    print("****************************************")
    print(f"{round(avail['day'], 3):.3f}% availability yesterday")
    print(f"{round(avail['week'], 3):.3f}% availability for the past week.")
    print(f"{round(avail['month'], 3):.3f}% availability for the past month.")
    print(f"{round(avail['year'], 3):.3f}% availability for the past year.")
    print("****************************************")
