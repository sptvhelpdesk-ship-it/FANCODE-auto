from flask import Flask, jsonify
import requests
import os
import time

app = Flask(__name__)
app.json.sort_keys = False

SOURCE_URL = os.environ.get("SOURCE_URL")
CDN_TYPE = "pd"

IND_PLAYLIST_BASE = "https://fc-ind-owner-tg.ivan-flux.workers.dev"
BD_PLAYLIST_BASE = "https://fc-bd-owner.ivan-flux.workers.dev"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def get_target_cdn(mode):
    mapping = {"pd": "pdlive", "fb": "fblive", "fl": "flive"}
    return mapping.get(str(mode).lower(), mode)


def process_json(obj):
    if isinstance(obj, dict):
        if "match_id" in obj and "language" in obj:
            match_id = obj.get("match_id")
            language = obj.get("language")

            if match_id and language:
                new_id = f"{match_id}-{language.upper()}"
                obj["match_id"] = new_id

                obj["Stream (ind)"] = f"{IND_PLAYLIST_BASE}/{new_id}.m3u8"
                obj["Stream (bd)"] = f"{BD_PLAYLIST_BASE}/{new_id}-BD.m3u8"

        if "STREAMING_CDN" in obj and isinstance(obj["STREAMING_CDN"], dict):
            cdn = obj["STREAMING_CDN"]
            target = get_target_cdn(CDN_TYPE)

            for key in cdn:
                val = cdn.get(key)
                if isinstance(val, str) and "fancode.com" in val:
                    for old in ["-flive.", "-pdlive.", "-fblive."]:
                        if old in val:
                            cdn[key] = val.replace(old, f"-{target}.")
                elif isinstance(val, dict):
                    for sub_key in val:
                        sub_val = val.get(sub_key)
                        if isinstance(sub_val, str) and "fancode.com" in sub_val:
                            for old in ["-flive.", "-pdlive.", "-fblive."]:
                                if old in sub_val:
                                    val[sub_key] = sub_val.replace(old, f"-{target}.")

            if cdn.get("is_drm") is True:
                drm_data = cdn.get("drm", {})
                keys = drm_data.get("keys", [])

                if keys:
                    drm_key = keys[0]

                    for key in cdn:
                        value = cdn.get(key)

                        if isinstance(value, str) and value.endswith(".mpd"):
                            cdn[key] = (
                                f"{value}|user-agent=iVan-flux"
                                f"&drmScheme=clearkey"
                                f"&drmLicense={drm_key}"
                            )

        for key in obj:
            process_json(obj[key])

    elif isinstance(obj, list):
        for item in obj:
            process_json(item)

    return obj


@app.route("/fancode")
def fancode():
    if not SOURCE_URL:
        return jsonify({"error": "SOURCE_URL not set"}), 500

    try:
        r = session.get(f"{SOURCE_URL}?t={int(time.time())}", timeout=10)

        if r.status_code != 200:
            return jsonify({"error": "Source Down"}), 502

        data = r.json()
        final_data = process_json(data)

        return jsonify(final_data), 200, {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
        }

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({"status": "FanCode JSON API Running"})


if __name__ == "__main__":
    app.run()
