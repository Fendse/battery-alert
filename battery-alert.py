#!/usr/bin/env python3

import argparse
import datetime
from enum import Enum
from gi.repository.GLib import MainLoop, Variant
import pydbus
import sys
import time
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

class BatteryLevel(Enum):
    """
    A battery level as reported by org.freedesktop.UPower.Device.BatteryLevel
    """
    Unknown = 0
    No_level = 1
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

class BatteryThresholds:
    """
    A set of threshold values to determine the battery level matching a percentage.
    """
    attr_names = ["high", "normal", "low", "critical"]

    def __init__(self, **kwargs):
        log("Creating threshold object")

        attr_defaults = [95, 70, 30, 15]

        for i in range(len(BatteryThresholds.attr_names)):
            attr_name = BatteryThresholds.attr_names[i]

            if attr_name in kwargs:
                attr_value = kwargs[attr_name]
            else:
                attr_value = attr_defaults[i]

            if attr_value > 100:
                raise ValueError(f"Thresholds must be below 100, but {attr_name} was {attr_value}")

            if attr_value < 0:
                raise ValueError(f"Thresholds must not be negative, but {attr_name} was {attr_value}")

            try:
                prev_attr_name = BatteryThresholds.attr_names[i - 1]
                prev_attr_value = getattr(self, prev_attr_name)

                if attr_value > prev_attr_value:
                    raise ValueError(f"Thresholds must be in descending order, but {attr_name} ({attr_value}) was greater than {prev_attr_name} ({prev_attr_value})")
            except (IndexError, AttributeError):
                pass

            log(f"{attr_name} set to {attr_value}")
            setattr(self, attr_name, attr_value)


    def get_level(self, level):
        if level < self.critical:
            return BatteryLevel.Critical
        elif level < self.low:
            return BatteryLevel.Low
        elif level < self.normal:
            return BatteryLevel.Normal
        elif level < self.high:
            return BatteryLevel.High
        else:
            return BatteryLevel.Full


def get_battery_level(device, custom_levels : BatteryThresholds, prefer_custom : bool = False) -> BatteryLevel:
    """
    Get a BatteryLevel representing the state of the given device, taking the provided
    custom thresholds into account.

    The level reported by the device is preferred unless it's BatteryLevel.NOT_APPLICABLE,
    or unless prefer_custom is True
    """

    percentage = device.Percentage
    reported_level = BatteryLevel(device.BatteryLevel)
    custom_level = custom_levels.get_level(percentage)

    if prefer_custom:
        log("Ignoring reported level as prefer_custom is set")
        return custom_level
    elif reported_level == BatteryLevel.NOT_APPLICABLE:
        log("Device does not report level, ignoring")
        return custom_level
    else:
        log("Using level as reported by UPower")
        return reported_level


def monitor_battery(device, refresh_rate : int, notify : Callable, custom_levels : Optional[BatteryThresholds] = None):
    """
    Continuously monitor the battery level of the given device,
    sending notifications via DBus as the level changes
    """
    prefer_custom = custom_levels is not None

    if prefer_custom:
        log("Using custom thresholds.")
    else:
        log("No custom thresholds provided, using defaults.")

    if custom_levels is None:
        custom_levels = BatteryThresholds()

    prev_battery_level = BatteryLevel.UNKNOWN

    while True:
        try:
            time.sleep(refresh_rate)

            log("Refreshing power device data")
            display_device.Refresh()

            # Respect device.IsPresent
            if not device.IsPresent:
                log("Device is not present, ignoring")
                continue

            # If it isn't a battery, ignore it
            if DeviceType(device.Type) != DeviceType.BATTERY:
                log(f"Device is not a battery but a(n) {DeviceType(device.Type).name}, ignoring")
                continue

            battery_level = get_battery_level(device, custom_levels, prefer_custom=prefer_custom)
            percentage = device.Percentage

            log(f"Battery at {percentage}% ({battery_level.name})")

            if battery_level != prev_battery_level:
                log("Battery level changed, notifying")

                obj_path = "/com/github/fendse/battery_alert"

                notify("Battery Alert", None, device.IconName,
                    f"Battery {percentage}% ({battery_level})",
                    "", [], {}, None,
                    notify_system = not notify_session_only)

            prev_battery_level = battery_level
        except KeyboardInterrupt:
            log("Interrupted")
            return


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
    


def threshold_dict(comma_separated_ints : str) -> Dict[str, int]:
    """
    Helper function to turn a string of digits separated by commas into
    a dict usable for constructing a BatteryThresholds object
    """
    result = {}

    values = s.split(",")
    for i in range(len(BatteryThresholds.attr_names)):
        result[BatteryThresholds.attr_names[i]] = int(values[i])

    return result


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()

    arg_parser.add_argument("--session", action="store_true", help="Send notifications to the running user's session bus only.")
    arg_parser.add_argument("--refresh-rate", type=int, default=60, help="Time between refreshes, in seconds.")
    arg_parser.add_argument("--thresholds", type=threshold_dict)
    arg_parser.add_argument("--debug", action="store_true", help="Reserved for development. May do literally anything.")

    arguments = arg_parser.parse_args()

    system_bus = pydbus.SystemBus()
    display_device_path = system_bus.get(".UPower").GetDisplayDevice()
    display_device = system_bus.get(".UPower", display_device_path)


    def notify(app_name : str, replaces_id : Optional[int], app_icon : str,
            summary : str, body : str, actions : List[Tuple[str, str]],
            hints : Dict[str, object],
            expire_timeout : Union[int, None, Literal["never"]]):
        if replaces_id is None:
            replaces_id = 0
        
        actions = [x for (name, identifier) in actions
            for x in (name, identifier)]

        if expire_timeout is None:
            expire_timeout = -1
        elif expire_timeout == "never":
            expire_timeout = 0
        
        notifier.Notify(app_name, replaces_id, app_icon,
            summary, body, actions, hints, expire_timeout)
    
    display_device.PropertiesChanged.connect(notice_display_device_change)
    loop = MainLoop()
    loop.run()


    try:
        if arguments.debug:
            notify("appname", None, "", "summary", "body", [], {}, None)
            loop.run()
        else:
            monitor_battery(display_device, arguments.refresh_rate, notify)
    finally:
        loop.quit()