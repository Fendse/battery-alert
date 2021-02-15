#!/usr/bin/env python3

import argparse
import datetime
from enum import Enum
from gi.repository.GLib import MainLoop, Variant
import pydbus
import sys
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

def log(*args, **kwargs):
    """
    Write a time-stamped message to an output file, defaulting to sys.stderr
    For arguments, see help(print)
    """
    prefix = f"[{str(datetime.datetime.now())}]"

    if "file" in kwargs:
        print(prefix, *args, **kwargs)
    else:
        print(prefix, *args, **kwargs, file=sys.stderr)


class DeviceType(Enum):
    """
    A power device type as reported by org.freedesktop.UPower.Device.Type
    """
    Unknown = 0
    Line_power = 1
    Battery = 2
    UPS = 3
    Monitor = 4
    Mouse = 5
    Keyboard = 6
    PDA = 7
    Phone = 8

class BatteryLevel(Enum):
    """
    A battery level as reported by org.freedesktop.UPower.Device.BatteryLevel
    """
    Unknown = 0
    No_level = 1 # Can't call it "None"
    Low = 3
    Critical = 4
    Normal = 6
    High = 7
    Full = 8

class BatteryState(Enum):
    Unknown = 0
    Charging = 1
    Discharging = 2
    Empty = 3
    Fully_charged = 4
    Pending_charge = 5
    Pending_discharge = 6


def notice_display_device_change(interface : str, changed : Dict[str, Any], invalidated : List[str]):
    log(changed)
    def did_change(property_name : str) -> bool:
        return property_name in changed or property_name in invalidated
    
    should_notify = any((did_change(p) for p in ("IconName", "BatteryLevel", "State", "Online")))

    if should_notify:
        log("Notifying")
        device = pydbus.SystemBus().get(".UPower", "/org/freedesktop/UPower/devices/DisplayDevice")

        device_type = DeviceType(device.Type)

        status = BatteryState(device.State)


        try:
            percentage = changed["Percentage"]
        except KeyError:
            percentage = device.Percentage
        
        battery_level = BatteryLevel(device.BatteryLevel)

        if battery_level == BatteryLevel.No_level:
            level_string = ""
        else:
            level_string = f" {battery_level.name}"
        

        summary = f"Battery{level_string}"

        body = f"Battery{level_string}: {percentage}%\n{status.name}"

        time_to_full = changed["TimeToFull"]
        time_to_empty = changed["TimeToEmpty"]

        if time_to_full:
            body += f", full in {str(datetime.timedelta(seconds=time_to_full))}"
        if device.TimeToEmpty:
            body += f", empty in {str(datetime.timedelta(seconds=time_to_empty))}"

        pydbus.SessionBus().get(".Notifications").Notify(
            "Battery Alert", 0, device.IconName,
            summary,
            body, [], {}, -1
        )
    else:
        log("No important changes, not notifying")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()

    arguments = arg_parser.parse_args()

    system_bus = pydbus.SystemBus()
    display_device_path = system_bus.get(".UPower").GetDisplayDevice()
    display_device = system_bus.get(".UPower", display_device_path)

    display_device.PropertiesChanged.connect(notice_display_device_change)
    loop = MainLoop()
    loop.run()