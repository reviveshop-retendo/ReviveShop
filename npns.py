from flask import Blueprint, request, jsonify

print("NPNS stub Starting Up")

npns = Blueprint("npns", "npns")


@npns.route("/api/v1/<path:rest>", methods=['GET', 'POST', 'PUT', 'DELETE'])
def api(rest):
    body = request.get_data(as_text=True)
    print("NPNS: %s /api/v1/%s" % (request.method, rest), flush=True)
    print("  body: " + body[:1000].replace("\n", " "), flush=True)
    if rest.endswith("devices.json") or rest.endswith("/devices"):
        return jsonify({"devices": []})
    return jsonify({})

@npns.route("/api/v1/people/@me/devices/@current/attributes", methods=['POST'])
@npns.route("/v1/api/people/@me/devices/@current/attributes", methods=['POST'])
def nim_device_attributes():
    # Stub to prevent 007-2673 communication error on 3DS eShop
    return "{}", 200
