"""
Get communication availability statistics from LibreNMS using a listing of 
devices from NetBox.
"""

###############################################################################

# Imports

###############################################################################

import asyncio
import os

import aiohttp
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


async def get_list_of_devices():
    NETBOX_API_KEY = os.getenv("NETBOX_API_KEY")
    NETBOX_URL = os.getenv("NETBOX_URL")
    nb = pynetbox.api(NETBOX_URL, token=NETBOX_API_KEY)
    nb.http_session.verify = False
    device_list = list(nb.dcim.devices.filter(status="active", tag=["librenms"]))
    return device_list


async def get_availability(session, device):
    LIBRENMS_URL = os.getenv("LIBRENMS_URL")
    LIBRENMS_API_KEY = os.getenv("LIBRENMS_API_KEY")
    headers = {"X-Auth-Token": LIBRENMS_API_KEY}
    device_ip = device.primary_ip4["address"].split("/")[0]

    async with session.get(
        LIBRENMS_URL + device_ip + "/availability", headers=headers
    ) as response:
        data = await response.json()

    if not data["availability"]:
        Progress().console.print(f"[red]{device.name} issue in LibreNMS")
        return None

    list_of_avails = data["availability"]
    availability = {"Name": device.name}
    availability.update(
        {avail["duration"]: avail["availability_perc"] for avail in list_of_avails}
    )

    return availability


async def multi_async(description: str, task_item: callable, device_list: list) -> None:
    async with aiohttp.ClientSession() as session:
        with Progress() as progress:
            task_id = progress.add_task(description, total=len(device_list))
            tasks = [task_item(session, device) for device in device_list]
            results = await asyncio.gather(*tasks)

            for result in results:
                if result is not None:
                    progress.advance(task_id)
    return results


def average_availability(results: list) -> list:
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


async def main():
    device_list = await get_list_of_devices()
    results = await multi_async(
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


if __name__ == "__main__":
    asyncio.run(main())
