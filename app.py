"""
app.py — PW Video URL API (plain GET, no encryption)
"""

import os
import time
import urllib.parse
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_BASE = "https://api.penpencil.co"


def _headers(token, uid, random_id):
    """Exact headers from browser capture."""
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "client-type": "WEB",
        "client-version": "3219",
        "client-id": "5eb393ee95fab7468a79d189",
        "x-sdk-version": "0.0.20",
        "version": "3.2.19",
        "networktype": "4g",
        "devicememory": "8192",
        "devicetype": "tablet",
        "screenresolution": "393 x 870",
        "devicestreamingtechnology": '{"dash":{"isSupported":true,"formats":["mp4","m4a"],"codecs":["avc1","aac"]},"hls":{"isSupported":false,"formats":[],"codecs":[]}}',
        "drmcapability": '{"aesSupport":"yes","fairPlayDrmSupport":"no","playreadyDrmSupport":"no","widevineDRMSupport":"yes"}',
        "frameratecapability": '{"videoQuality":"Lower than 480p (SD)"}',
        "videocodeccapability": '{"Hevc":{"isSupported":"true","Profile":[{"name":"Main"},{"name":"Main 10"},{"name":"Main 12"},{"name":"Main 4:2:2 10"},{"name":"Main 4:2:2 12"},{"name":"Main 4:4:4"},{"name":"Main 4:4:4 10"},{"name":"Main 4:4:4 12"},{"name":"Main 4:4:4 16 Intra"}]},"AV1":{"isSupported":"true","Profile":[{"name":"Main"},{"name":"High"},{"name":"Professional"}]}}',
        "audiocodeccapability": '{"AAC-LC":{"isSupported":true,"Profile":[{"container":"audio/mp4","supported":true},{"container":"audio/webm","supported":false},{"container":"audio/ogg","supported":false}]},"HE-AAC v1":{"isSupported":true,"Profile":[{"container":"audio/mp4","supported":true},{"container":"audio/webm","supported":false},{"container":"audio/ogg","supported":false}]},"HE-AAC v2":{"isSupported":true,"Profile":[{"container":"audio/mp4","supported":true},{"container":"audio/webm","supported":false},{"container":"audio/ogg","supported":false}]}}',
        "authorization": f"Bearer {token}",
        "userid": uid,
        "randomid": random_id,
        "origin": "https://www.pw.live",
        "referer": "https://www.pw.live/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    }


@app.route("/")
def index():
    return jsonify({
        "status": "active",
        "service": "PW Video URL API",
        "endpoints": ["/health", "/api/play", "/api/video-url-details"],
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": int(time.time())})


@app.route("/api/video-url-details", methods=["GET", "POST"])
def video_url_details():
    """
    Fetch signed video URL from PW.

    GET: /api/video-url-details?token=...&childId=...&videoUrl=...&parentId=...
    POST: {"token": "...", "childId": "...", "videoUrl": "...", "parentId": "..."}
    """
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
    else:
        body = request.args.to_dict()

    token = body.get("token", "").strip()
    child_id = body.get("childId", "").strip()
    video_url = body.get("videoUrl", "").strip()
    parent_id = body.get("parentId", "").strip()

    if not token:
        return jsonify({"success": False, "error": "token required"}), 400
    if not child_id:
        return jsonify({"success": False, "error": "childId required"}), 400
    if not video_url:
        return jsonify({"success": False, "error": "videoUrl required"}), 400

    # Extract uid from JWT (for userid header)
    import base64, json
    try:
        parts = token.replace("Bearer ", "").strip().split(".")
        p = parts[1] + "=" * (-len(parts[1]) % 4)
        jwt_data = json.loads(base64.urlsafe_b64decode(p))
        uid = jwt_data.get("data", {}).get("_id", "")
    except Exception as e:
        return jsonify({"success": False, "error": f"JWT decode failed: {e}"}), 400

    # Build URL
    url_enc = urllib.parse.quote(video_url, safe="")
    api_url = (
        f"{API_BASE}/v1/videos/video-url-details"
        f"?type=LISTING_VIDEOS"
        f"&videoContainerType=DASH"
        f"&reqType=query"
        f"&childId={child_id}"
        f"&videoUrl={url_enc}"
        f"&clientVersion=201"
    )

    random_id = body.get("randomId") or __import__("uuid").uuid4().hex

    try:
        resp = requests.get(
            api_url,
            headers=_headers(token, uid, random_id),
            timeout=20,
        )
    except requests.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 500

    if resp.status_code != 200:
        return jsonify({
            "success": False,
            "error": f"PW API {resp.status_code}",
            "response": resp.text[:300],
        }), resp.status_code

    data = resp.json()
    if not data.get("success"):
        return jsonify({"success": False, "error": data}), 500

    # Build final URL
    d = data["data"]
    full_url = d.get("url", "") + d.get("signedUrl", "")

    return jsonify({
        "success": True,
        "data": {
            **d,
            "fullUrl": full_url,
            "expiresIn": max(0, int(d.get("signatureExpireAt", 0) / 1000 - time.time())),
        },
    })


@app.route("/api/play", methods=["POST"])
def play():
    """
    Simple wrapper — same as video-url-details but returns only full URL.
    POST: {"token": "...", "childId": "...", "videoUrl": "..."}
    """
    body = request.get_json(force=True, silent=True) or {}
    resp = video_url_details.__wrapped__(body) if hasattr(video_url_details, "__wrapped__") else None
    # Just forward to the same logic
    with app.test_request_context(json=body, method="POST"):
        return video_url_details()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
