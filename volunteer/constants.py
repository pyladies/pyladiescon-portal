from enum import Enum


class RoleTypes(Enum):
    """Role types for the volunteer."""

    ADMIN = "Admin"
    STAFF = "Staff"
    VENDOR = "Vendor"
    VOLUNTEER = "Volunteer"


class ApplicationStatus(Enum):
    """Application status for the volunteer."""

    PENDING = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"
