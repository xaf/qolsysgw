import logging
import re
import subprocess


LOGGER = logging.getLogger(__name__)


class LoggerCallback(object):
    def __init__(self, msg=None):
        self.msg = msg or 'Logger callback'

    async def __call__(self, *args, **kwargs):
        LOGGER.debug(f"{self.msg}{': ' if args or kwargs else ''}"
                     f"{f'args={args} ' if args else ''}"
                     f"{f'kwargs={kwargs}' if kwargs else ''}")


async def defaultLoggerCallback(*args, **kwargs):
    callback = LoggerCallback()
    callback(*args, **kwargs)


def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])


def find_subclass(cls, subtype: str, cache: dict = None, normalize=True,
                  preserve_capitals=False):
    if cache and subtype in cache:
        return cache[subtype]

    normalized_subtype = subtype
    if normalize:
        normalized_subtype = re.compile(r'[\W_]+').sub(' ', normalized_subtype)
        if preserve_capitals:
            normalized_subtype = re.compile(r'(?<=[^\s])([A-Z])').sub(
                ' \\1', normalized_subtype)
        normalized_subtype = normalized_subtype.title()
        normalized_subtype = re.compile(r'\s').sub('', normalized_subtype)

    search = f"{cls.__name__}{normalized_subtype}"

    for klass in all_subclasses(cls):
        if klass.__name__ == search:
            if cache is not None:
                cache[subtype] = klass
            return klass

    if cache is not None:
        cache[subtype] = None
    return None


def get_mac_from_host(ip_or_host):
    try:
        # The arp command will automatically resolve the hostname to an
        # IP address for us if needed
        process = subprocess.run(['arp', ip_or_host], capture_output=True)
    except (subprocess.SubprocessError, OSError):
        LOGGER.exception(f"Error trying to get the mac address for '{ip_or_host}'")
        return None

    output = process.stdout.decode('utf-8')

    m = re.search(r'(([a-f\d]{1,2}:){5}[a-f\d]{1,2})', output)

    if m is None:
        LOGGER.warning(f"No mac address found for '{ip_or_host}'")
        return None

    mac = m[0]
    LOGGER.debug(f"Found mac address '{mac}' for '{ip_or_host}'")
    return mac
