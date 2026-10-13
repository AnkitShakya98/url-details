"""app.py — PW Video URL via encrypted playback/start."""

import os
import time
import base64
import json
import uuid
from flask import Flask, request, jsonify
import requests

from pw_crypto import encrypt, decrypt, decode_jwt, PWCryptoError

app = Flask(__name__)
API_BASE = "https://api.penpencil.co"
ORG_ID = "5eb393ee95fab7468a79d189"


def _headers(token, uid, random_id, roles):
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "client-type": "WEB",
        "client-version": "3219",
        "client-id": ORG_ID,
        "x-sdk-version": "0.0.20",
        "version": "3.2.19",
        "networktype": "4g",
        "devicememory": "8192",
        "devicetype": "tablet",
        "screenresolution": "393 x 870",
        "organizationId": ORG_ID,                     # ← CRITICAL
        "roles": roles,                                # ← CRITICAL
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
    return jsonify({"status": "active", "service": "PW Video API"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": int(time.time())})


@app.route("/api/play", methods=["POST", "GET"])
def play():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
    else:
        body = request.args.to_dict()

    token = body.get("token", "").strip()
    child_id = body.get("childId", "").strip()
    parent_id = body.get("parentId", "").strip()

    if not token or not child_id or not parent_id:
        return jsonify({"success": False, "error": "token, childId, parentId required"}), 400

    # Decode JWT
    try:
        jwt_data = decode_jwt(token)
        jti = jwt_data["jti"]
        uid = jwt_data["data"]["_id"]
        roles = ",".join(jwt_data["data"].get("roles", []))
    except Exception as e:
        return jsonify({"success": False, "error": f"JWT decode: {e}"}), 400

    # Build payload
    payload = {
        "type": "BATCHES",
        "videoContainerType": "DASH",
        "reqType": "query",
        "childId": child_id,
        "parentId": parent_id,
        "clientVersion": "201",
        "timestamp": int(time.time() * 1000),
    }

    # Encrypt
    try:
        encrypted = encrypt(jti, uid, payload)
    except PWCryptoError as e:
        return jsonify({"success": False, "error": f"encrypt: {e}"}), 500

    # POST
    try:
        resp = requests.post(
            f"{API_BASE}/v1/videos/playback/start",
            headers=_headers(token, uid, str(uuid.uuid4()), roles),
            json=encrypted,
            timeout=20,
        )
    except requests.RequestException as e:
        return jsonify({"success": False, "error": f"request: {e}"}), 500

    if resp.status_code not in (200, 201):
        return jsonify({
            "success": False,
            "error": f"PW API {resp.status_code}",
            "response": resp.text[:500],
        }), resp.status_code

    api_body = resp.json()
    if not api_body.get("success"):
        return jsonify({"success": False, "error": api_body}), 500

    # Decrypt
    enc_resp = api_body["data"]
    if "data" in enc_resp and isinstance(enc_resp["data"], dict):
        enc_resp = enc_resp["data"]

    try:
        decrypted = decrypt(jti, uid, enc_resp)
    except PWCryptoError as e:
        return jsonify({"success": False, "error": f"decrypt: {e}"}), 500

    url = decrypted.get("url", "")
    signed = decrypted.get("signedUrl", "")

    return jsonify({
        "success": True,
        "data": {
            **decrypted,
            "fullUrl": url + signed if url and signed else url,
            "expiresIn": max(0, int(decrypted.get("signatureExpireAt", 0) / 1000 - time.time())),
        },
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
