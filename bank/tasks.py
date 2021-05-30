import requests

from django.conf import settings

from background_task import background


@background(schedule=10)
def discord_dm_notification(payload):
    requests.post(settings.DEMOCRACIV_DISCORD_BOT_DM_ENDPOINT, json=payload)
