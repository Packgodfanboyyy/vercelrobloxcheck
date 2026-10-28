
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


SEARCH_URL = "https://search.roblox.com/catalog/json"


def search_roblox():
    """Best-effort search using the legacy Roblox catalog endpoint."""
    params = urlencode({
        "Category": "9",
        "Keyword": "TornadoTon",
        "ResultsPerPage": "30",
    })

    request = Request(
        f"{SEARCH_URL}?{params}",
        headers={"User-Agent": "TornadoTonTracker/1.0"},
    )

    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    results = {}

    def visit(value):
        if isinstance(value, dict):
            title = (
                value.get("Name")
                or value.get("name")
                or value.get("Title")
                or value.get("title")
            )
            asset_id = (
                value.get("AssetId")
                or value.get("assetId")
                or value.get("Id")
                or value.get("id")
            )

            if title and asset_id:
                title = str(title).strip()

                if "tornadoton" in title.casefold():
                    creator = (
                        value.get("CreatorName")
                        or value.get("creatorName")
                        or value.get("Creator")
                        or value.get("creator")
                        or "Not provided"
                    )
                    description = (
                        value.get("Description")
                        or value.get("description")
                        or ""
                    )

                    text = f"{title} {creator} {description}".casefold()

                    results[str(asset_id)] = {
                        "id": str(asset_id),
                        "title": title,
                        "creator": str(creator),
                        "distrokid_mentioned": "distrokid" in text,
                    }

            for child in value.values():
                visit(child)

        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return list(results.values())


def send_discord_message(content):
    webhook = os.environ["DISCORD_WEBHOOK_URL"]

    body = json.dumps({
        "content": content,
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")

    request = Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=15) as response:
        return response.status


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET", "")
        authorization = self.headers.get("Authorization", "")

        if not secret or authorization != f"Bearer {secret}":
            self.respond(401, {"error": "Unauthorized"})
            return

        try:
            matches = search_roblox()

            if matches:
                lines = [
                    "**🎵 Daily TornadoTon Roblox catalog check**",
                    f"Search returned {len(matches)} matching result(s):",
                ]

                for item in matches[:10]:
                    asset_url = (
                        "https://create.roblox.com/store/asset/"
                        f"{item['id']}/"
                    )

                    uploader = (
                        "DistroKid mentioned in listing data"
                        if item["distrokid_mentioned"]
                        else "DistroKid attribution not verified"
                    )

                    lines.append(
                        f"• [{item['title']}]({asset_url}) "
                        f"(ID: `{item['id']}`) — "
                        f"Creator: {item['creator']} — {uploader}"
                    )

                message = "\n".join(lines)
            else:
                message = (
                    "**🔎 Daily TornadoTon Roblox catalog check**\n"
                    "The search returned no matching titles today. "
                    "This does not prove the song is absent; "
                    "the search endpoint may be incomplete or restricted."
                )

            send_discord_message(message)
            self.respond(200, {
                "ok": True,
                "matches": len(matches),
                "message": "Discord status sent",
            })

        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            # Try to report failures to Discord, too.
            try:
                send_discord_message(
                    "**⚠️ TornadoTon daily check failed.**\n"
                    "Roblox search could not be completed. "
                    "This is not a 'song not found' result.\n"
                    f"Error: `{str(exc)[:500]}`"
                )
            except Exception:
                pass

            self.respond(502, {
                "ok": False,
                "error": str(exc)[:500],
            })

    def respond(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
