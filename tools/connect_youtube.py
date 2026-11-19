"""Authorize unattended YouTube uploads with a Google Desktop OAuth client."""

import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

from tools.mcp_publish import load_credentials, save_credentials


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_json", help="Google Cloud Desktop OAuth client JSON")
    args = parser.parse_args()
    flow = InstalledAppFlow.from_client_secrets_file(
        args.client_json, ["https://www.googleapis.com/auth/youtube.upload"],
        autogenerate_code_verifier=True,
    )
    auth = flow.run_local_server(host="127.0.0.1", port=0, prompt="consent")
    if not auth.refresh_token:
        parser.exit(1, "Google did not return an offline refresh token.\n")

    credentials = load_credentials()
    credentials["youtube"] = {
        "enabled": True,
        "client_id": auth.client_id,
        "client_secret": auth.client_secret,
        "refresh_token": auth.refresh_token,
    }
    if not save_credentials(credentials):
        parser.exit(1, "Could not save YouTube authorization.\n")
    print("YouTube authorization saved. Restart Clipify to apply upload settings.")


if __name__ == "__main__":
    main()
