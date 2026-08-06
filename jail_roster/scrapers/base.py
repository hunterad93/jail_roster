from dataclasses import dataclass, asdict


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
