from flask import Blueprint, request, make_response
import xmltodict
import time
import os
import socket

print("NUS Starting Up", flush=True)

nus = Blueprint("nus", "nus")


def _lan_ip() -> str:
    """LAN address the 3DS must dial for content (this PC)."""
    override = os.environ.get("RS_SERVER_IP")
    if override:
        return override
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _respond(envelope_body: str):
    response = make_response(envelope_body)
    response.headers.set("Content-Type", "text/xml; charset=utf-8")
    return response


def _soap_env(inner: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<soapenv:Body>' + inner + '</soapenv:Body></soapenv:Envelope>')


def _title_hash_response(body) -> str:
    fields = body.get('nus:GetSystemTitleHash') or body.get('GetSystemTitleHash') or {}
    device_id = fields.get('nus:DeviceId') or fields.get('DeviceId') or '0'
    message_id = fields.get('nus:MessageId') or fields.get('MessageId') or ''
    ts = int(round(time.time() * 1000))
    # Echo a fixed hash; on mismatch NIM calls GetSystemUpdate which returns
    # an empty title list, so no update is ever triggered.
    inner = ('<GetSystemTitleHashResponse xmlns="urn:nus.wsapi.broadon.com">'
             '<Version>1.0</Version>'
             f'<DeviceId>{device_id}</DeviceId>'
             f'<MessageId>{message_id}</MessageId>'
             f'<TimeStamp>{ts}</TimeStamp>'
             '<ErrorCode>0</ErrorCode>'
             '<TitleHash>7E745F7B67D553BEA847859404790C93</TitleHash>'
             '</GetSystemTitleHashResponse>')
    return _soap_env(inner)


def _system_update_response(body) -> str:
    fields = body.get('nus:GetSystemUpdate') or body.get('GetSystemUpdate') or {}
    device_id = fields.get('nus:DeviceId') or fields.get('DeviceId') or '0'
    message_id = fields.get('nus:MessageId') or fields.get('MessageId') or ''
    ts = int(round(time.time() * 1000))
    # Echo the console's own installed title list back (hex IDs, same versions).
    # If nothing is newer and nothing is missing, NIM concludes "no sysupdate".
    raw_titles = fields.get('nus:TitleVersion')
    if raw_titles is None:
        raw_titles = fields.get('TitleVersion')
    if not isinstance(raw_titles, list):
        raw_titles = [raw_titles]
    title_xml = ""
    for tv in raw_titles or []:
        tid = tv.get('nus:TitleId') or tv.get('TitleId')
        ver = tv.get('nus:Version') or tv.get('Version')
        try:
            tid_hex = "%016X" % int(tid)
        except (TypeError, ValueError):
            tid_hex = tid
        title_xml += (f"<TitleVersion><TitleId>{tid_hex}</TitleId>"
                      f"<Version>{ver}</Version></TitleVersion>")
    content_base = f'http://{_lan_ip()}:8000/ccs/download'
    uncached_base = f'https://{_lan_ip()}:8000/ccs/download'
    inner = ('<GetSystemUpdateResponse xmlns="urn:nus.wsapi.broadon.com">'
             '<Version>1.0</Version>'
             f'<DeviceId>{device_id}</DeviceId>'
             f'<MessageId>{message_id}</MessageId>'
             f'<TimeStamp>{ts}</TimeStamp>'
             '<ErrorCode>0</ErrorCode>'
             f'<ContentPrefixURL>{content_base}</ContentPrefixURL>'
             f'<UncachedContentPrefixURL>{uncached_base}</UncachedContentPrefixURL>'
             + title_xml +
             '<UploadAuditData>1</UploadAuditData>'
             '<TitleHash>7E745F7B67D553BEA847859404790C93</TitleHash>'
             '</GetSystemUpdateResponse>')
    return _soap_env(inner)


@nus.route("/nus/services/NetUpdateSOAP", methods=['POST'])
def soap():
    data = request.get_data()
    if data == b"OwO":
        return "UwU"
    try:
        parsed = xmltodict.parse(data)
    except Exception:
        return make_response("Error", 500)
    try:
        body = parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']
    except Exception:
        body = parsed
    op = [k for k in body if 'SystemTitleHash' in k or 'Update' in k]
    print("NUS op: " + (",".join(op) if op else "unknown"), flush=True)
    print("  body: " + data.decode('utf-8', 'replace')[:2000].replace("\n", " "), flush=True)
    if any('SystemTitleHash' in k for k in body):
        return _respond(_title_hash_response(body))
    if any('GetSystemUpdate' in k for k in body):
        return _respond(_system_update_response(body))
    return _respond(_title_hash_response(body))