from .client import PretalxClient

PRETALX_BASE_URL="https://pretalx.com/api"
EVENT_NAME="mayatest1-2025"

def fetch_event_speakers():
    client = PretalxClient(base_url=PRETALX_BASE_URL)
    client.auth()
    return client.get_speakers(EVENT_NAME)

