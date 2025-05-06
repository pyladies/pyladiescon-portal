import logging

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = settings.GOOGLE_SERVICE_ACCOUNT_FILE
FOLDER_ID = settings.GOOGLE_DRIVE_FOLDER_ID


def validate_folder_id():
    service = get_gdrive_service()
    try:
        service.files().get(fileId=FOLDER_ID, fields="id,name").execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            logger.error(
                f"Folder ID {FOLDER_ID} not found. Please check the folder ID in settings."
            )
        else:
            logger.error(f"Error validating folder ID: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating folder ID: {str(e)}")
        return False


def get_gdrive_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def add_to_gdrive(email):
    service = get_gdrive_service()
    try:
        if not validate_folder_id():
            logger.error(f"Cannot add {email} to GDrive: Invalid folder ID")
            return

        permissions = (
            service.permissions()
            .list(fileId=FOLDER_ID, fields="permissions(id, emailAddress)")
            .execute()
            .get("permissions", [])
        )

        existing = [p for p in permissions if p.get("emailAddress") == email]

        if existing:
            logger.info(f"Email {email} already has access.")
            return

        permission = {"type": "user", "role": "writer", "emailAddress": email}

        result = (
            service.permissions()
            .create(
                fileId=FOLDER_ID,
                body=permission,
                fields="id",
                sendNotificationEmail=False,
            )
            .execute()
        )

        logger.info(f"Added {email} to GDrive with permission ID: {result.get('id')}")

    except HttpError as e:
        if e.resp.status == 404:
            logger.error(
                f"Google API error adding {email}: Folder not found. Check GOOGLE_DRIVE_FOLDER_ID in settings."
            )
        else:
            logger.error(f"Google API error adding {email}: {str(e)}")
    except Exception as e:
        logger.error(f"Error adding {email} to GDrive: {str(e)}")


def remove_from_gdrive(email):
    service = get_gdrive_service()
    try:
        if not validate_folder_id():
            logger.error(f"Cannot remove {email} from GDrive: Invalid folder ID")
            return

        permissions = (
            service.permissions()
            .list(fileId=FOLDER_ID, fields="permissions(id, emailAddress)")
            .execute()
            .get("permissions", [])
        )

        target_permissions = [p for p in permissions if p.get("emailAddress") == email]

        if not target_permissions:
            logger.info(f"No permissions found for {email} to remove")
            return

        for p in target_permissions:
            service.permissions().delete(
                fileId=FOLDER_ID, permissionId=p["id"]
            ).execute()
            logger.info(f"Removed {email} from GDrive (permission ID: {p['id']})")

    except HttpError as e:
        if e.resp.status == 404:
            logger.error(
                f"Google API error removing {email}: Folder not found. Check GOOGLE_DRIVE_FOLDER_ID in settings."
            )
        else:
            logger.error(f"Google API error removing {email}: {str(e)}")
    except Exception as e:
        logger.error(f"Error removing {email} from GDrive: {str(e)}")
