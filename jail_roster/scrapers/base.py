from dataclasses import dataclass, asdict

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; MTJailRoster/1.0; +https://github.com/hunterad93/jail_roster)"
DEFAULT_TIMEOUT = 45
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


def http_client(**kwargs) -> httpx.Client:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    kwargs.setdefault("follow_redirects", True)
    headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
    return httpx.Client(headers=headers, **kwargs)


def http_get(url: str, **kwargs) -> httpx.Response:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    kwargs.setdefault("follow_redirects", True)
    headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
    return httpx.get(url, headers=headers, **kwargs)


@dataclass
class Inmate:
    jail: str
    last_name: str
    first_name: str
    middle_name: str = ""
    booking_date: str = ""
    charges: str = ""
    bond: str = ""
    status: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
