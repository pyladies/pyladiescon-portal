from enum import StrEnum


# class RoleTypes(StrEnum):
#     """Role types for the volunteer."""

#     ADMIN = "Admin"
#     STAFF = "Staff"
#     VENDOR = "Vendor"
#     VOLUNTEER = "Volunteer"


class ApplicationStatus(StrEnum):
    """Application status for the volunteer."""

    PENDING = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


class Region(StrEnum):
    """Region where the volunteer usually reside."""

    NO_REGION = ""
    ASIA = "Asia"
    EUROPE = "Europe"
    NORTH_AMERICA = "North America"
    SOUTH_AMERICA = "South America"
    AFRICA = "Africa"
    OCEANIA = "Oceania"
