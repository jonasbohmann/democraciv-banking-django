from django.conf import settings


def make_embed(*, title: str, description: str, url: str, colour: int = 1776672) -> dict:
    return {
        "title": str(title),
        "description": str(description),
        "url": str(url),
        "color": colour,
        "author": {
            "name": settings.BANK_NAME,
            "icon_url": settings.BANK_ICON_URL
        }
    }


def add_field(embed: dict, *, name: str, value: str, inline: bool = False) -> dict:
    fields = embed.get('fields', [])
    name = str(name)
    value = str(value)

    if name == "":
        name = "*empty*"

    if value == "":
        value = "*empty*"

    fields.append({'name': name, 'value': value[:1020], 'inline': inline})
    embed['fields'] = fields
    return embed
