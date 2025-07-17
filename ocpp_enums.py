# ocpp_enums.py
"""OCPP 1.6 Enumerations and Constants"""

from enum import Enum


class MessageType(Enum):
    CALL = 2
    CALL_RESULT = 3
    CALL_ERROR = 4


class OCPPAction(Enum):
    BOOT_NOTIFICATION = "BootNotification"
    HEARTBEAT = "Heartbeat"
    STATUS_NOTIFICATION = "StatusNotification"
    START_TRANSACTION = "StartTransaction"
    STOP_TRANSACTION = "StopTransaction"
    METER_VALUES = "MeterValues"
    AUTHORIZE = "Authorize"
    SET_CHARGING_PROFILE = "SetChargingProfile"
    CLEAR_CHARGING_PROFILE = "ClearChargingProfile"
    GET_COMPOSITE_SCHEDULE = "GetCompositeSchedule"


class ChargerStatus(Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EV = "SuspendedEV"
    SUSPENDED_EVSE = "SuspendedEVSE"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class AuthorizationStatus(Enum):
    ACCEPTED = "Accepted"
    BLOCKED = "Blocked"
    EXPIRED = "Expired"
    INVALID = "Invalid"
    CONCURRENT_TX = "ConcurrentTx"


class ResetType(Enum):
    HARD = "Hard"
    SOFT = "Soft"


class ResetStatus(Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class ConfigurationStatus(Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    REBOOT_REQUIRED = "RebootRequired"
    NOT_SUPPORTED = "NotSupported"


class ChargingProfileStatus(Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    NOT_SUPPORTED = "NotSupported"


class ClearChargingProfileStatus(Enum):
    ACCEPTED = "Accepted"
    UNKNOWN = "Unknown"
