from flask import Flask, jsonify
import requests
import os
import time

app = Flask(__name__)
app.json.sort_keys = False

# 🌐 Configurable Source URL & CDN Type
SOURCE_URL = os.environ.get("SOURCE_URL")

# 🔄 CDN Type Config: আপনি পরিবেশের ভ্যারিয়েবল বা এখানে পরিবর্তন করতে পারবেন
# অপশন হতে পারে: "pdlive", "fblive", "flive" ইত্যাদি। (ডিফল্ট: pdlive)
CDN_TYPE = os.environ.get("CDN_TYPE", "pdlive")

# 🔥 Cloudflare Worker Playlist Base URLs
IND_PLAYLIST_BASE = "https://fc-ind-owner-tg.ivan-flux.workers.dev"
BD_PLAYLIST_BASE = "https://fc-bd-owner.ivan-flux.workers.dev"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})


def rewrite_cdn_url(url, new_cdn_type):
    """
    FanCode CDN লিঙ্ক রি-রাইট করার ফাংশন।
    উদাহরণ: -flive.fancode.com কে -pdlive.fancode.com বা -fblive.fancode.com এ রূপান্তর করবে।
    """
    if isinstance(url, str) and "fancode.com" in url and "-flive." in url:
        return url.replace("-flive.", f"-{new_cdn_type}.")
    return url


def process_json(obj):
    if isinstance(obj, dict):

        # ✅ ১. match_id মডিফাই এবং Stream (ind) & Stream (bd) লিঙ্ক যোগ করা
        if "match_id" in obj and "language" in obj:
            match_id = obj.get("match_id")
            language = obj.get("language")

            if match_id and language:
                # যদি match_id তে ল্যাঙ্গুয়েজ অলরেডি যুক্ত না থাকে
                if not match_id.endswith(f"-{language.upper()}"):
                    new_id = f"{match_id}-{language.upper()}"
                    obj["match_id"] = new_id
                else:
                    new_id = match_id

                # 🔥 Cloudflare Stream Links
                obj["Stream (ind)"] = f"{IND_PLAYLIST_BASE}/{new_id}.m3u8"
                obj["Stream (bd)"] = f"{BD_PLAYLIST_BASE}/{new_id}-BD.m3u8"

        # 🔥 ২. NEW: STREAMING_CDN লিঙ্ক রি-রাইট (flive -> pdlive / fblive)
        if "STREAMING_CDN" in obj and isinstance(obj["STREAMING_CDN"], dict):
            cdn = obj["STREAMING_CDN"]

            # fancode_cdn কে স্পষ্টভাবে চেনার সুবিধার্থে fancode_in_cdn কী (Key) যোগ করতে পারেন
            if "fancode_cdn" in cdn and "fancode_in_cdn" not in cdn:
                cdn["fancode_in_cdn"] = cdn["fancode_cdn"]

            # STREAMING_CDN এর ভিতরের সব URL ফিল্ড অটোমেটিক রি-রাইট করা
            for key, val in cdn.items():
                if isinstance(val, str):
                    cdn[key] = rewrite_cdn_url(val, CDN_TYPE)

                # backup অবজেক্ট থাকলে সেটির ভেতরের লিঙ্কগুলোও রি-রাইট করবে
                elif isinstance(val, dict):
                    for sub_key, sub_val in val.items():
                        if isinstance(sub_val, str):
                            val[sub_key] = rewrite_cdn_url(sub_val, CDN_TYPE)

        # 🔥 ৩. DRM Handling (MPD ফরম্যাটের জন্য)
        if "STREAMING_CDN" in obj and isinstance(obj["STREAMING_CDN"], dict):
            cdn = obj["STREAMING_CDN"]

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

        # 🔁 রিকার্সিভলি সাব-অবজেক্ট প্রসেস করা
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
        # 🔥 নতুন ডাটা পাওয়ার জন্য ক্যাশ বাইপাস করা
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
    return jsonify({
        "status": "FanCode JSON API Running",
        "active_cdn_type": CDN_TYPE
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
