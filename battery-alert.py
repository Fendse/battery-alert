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
    UNKNOWN = 0
    LINE_POWER = 1
    BATTERY = 2
    UPS = 3
    MONITOR = 4
    MOUSE = 5
    KEYBOARD = 6
    PDA = 7
    PHONE = 8

    def __init__(self, value : int):
        names = {
            0: "Unknown",
            1: "Line power",
            2: "Battery",
            3: "UPS",
            4: "Monitor",
            5: "Mouse",
            6: "Keyboard",
            7: "PDA",
            8: "Phone",
        }
        self._nicename = names[value]
        self._value_ = value

    def __str__(self):
        return self._nicename

class BatteryLevel(Enum):
    """
    A battery level as reported by org.freedesktop.UPower.Device.BatteryLevel
    """
    UNKNOWN = 0
    NONE = 1
    LOW = 3
    CRITICAL = 4
    NORMAL = 6
    HIGH = 7
    FULL = 8

    def __init__(self, value : int):
        names = {
            0: "Unknown",
            1: "None",
            3: "Low",
            4: "Critical",
            6: "Normal",
            7: "High",
            8: "Full",
        }
        self._nicename = names[value]
        self._value_ = value

    def __str__(self):
        return self._nicename

class BatteryState(Enum):
    """
    A device state as reported by org.freedesktop.UPower.Device.State
    """
    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    EMPTY = 3
    FULLY_CHARGED = 4
    PENDING_CHARGE = 5
    PENDING_DISCHARGE = 6

    def __init__(self, value : int):
        names = {
            0: "Unknown",
            1: "Charging",
            2: "Discharging",
            3: "Empty",
            4: "Fully charged",
            5: "Pending charge",
            6: "Pending discharge",
        }
        self._nicename = names[value]
        self._value_ = value

    def __str__(self):
        return self._nicename


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

        if battery_level == BatteryLevel.NONE:
            level_string = ""
        else:
            level_string = f" {battery_level.name}"
        

        summary = f"{device_type.name}{level_string}"

        body = f"{device_type.name}{level_string}: {percentage}%\n{status.name}"

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