from flask import Blueprint, request, render_template, make_response
import xmltodict, os, random, string, time, base64
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shopdeck.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
from shopdeckdb.models import *
from django.core.exceptions import ObjectDoesNotExist
from shopdeck import settings
from io import BytesIO
from time import sleep

print("ECS Starting Up")

#generate totally-genuine-devicetoken
def id_generator(size=21, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

ecs = Blueprint("ecs", "ecs")
@ecs.route("/ecs/services/ECommerceSOAP", methods=['POST'])
def soap():
    if request.get_data() == b"OwO":
        return "UwU"
    try:
        parsed = xmltodict.parse(request.get_data())
    except:
        return "Error"
    if request.headers.get('User-Agent') != "CTR EC 040600 Mar 14 2012 13:32:39" and request.headers.get('User-Agent') != "CTR NUP 040600 Mar 14 2012 13:32:39":
        return "Error"
    if 'ecs:GetAccountStatus' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        print("nim is fetching account info")
        try:
            ds = Client3DS.objects.get(consoleid=str(parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:DeviceId']))
            if 'ecs:AccountId' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']:
                if str(ds.id) != parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:AccountId']:
                    r = make_response(render_template("ecs/getAccountStatusError.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:MessageId'], time=int(round(time.time()*1000)), accountid=ds.id, country=ds.country, region=ds.region, setting=settings, errcode="902", errmsg="IAS - Account Id is not registered"))
                    r.headers.set("Content-Type", "text/xml; charset=utf-8")
                    return r
        except ObjectDoesNotExist:
            #Create new Client3DS object, and save it!
            print("New 3DSClient: "+str(parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:DeviceId']))
            ds = Client3DS.objects.create(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:DeviceId'], devicetoken=id_generator(), is_terminated=False, balance=0, language=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:Language'], region=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:Region'], country=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:Country'], uniquekey=id_generator())
        if 'ecs:DeviceToken' not in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']:
            r = make_response(render_template("ecs/getAccountStatusError.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:MessageId'], time=int(round(time.time()*1000)), accountid=ds.id, country=ds.country, region=ds.region, setting=settings, errcode="903", errmsg="IAS - Invalid device token"))
            r.headers.set("Content-Type", "text/xml; charset=utf-8")
            return r
        try:
            ctid = customTitleID.objects.filter(related_to=ds)
        except ObjectDoesNotExist:
            ctid = []
        try:
            owned = ownedTitle.objects.filter(owner=ds)
        except ObjectDoesNotExist:
            owned = []
        r = make_response(render_template("ecs/getAccountStatus.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetAccountStatus']['ecs:MessageId'], time=int(round(time.time()*1000)), accountid=ds.id, balance=ds.balance, country=ds.country, region=ds.region, owned=owned, setting=settings, customtid=ctid, int=int))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:AccountListETicketIds' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountListETicketIds']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        try:
            ctid = customTitleID.objects.filter(related_to=ds)
        except ObjectDoesNotExist:
            ctid = []
        try:
            owned = ownedTitle.objects.filter(owner=ds)
        except ObjectDoesNotExist:
            return "error"
        r = make_response(render_template("ecs/accountListETicketIds.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountListETicketIds']['ecs:MessageId'],time=int(round(time.time()*1000)), customtid=ctid, owned=owned, int=int))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:DeleteSavedCard' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        print("Synchronizing")
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:DeleteSavedCard']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        r = make_response(render_template("ecs/deleteSavedCard.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:DeleteSavedCard']['ecs:MessageId'],time=int(round(time.time()*1000)), ecsname="DeleteSavedCardResponse"))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:GetStandbyMode' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        print("Synchronizing")
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetStandbyMode']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        r = make_response(render_template("ecs/deleteSavedCard.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetStandbyMode']['ecs:MessageId'],time=int(round(time.time()*1000)), ecsname="GetStandbyModeResponse"))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:AccountGetETickets' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        print("Sending ticket...")
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        try:
            owned = ownedTitle.objects.get(ticketid='{:016x}'.format(int(parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:TicketId'])), owner=ds)
            istitle = True
        except ObjectDoesNotExist:
            istitle = False
        try:
            owned = ownedTicket.objects.get(ticketid='{:016x}'.format(int(parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:TicketId'])), owner=ds)
            istik = True
        except ObjectDoesNotExist:
            istik = False
        if istitle == False and istik==False:
            return "Error"
        _devcert = parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:DeviceCert']
        try:
            _raw = base64.b64decode(_devcert)
            with open('/tmp/opencode/devicecert.bin', 'wb') as _f:
                _f.write(_raw)
            print("DeviceCert dumped: %d bytes, @0xC6=%r, stored=%r" % (len(_raw), _raw[0xC6:0xCE], ds.devicecert_consoleid))
        except Exception as _e:
            print("DeviceCert dump failed:", _e)
        if not ds.devicecert_consoleid:
            print("No DeviceCert Console ID detected. Storing it!!!")
            cid = base64.b64decode(_devcert)[0xC6:0xCE].decode('utf-8')
            ds.devicecert_consoleid = cid
            ds.save()
        print("Generating ticket...")
        if istitle:
            realtik = "cdn/"+str(owned.title.tid)+"/title.tik"
            if os.path.isfile(realtik):
                with open(realtik, "rb") as f:
                    ticket_bytes = f.read()
            else:
                with open("basetik.bin", "rb") as f:
                    ticket_bytes = f.read()
        else:
            with open("basetik_licence.bin", "rb") as f:
                ticket_bytes = f.read()
        if istitle:
            titleid = owned.title.tid
        if istik:
            titleid = owned.item.title.tid
        titlever = 0
        if istitle:
            try:
                with open("cdn/"+str(owned.title.tid)+"/tmd.bin", "rb") as tmf:
                    tmd = tmf.read()
                # TMD header starts after the signature block (size depends on
                # signature type). 3dbrew: Title Version is at header+0x9C.
                sig_type = int.from_bytes(tmd[0:4], byteorder="big")
                header = {0x00010003: 0x240, 0x00010004: 0x140, 0x00010005: 0x80}.get(sig_type, 0x140)
                titlever = int.from_bytes(tmd[header+0x9C:header+0x9E], byteorder="big")
            except Exception:
                titlever = 0
            if not titlever:
                titlever = owned.title.version
        with BytesIO(ticket_bytes) as tk:
            #Write Title ID
            tk.seek(0x1DC)
            tk.write(int.to_bytes(int(titleid, base=16), 8, "big"))
            #Write Title Version to match the TMD version
            tk.seek(0x1E6)
            tk.write(int.to_bytes(titlever, 2, "big"))
            #Write Ticket ID
            tk.seek(0x1D0)
            tk.write(int.to_bytes(int(owned.ticketid, base=16), 8, "big"))
            #Write Console ID
            tk.seek(0x1D8)
            tk.write(int.to_bytes(int(ds.devicecert_consoleid, base=16), 4, "big"))
            #Write Account ID
            aid = "{:08d}".format(ds.id)
            tk.seek(0x21C)
            tk.write(int.to_bytes(int(aid, base=16), 4, "big"))
            modified_tik = tk.getvalue()
        #TODO when dlc update: check if ticket is one time licence, and if yes, delete it. else, do nothing.
        if istik:
            owned.delete()
        r = make_response(render_template("ecs/getAccountETickets.xml", id=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:DeviceId'], message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountGetETickets']['ecs:MessageId'],time=int(round(time.time()*1000)), tik=base64.b64encode(modified_tik).decode('utf-8')))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:AccountCheckBalance' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountCheckBalance']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        r = make_response(render_template("ecs/accountCheckBalance.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:AccountCheckBalance']['ecs:MessageId'], time=int(round(time.time()*1000)), balance=ds.balance, country=ds.country, ecsname="AccountCheckBalanceResponse"))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:CurrencyAccountsCheckBalance' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:CurrencyAccountsCheckBalance']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        r = make_response(render_template("ecs/accountCheckBalance.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:CurrencyAccountsCheckBalance']['ecs:MessageId'], time=int(round(time.time()*1000)), balance=ds.balance, country=ds.country, ecsname="CurrencyAccountsCheckBalanceResponse"))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    if 'ecs:GetTaxes' in parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']:
        try:
            ds = Client3DS.objects.get(consoleid=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetTaxes']['ecs:DeviceId'])
        except ObjectDoesNotExist:
            return "Error"
        try:
            aitem = item.objects.get(id=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetTaxes']['ecs:Items'])
        except ObjectDoesNotExist:
            return "Error"
        r = make_response(render_template("ecs/getTaxes.xml", id=ds.consoleid, message=parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body']['ecs:GetTaxes']['ecs:MessageId'],time=int(round(time.time()*1000)), country=ds.country, itemid=aitem.id, itemprice=aitem.price))
        r.headers.set("Content-Type", "text/xml; charset=utf-8")
        return r
    try:
        _action = list(parsed['SOAP-ENV:Envelope']['SOAP-ENV:Body'].keys())
    except Exception:
        _action = []
    print("Unhandled ECommerceSOAP action: "+str(_action), flush=True)
    return "Error"
