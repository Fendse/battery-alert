#!/usr/bin/env python3

import argparse
import datetime
from enum import Enum
from gi.repository.GLib import MainLoop, Variant
import pydbus
import sys
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple, Union

def log(*args, **kwargs) -> None:
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


def send_notification(device_type : str, status : BatteryState,
        percentage : int, battery_level : BatteryLevel,
        time_to_full : int, time_to_empty : int,
        icon : str) -> None:
    """
    Sends a desktop notification based on the given information
    """
    if battery_level == BatteryLevel.NONE:
        level_string = ""
    else:
        level_string = f" {str(battery_level)}"

    summary = f"{str(device_type)}{level_string}"
    body = f"{str(device_type)}{level_string}: {percentage}%\n{str(status)}"

    if time_to_full:
        body += f", full in {str(datetime.timedelta(seconds=time_to_full))}"
    if device.TimeToEmpty:
        body += f", empty in {str(datetime.timedelta(seconds=time_to_empty))}"

    pydbus.SessionBus().get(".Notifications").Notify(
        "Battery Alert", 0, icon,
        summary,
        body, [], {}, -1
    )


def device_monitor(device : pydbus.proxy.ProxyObject, important_properties : Set[str]) -> None:
    """
    Return a callback that upon a PropertiesChanged event for the given device,
    sends a desktop notification if the change is considered significant.
    An event represents a significant change if any of the properties in
    important_properties has been changed or invalidated
    """

    def notice_device_change(interface : str, changed : Dict[str, Any], invalidated : List[str]):
        log(changed)
        def did_change(property_name : str) -> bool:
            return property_name in changed or property_name in invalidated

        def value_of(property_name : str) -> Any:
            try:
                return changed[property_name]
            except KeyError:
                return getattr(device, property_name)

        should_notify = any((did_change(p) for p in important_properties))

        if should_notify:
            log("Notifying")

            device_type = DeviceType(value_of("Type"))
            status = BatteryState(value_of("State"))
            percentage = value_of("Percentage")
            battery_level = BatteryLevel(value_of("BatteryLevel"))
            time_to_full = value_of("TimeToFull")
            time_to_empty = value_of("TimeToEmpty")
            icon = value_of("IconName")

            send_notification(device_type, status, percentage,
                battery_level, time_to_full,
                time_to_empty, icon)

        else:
            log("No important changes, not notifying")

    return notice_device_change


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()

    presumed_important = set(("IconName", "BatteryLevel", "State", "Online"))
    alert_on_help_text = f"""
        The name of a UPower device property which
        causes a desktop notification to be sent when any of them changes.
        Can be specified multiple times.
        The properties {presumed_important} do not need to be explicitly specified"
    """
    arg_parser.add_argument("--alert-on",
        action="append", dest="important_properties",
        default=[],
        metavar="PROPERY_NAME", help=alert_on_help_text)

    no_alert_help_text = f"""
        The name of a UPower device property which does NOT
        cause a desktop notification to be sent if it changes.
        This takes priority over --alert-on, and can be used to
        suppress notifications from the properties {presumed_important}
    """
    arg_parser.add_argument("--no-alert-on",
        action="append", dest="unimportant_properties",
        default=[],
        metavar="PROPERTY_NAME", help=no_alert_help_text)

    device_metavar = "DEVICE"
    device_help_text = f"""
        The name of a UPower device to watch for property changes on.
        If ${device_metavar} begins with "/" it is assumed
        to be a complete DBus object path,
        otherwise /org/freedesktop/UPower/devices/${device_metavar} is used.
        If none is specified, "DisplayDevice" is assumed.
    """
    arg_parser.add_argument("--device",
        action="append", dest="devices",
        default=[],
        metavar=device_metavar, help=device_help_text)

    arguments = arg_parser.parse_args()

    log(arguments.devices)

    important_properties = presumed_important.union(set(arguments.important_properties))

    for prop in arguments.unimportant_properties:
        important_properties.discard(prop)

    system_bus = pydbus.SystemBus()

    subscriptions = {}
    for device_name in arguments.devices or ["DisplayDevice"]:
        if device_name.startswith("/"):
            object_path = device_name
        else:
            object_path = f"/org/freedesktop/UPower/devices/{device_name}"

        log(object_path)
        device = system_bus.get(".UPower", object_path)
        log(device)

        subscription = device.PropertiesChanged.connect(device_monitor(device, important_properties))

        subscriptions[object_path] = subscription

    loop = MainLoop()
    loop.run()