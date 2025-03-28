import datetime
import math
import re


NUMBER_UNITS = (
    ('', 1),
    ('K', 1e3),
    ('M', 1e3),
    ('G', 1e3),
    ('T', 1e3),
    ('P', 1e3),
    ('E', 1e3),
    ('Z', 1e3),
    ('Y', 1e3),
)

TIME_UNITS = (
    ('ns', 1),
    ('μs', 1e3),
    ('ms', 1e3),
    ('s', 1e3),
    ('min', 60),
    ('h', 60),
)
# 1024
BYTES_UNITS = (
    ('iB', 1),
    ('KiB', 1024),
    ('MiB', 1024),
    ('GiB', 1024),
    ('TiB', 1024),
    ('PiB', 1024),
    ('EiB', 1024),
    ('ZiB', 1024),
    ('YiB', 1024)
)

def format_bytes(n: float, round: int = 2) -> str:
    i = 0
    for u, un in BYTES_UNITS[1:]:
        if n / un < 1:
            break
        n /= un
        i += 1
    return f'{n:.{round}f}{BYTES_UNITS[i][0]}'

def format_number(n: float, round: int = 2) -> str:
    i = 0
    for u, un in NUMBER_UNITS[1:]:
        if n / un < 1:
            break
        n /= un
        i += 1
    return f'{n:.{round}f}{NUMBER_UNITS[i][0]}'

def format_count_time(n: float, round: int = 2) -> str:
    i = 0
    for u, un in TIME_UNITS[1:]:
        if n / un < 1:
            break
        n /= un
        i += 1
    return f'{n:.{round}f}{TIME_UNITS[i][0]}'

def format_datetime_from_timestamp(n: float) -> str:
    return datetime.datetime.fromtimestamp(n).strftime('%Y-%m-%d %H:%M:%S')

TIME_UNITS_DICT = {
    'ns': 1e-9,
    'μs': 1e-6,
    'ms': 1e-3,
    's': 1,
    'min': 60,
    'm': 60,
    'h': 3600,
    'd': 86400,
    'w': 7 * 86400,
    'mo': 30 * 86400,
}
NUMBER_UNITS_DICT = {
    '': 1,
    'K': 1e3,
    'M': 1e6,
    'G': 1e9,
    'T': 1e12,
    'P': 1e15,
    'E': 1e18,
    'Z': 1e21,
    'Y': 1e24,
}

def parse_time_units(n: str) -> float:
    """
        to seconds
    """
    if n is None or n == '':
        return 0
    if n.lower() == "inf":
        return math.inf
    matches = re.findall(r'([\d.]+)([a-zA-Zμ]+)', n)
    
    total_seconds = 0
    for match in matches:
        value_str, unit = match
        value = float(value_str)
        if unit in TIME_UNITS_DICT:
            total_seconds += value * TIME_UNITS_DICT[unit]
        else:
            raise ValueError(f"Invalid unit '{unit}' in time string")
    
    return total_seconds

def parse_number_units(n: str) -> float:
    if n is None or n == '':
        return 0.0
    if n.lower() == "inf":
        return math.inf
    matches = re.findall(r'([\d.]+)\s*([a-zA-Z]*)', n)

    total = 0.0
    for match in matches:
        value_str, unit = match
        unit = unit.upper()
        value = float(value_str)
        if unit in NUMBER_UNITS_DICT:
            total += value * NUMBER_UNITS_DICT[unit]
        else:
            raise ValueError(f"Invalid unit '{unit}' in time string")

    return total