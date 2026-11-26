"""Place an outbound call: Twilio dials the number and streams the audio to the voice bot.

Usage: uv run python -m voice.dial <tunnel-host> [number in E.164, e.g. +9198...]
The number defaults to MY_PHONE_NUMBER in .env. On a Twilio trial it must be a verified number.
The bot must be running with: uv run python -m voice.bot -t twilio -x <tunnel-host>
"""

import os
import sys

from dotenv import load_dotenv
from twilio.rest import Client


def dial(host, to):
    twiml = f'<Response><Connect><Stream url="wss://{host}/ws"/></Connect></Response>'
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    call = client.calls.create(to=to, from_=os.environ["TWILIO_PHONE_NUMBER"], twiml=twiml)
    return call.sid


if __name__ == "__main__":
    load_dotenv()
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    to = sys.argv[2] if len(sys.argv) == 3 else os.environ.get("MY_PHONE_NUMBER")
    if not to:
        sys.exit("no number: pass one or set MY_PHONE_NUMBER in .env")
    print("call placed:", dial(sys.argv[1], to))
