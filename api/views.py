from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from shopdeck import settings
from shopdeckdb.models import *
from django.core.exceptions import ObjectDoesNotExist
import time, random, string, os
from django.contrib.sessions.backends.db import SessionStore

print("API (Ninja) Starting Up")

def id_generator(size=32, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def homebrew_owned(ds):
    """Every public title is treated as owned by every console.

    This shop only ever hosts homebrew, so "everything appears owned" is not a
    licence bypass - it simply lets a console download the homebrew it is
    entitled to without going through checkout. That matters because the
    purchase flow (Tap Here to Purchase) is refused client-side with 007-2001
    on consoles carrying an attached NNID the eShop cannot validate; the
    console stops after tax_location and sends no purchase request at all, so
    there is no server-side seam to fix. Downloading an already-owned title
    validates nothing and works, and it is the only path that does.

    The ownedTitle row is not just a list entry: it carries the ticketid the
    console installs (ecs.py AccountGetETickets) and gates the CDN content
    fetch (cdn.py). Faking the owned list without the row breaks the download,
    so this materialises a real row per public title, exactly like the webui
    redemption path (webui/views.py). Rows are only ever added, never
    removed, so a real purchase record is never clobbered.
    """
    for title in Title.objects.filter(public=True):
        ownedTitle.objects.get_or_create(
            title=title, owner=ds,
            defaults={
                "version": title.version,
                "ticketid": (b'\x00\x04' + os.urandom(6)).hex(),
            },
        )
    return ownedTitle.objects.filter(owner=ds)

@csrf_exempt
def service_hosts(request):
   res = {"services":{"service":[{"name":"CCIF","origin_fqdn":settings.SOAP_URL},{"name":"SAMURAI_CTR","origin_fqdn":settings.METADATA_API_URL,"cdn_fqdn":settings.METADATA_API_URL},{"name":"EOU","origin_fqdn":settings.SOAP_URL,"cdn_fqdn":settings.SOAP_URL}]}}
   return JsonResponse(res)

REGION_CODES = {
   "US": "USA", "JP": "JPN", "GB": "EUR", "FR": "EUR", "DE": "EUR",
   "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR",
   "PT": "EUR", "IE": "EUR", "FI": "EUR", "SE": "EUR", "NO": "EUR",
   "DK": "EUR", "CH": "EUR", "GR": "EUR", "CZ": "EUR", "HU": "EUR",
   "PL": "EUR", "RO": "EUR", "AU": "AUS", "BR": "BRA", "CN": "CHN",
   "KR": "KOR", "TW": "TWN",
}

@csrf_exempt
def country(request, country):
   region_code = REGION_CODES.get(country.upper(), country)
   res = {"country_detail":{"region_code":region_code,"max_cash":{"amount":"99999,00 Credit","currency":"CREDIT","raw_value":"99999"},"loyalty_system_available":False,"legal_payment_message_required":False,"legal_business_message_required":False,"tax_excluded_country":True,"tax_free_country":True,"prepaid_card_available":True,"credit_card_available":False,"credit_card_store_available":False,"jcb_security_code_available":False,"nfc_available":False,"coupon_available":False,"my_coupon_available":True,"price_format":{"positive_prefix":"","positive_suffix":" Credit","negative_prefix":"- ","negative_suffix":" Credit","formats":{"format":[{"value":"# ### ### ###,##","digit":"#"}],"pattern_id":"5"}},"default_timezone":"+00:00","eshop_available":True,"name":country,"iso_code":country,"default_language_code":"en","language_selectable":False}}
   return JsonResponse(res)

@csrf_exempt
def open(request):
   data = request.POST
   if data.get("device_id")==None:
      return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=data.get("device_id"))
   except ObjectDoesNotExist:
      return JsonResponse({"error": True})
   if ds.is_terminated:
      return JsonResponse({"error": {"code": "8008", "message": "Your account has been terminated. Sorry."}}, status=400)
   s = SessionStore()
   s['deviceid'] = data.get("device_id")
   s.create()
   currenttime = int(round(time.time()*1000))
   if request.headers.get("User-Agent") != None:
      if request.headers.get("User-Agent").startswith("MINT") and request.get_full_path() == "/ninja/ws/my/session/!open?_type=json":
         #LOTS of placeholder here coz i dont have access to nintendo servers
         # NOTE: shop_account_initialized MUST stay False. 007-2001 is the NNID /
         # account-link error; returning True tells the console the eShop account
         # setup is already complete, so it skips the NNID registration step and
         # aborts checkout locally with 007-2001 before sending any request.
         # This matches Whatsauser/Shopdeck-Updated, the documented 007-2001 fix.
         res = {"session_config":{"pid":ds.id,"account_id":"Somebody","mii":{"name":"Somebody","icon_url":"https://example.com/"},"country":ds.country,"saved_lang":ds.language,"shop_account_initialized":False,"device_link_updated":False,"owned_titles_modified":currenttime,"shared_titles_last_modified":currenttime,"age":25,"server_time":currenttime,"devices":{"device":[{"name":"CTR","initial_device_account_id":str(ds.id),"npns_ready":True,"id":4}]},"wishlist_last_modified":currenttime,"parental_controls":{"parental_control":[{"device":"CTR","type":"game_rating_age","value":0},{"device":"CTR","type":"game_rating_lock","value":0},{"device":"CTR","type":"shopping","value":0}]},"auto_billing_contracted":False,"id":s.session_key}}
      else:
         # Non-MINT client: the fix fork returns a deliberately minimal session so
         # the console treats this as an uninitialised account and runs its own
         # setup/link flow. Returning the full MINT object here also caused the
         # console to consider itself linked and fail with 007-2001.
         res = {"session_config":{"country":ds.country,"saved_lang":ds.language,"shop_account_initialized":False,"device_link_updated":False,"owned_titles_modified":currenttime,"shared_titles_last_modified":currenttime,"server_time":currenttime,"devices":{"device":[{"name":"CTR","id":4}]},"auto_billing_contracted":False,"id":s.session_key}}
      res = JsonResponse(res)
      res.set_cookie("JSESSIONID", s.session_key, httponly=True, path="/ninja")
      res.set_cookie("AWSELB", s.session_key + ".aws-lb", httponly=True, path="/ninja")
      return res

@csrf_exempt
def close(request):
   request.session.flush()
   return HttpResponse()

@csrf_exempt
def balance(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   res = {"balance":{"amount":str(ds.balance)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance)}}
   return JsonResponse(res)

#This is due to how eShop servers handle my/wishlist/notice: its a empty json, even if you have wishlisted titles
@csrf_exempt
def dummy_wishlist(request):
   res = {"wishlist_notice":{"wished_title_id":[],"total":0}}
   return JsonResponse(res)

@csrf_exempt
def wishlist(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   wishlisted_titles = wishlistedTitle.objects.filter(owner=ds)
   wishlisted = []
   for title in wishlisted_titles:
      wishlisted.append({"platform": {"name": title.title.platform.name, "id": title.title.platform.id, "device": "CTR", "category": title.title.genre.id}, "publisher": {"name": title.title.publisher.publisher_name, "id": title.title.publisher.id}, "display_genre": title.title.genre.name, "release_date_on_eshop": str(title.title.date), "release_date_on_original": str(title.title.date), "retail_sales": title.title.retail_sales, "eshop_sales": True, "in_app_purchase": title.title.in_app_purchase, "name": title.title.name, "id": title.title.id, "icon_url": title.title.icon_url, "banner_url": title.title.banner_url})
   res = {"wishlist":{"wished_title":wishlisted,"total":len(wishlisted)}}
   return JsonResponse(res)

#FIXME: Make this not just a static JSON response.
@csrf_exempt
def owned_coupons(request):
   res = {"coupons":{}}
   return JsonResponse(res)

@csrf_exempt
def ownedtitles(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   owned_titles = homebrew_owned(ds)
   owned = []
   i = 0
   for title in owned_titles:
      owned.append({"title_id": title.title.tid, "id": title.title.id, "index": i})
      i += 1

   res = {"owned_titles":{"owned_title":owned}}
   return JsonResponse(res)

@csrf_exempt
def language(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   res = {"session_config":{"saved_lang":ds.language}}
   return JsonResponse(res)

@csrf_exempt
def empty(request):
   return JsonResponse({})

@csrf_exempt
def online_price(request, country):
   if request.GET.get('title[]') == None:
      return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   tlist = list(request.GET.get('title[]').split(","))
   titles = []
   for ind_title in tlist:
      try:
         title = Title.objects.get(id=resolve_title_pk(ind_title))
         try:
            titleowned = ownedTitle.objects.get(title=title, owner=ds)
            is_title_owned = True
         except ObjectDoesNotExist:
            is_title_owned = False
         if title.price == 0:
            titleprice = "Free"
         else:
            titleprice = str(title.price)+",00 Credit"
         titles.append({"title_id": int(ind_title), "eshop_sales_status": "onsale", "price": {"regular_price": {"amount": titleprice, "currency": "CREDIT", "raw_value": str(title.price), "id": 2172116800}}, "title_owned": is_title_owned})
      except ObjectDoesNotExist:
         try:
            mv = movie.objects.get(id=int(ind_title))
         except ObjectDoesNotExist:
            return JsonResponse({"error": True})
         try:
            ownedMovie.objects.get(movie=mv, owner=ds)
            is_movie_owned = True
         except ObjectDoesNotExist:
            is_movie_owned = False
         if mv.price == 0:
            movieprice = "Free"
         else:
            movieprice = str(mv.price)+",00 Credit"
         titles.append({"title_id": int(ind_title), "eshop_sales_status": "onsale", "price": {"regular_price": {"amount": movieprice, "currency": "CREDIT", "raw_value": str(mv.price), "id": 2172116800}}, "title_owned": is_movie_owned})
   res = {"online_prices": {"online_price": titles}}
   return JsonResponse(res)

@csrf_exempt
def ec_info(request, country, tid):
   try:
      title = Title.objects.get(id=resolve_title_pk(tid))
   except:
      try:
         mv = movie.objects.get(id=int(tid))
         res = {"title_ec_info":{"title_id":mv.id,"content_size":0,"title_version":"0","disable_download":not mv.public}}
         return JsonResponse(res)
      except:
         return JsonResponse({"error": True})
   res = {"title_ec_info":{"title_id":title.tid,"content_size":title.size,"title_version":title.version,"disable_download":title.is_not_downloadable}}
   return JsonResponse(res)

@csrf_exempt
def put_wishlist(request):
   try:
      title = Title.objects.get(id=resolve_title_pk(request.POST.get("id")))
   except:
      return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   try:
      wishlisted = wishlistedTitle.objects.get(title=title, owner=ds)
      return JsonResponse({"error": True})
   except ObjectDoesNotExist:
      pass
   wishlisted = wishlistedTitle.objects.create(title=title, owner=ds)
   wishlisted.save()
   return JsonResponse({})

@csrf_exempt
def delete_wishlist(request, tid):
   try:
      title = Title.objects.get(id=resolve_title_pk(tid))
   except:
      return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   try:
      wishlisted = wishlistedTitle.objects.get(title=title, owner=ds)
   except ObjectDoesNotExist:
      return JsonResponse({"error": True})
   wishlisted.delete()
   return JsonResponse({})

@csrf_exempt
def check_redeemable(request):
   try:
      card = redeemableCard.objects.get(code=request.POST.get("card_number"))
   except:
      return JsonResponse({"error": {"code": "6561", "message": "This code is incorrect.\nPlease check up your code and try again."}}, status=400)
   if card.used:
      return JsonResponse({"error": {"code": "3101", "message": "This code is already used.\nSorry!"}}, status=400)
   if card.is_money:
      res = {"redeemable_card": {"number": request.POST.get("card_number"),"cash": {"amount": card.content+",00 Credit","currency": "CREDIT","raw_value": card.content}}}
      return JsonResponse(res)
   else:
      try:
         title = Title.objects.get(tid__iexact=card.content)
      except ObjectDoesNotExist:
         return JsonResponse({"error": {"code": "5615", "message": "The corresponding title was not found.\nContact an administrator."}}, status=400)
      if request.POST.get("tin") != None:
         return JsonResponse({"error": {"code": "6969", "message": "This is a title download code.\nPlease use the right tool."}})
      res = {"redeemable_card": {"number": request.POST.get("card_number"), "contents": {"content": [{"title": {"name": title.name, "id": title.id}}]},"title_ec_info": {"title_id": title.tid, "content_size": title.size, "title_version": title.version}}}
      return JsonResponse(res)
   
@csrf_exempt
def pretransac_redeem(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   res = {"prereplenish_info": {"current_balance": {"amount": str(ds.balance)+",00 Credit", "currency": "CREDIT", "raw_value": str(ds.balance)},"replenish_amount": {"amount": str(request.GET.get("replenish_amount"))+",00 Credit", "currency": "CREDIT", "raw_value": str(request.GET.get("replenish_amount"))},"post_balance": {"amount": str(int(float(request.GET.get("replenish_amount")))+ds.balance)+",00 Credit", "currency": "CREDIT", "raw_value": str(int(float(request.GET.get("replenish_amount")))+ds.balance)}}}
   return JsonResponse(res)

@csrf_exempt
def add_money_prepaid(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   try:
      card = redeemableCard.objects.get(code=request.POST.get("card_number"))
   except:
      return JsonResponse({"error": {"code": "6561", "message": "This code is incorrect.\nPlease check up your code and try again."}}, status=400)
   if card.used:
      res = {"error": {"code": "4626", "message": "This code is already used.\nSorry!"}}
      return JsonResponse(res, status=400)
   res = {"transaction_result": {"transaction_id": 1,"post_balance": {"amount": str(int(card.content)+ds.balance)+",00 Credit","currency": "CREDIT","raw_value": str(int(card.content)+ds.balance)},"integrated_account": True}}
   card.used = True
   card.save()
   ds.balance = int(card.content)+ds.balance
   ds.save()
   return JsonResponse(res)

@csrf_exempt
def prepurchase_info(request, country, tid):
   try:
      title = Title.objects.get(id=resolve_title_pk(tid))
      content_price = title.price
      content_size = title.size
   except:
      try:
         mv = movie.objects.get(id=int(tid))
         content_price = mv.price
         content_size = 0
      except:
         return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   res = {"prepurchase_info":{"tax_excluded":False,"purchasing_content":[{"eshop_sales_status":"onsale","content_size":content_size,"payment_amount":{"price":{"regular_price":{"amount":str(content_price)+",00 Credit","currency":"CREDIT","raw_value":str(content_price),"id":2172116800}},"total_amount":{"amount":str(content_price)+",00 Credit","currency":"CREDIT","raw_value":str(content_price)}}}],"current_balance":{"amount":str(ds.balance)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance)},"post_balance":{"amount":str(ds.balance-content_price)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance-content_price)},"total_amount":{"price":{"regular_price":{"amount":str(content_price)+",00 Credit","currency":"CREDIT","raw_value":str(content_price)}},"total_amount":{"amount":str(content_price)+",00 Credit","currency":"CREDIT","raw_value":str(content_price)}}}}
   return JsonResponse(res)

@csrf_exempt
def purcahse_title(request, country, tid):
   try:
      title = Title.objects.get(id=resolve_title_pk(tid))
   except:
      title = None
   if title is None:
      try:
         mv = movie.objects.get(id=int(tid))
      except:
         return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   if title is not None:
      cprice, cpublic, cid = title.price, title.public, title.tid
      if not cpublic:
         return JsonResponse({"error": {"code": "6265", "message": "This title is not public.\nYou cannot download it."}}, status=400)
      if ds.balance - cprice < 0:
         return JsonResponse({"error": {"code": "8167", "message": "You don't have enough money for that."}})
      try:
         owned = ownedTitle.objects.get(title=title, owner=ds)
      except ObjectDoesNotExist:
         ds.balance = ds.balance - cprice
         ds.save()
         owned = ownedTitle.objects.create(title=title, ticketid=(b'\x00\x04'+ os.urandom(6)).hex(), version=title.version, owner=ds)
         owned.save()
   else:
      cprice, cpublic, cid = mv.price, mv.public, mv.id
      if not cpublic:
         return JsonResponse({"error": {"code": "6265", "message": "This video is not public.\nYou cannot download it."}}, status=400)
      if ds.balance - cprice < 0:
         return JsonResponse({"error": {"code": "8167", "message": "You don't have enough money for that."}})
      try:
         owned = ownedMovie.objects.get(movie=mv, owner=ds)
      except ObjectDoesNotExist:
         ds.balance = ds.balance - cprice
         ds.save()
         owned = ownedMovie.objects.create(movie=mv, ticketid=(b'\x00\x04'+ os.urandom(6)).hex(), owner=ds)
         owned.save()
   res = {"transaction_result":{"transaction_id":1,"title_id":cid,"ticket_id":int(owned.ticketid, base=16),"post_balance":{"amount":str(ds.balance)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance)},"business_type":"NCL_DIST","integrated_account":True}}
   return JsonResponse(res)

@csrf_exempt
def purcahse_ticket(request, country, tid):
   try:
      aitem = item.objects.get(id=int(request.POST.get("item_id[]")))
   except:
      return JsonResponse({"error": True})
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   if ds.balance - aitem.price < 0:
      return JsonResponse({"error": {"code": "8167", "message": "You don't have enough money for that."}})
   try:
      owned = ownedTicket.objects.get(item=aitem, owner=ds)
   except ObjectDoesNotExist:
      ds.balance = ds.balance - aitem.price
      ds.save()
      owned = ownedTicket.objects.create(item=aitem, ticketid=(b'\x00\x04'+ os.urandom(6)).hex(), owner=ds)
      owned.save()
   res = {"transaction_results": {"transaction_result":[{"transaction_id":1,"title_id":aitem.title.tid,"ticket_id":int(owned.ticketid, base=16),"post_balance":{"amount":str(ds.balance)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance)},"integrated_account":True}]}}
   return JsonResponse(res)

@csrf_exempt
def tax_location(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   # Match the working forks exactly: the console validates the tax-location
   # record id against its own table, so an invented id (e.g. 55000) or extra
   # fields can make it reject the location and abort before prepurchase_info.
   res = {"tax_location": {"state": "United States", "state_code": ds.country, "id": 71647}}
   return JsonResponse(res)

@csrf_exempt
def redeem_title(request, country, tid):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   try:
      title = Title.objects.get(id=resolve_title_pk(tid))
   except:
      return JsonResponse({"error": True})
   try:
      card = redeemableCard.objects.get(code=request.POST.get("card_number"))
   except:
      return JsonResponse({"error": {"code": "6561", "message": "This code is incorrect.\nPlease check up your code and try again."}})
   if card.used:
      return JsonResponse({"error": {"code": "3101", "message": "This code is already used.\nSorry!"}}, status=400)
   if card.content != title.tid:
      return JsonResponse({"error": {"code": "9468", "message": "Invalid title ID.\nPlease check up your code and try again."}}, status=400)
   card.used = True
   card.save()
   tikid = (b'\x00\x04'+ os.urandom(6)).hex()
   owned = ownedTitle.objects.create(title=title, version=title.version, ticketid=tikid, owner=ds)
   owned.save()
   res = {"transaction_result":{"transaction_id":1,"title_id":title.tid,"ticket_id":int(tikid, base=16),"post_balance":{"amount":str(ds.balance)+",00 Credit","currency":"CREDIT","raw_value":str(ds.balance)},"business_type":"NCL_DIST","integrated_account":True}}
   return JsonResponse(res)


#Todo make the date not be a static value
@csrf_exempt
def transactions(request):
    try:
        ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
    except:
        return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)

    ownedtitles = ownedTitle.objects.filter(owner=ds)

    transactions = []
    index = 1 
    for transaction in ownedtitles:
        transactions.append({
            "date": "14.04.2024",
            "type": "Title Download",
            "description": transaction.title.name,
            "transaction_amount": {
                "amount": "0,00",
                "currency": "EUR",
                "raw_value": "0"
            },
            "balance": {
                "amount": "0,00",
                "currency": "EUR",
                "raw_value": "0"
            },
            "title": {},
            "receipt": False,
            "index": index, 
            "id": transaction.title.id
        })
        index += 1  

    res = {
        "transactions": {
            "transaction": transactions,
            "length": len(transactions),
            "offset": 0,
            "total": len(transactions)
        }
    }

    return JsonResponse(res)

@csrf_exempt
def shared_titles(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
   except:
      return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)
   ownedtitles = homebrew_owned(ds)
   wishlisted = []
   for title in ownedtitles:
      wishlisted.append({"platform": {"name": title.title.platform.name, "id": title.title.platform.id, "device": "CTR", "category": title.title.genre.id}, "publisher": {"name": title.title.publisher.publisher_name, "id": title.title.publisher.id}, "display_genre": title.title.genre.name, "release_date_on_eshop": str(title.title.date), "release_date_on_original": str(title.title.date), "retail_sales": title.title.retail_sales, "eshop_sales": True, "in_app_purchase": title.title.in_app_purchase, "name": title.title.name, "id": title.title.id, "icon_url": title.title.icon_url, "banner_url": title.title.banner_url})
   res = {"owned_titles":{"owned_title":wishlisted,"total":len(wishlisted)}}
   return JsonResponse(res)

@csrf_exempt
def id_pair(request):
   return JsonResponse({"error": {"code": "6569", "message": "Due to technical limitations,\nthis functionnality is not available."}}, status=401)

@csrf_exempt
def public_status(request, country):
   if request.GET.get("ns_uid") == None:
      return JsonResponse({"error": True})
   try:
      title = Title.objects.get(id=resolve_title_pk(request.GET.get("ns_uid")))
   except:
      return JsonResponse({"error": {"code": "5546", "message": "Title not found."}}, status=400)
   if title.public:
      type = "PUBLIC"
   else:
      type = "PRIVATE"
   res = {"title_public_status":{"public_status":type,"type":"T","ns_uid":title_content_id(title.id),"title_id":title.tid}}
   return JsonResponse(res)

@csrf_exempt
def votable_titles(request):
    try:
        ds = Client3DS.objects.get(consoleid=request.session["deviceid"])
    except Client3DS.DoesNotExist:
        return JsonResponse({"error": {"code": "3010","message": "The connection to the server has\ntimed out due to user inactivity.\n\nPlease restart Nintendo eShop\nand try again."}}, status=400)

    owned_titles = ownedTitle.objects.filter(owner=ds)

    transactions = []
    index = 1 
    for owned_title in owned_titles:
        t = owned_title.title
        region_initial = (ds.region or "US").upper()[:2]
        transactions.append({
            "title": {
                "platform": {
                    "name": t.platform.name if t.platform else None,
                    "id": t.platform.id if t.platform else None,
                    "device": "CTR",
                    "category": 8
                },
                "publisher": {
                    "name": t.publisher.publisher_name if t.publisher else None,
                    "id": t.publisher.id if t.publisher else None
                },
                "rating_info": {
                    "rating_system": {
                        "name": None,
                        "id": None
                    },
                    "rating": {
                        "icons": {
                            "icon": [
                                {"url": None, "type": "normal"},
                                {"url": None, "type": "small"}
                            ]
                        },
                        "name": None,
                        "age": None,
                        "id": None
                    }
                },
                "release_date_on_eshop": str(t.date),
                "release_date_on_retail": str(t.date),
                "retail_sales": t.retail_sales,
                "eshop_sales": t.is_not_downloadable,
                "in_app_purchase": t.in_app_purchase,
                "name": "• " + region_initial + " • " + "\n" + t.name,
                "id": t.id,
                "icon_url": t.icon_url,
                "banner_url": t.banner_url
            },
            "index": index
        })
        index += 1  

    res = {
        "contents": {
            "content": transactions,
            "length": len(transactions),
            "offset": 0,
            "total": len(transactions)
        }
    }

    return JsonResponse(res)
    
# Rate-this-title: one vote per console per title; voting again replaces it.
@csrf_exempt
def vote(request):
    if request.method == 'POST':
        try:
            required_params = ['id', 'age', 'gender', 'q3', 'q4', 'q5']
            for param in required_params:
                if param not in request.POST:
                    return JsonResponse({"error": {"code": "400", "message": f"Missing required parameter: {param}"}}, status=400)

            ds = Client3DS.objects.get(consoleid=request.session.get("deviceid"))
        except Client3DS.DoesNotExist:
            return JsonResponse({"error": {"code": "3010", "message": "The connection to the server has timed out due to user inactivity. Please restart Nintendo eShop and try again."}}, status=400)
        
        try:
            q4 = request.POST['q4'].lower() == 'true'
            q5 = request.POST['q5'].lower() == 'true'
            try:
                voted_title = Title.objects.get(id=request.POST['id'])
            except (Title.DoesNotExist, ValueError):
                return JsonResponse({"error": {"code": "5668", "message": "Title does not exists."}}, status=400)

            stars = int(float(request.POST['q3']))
            if stars < 1:
                stars = 1
            if stars > 5:
                stars = 5

            Vote.objects.update_or_create(
                client=ds,
                voted_title=voted_title,
                defaults={
                    "age": int(request.POST['age']),
                    "gender": request.POST['gender'][:10],
                    "q3": str(stars),
                    "q4": q4,
                    "q5": q5,
                },
            )
        except Exception as e:
            return JsonResponse({"error": {"code": "500", "message": "Internal Server Error", "details": str(e)}}, status=500)

        return JsonResponse({}, status=200)
    else:
        return JsonResponse({"error": {"code": "405", "message": "Method Not Allowed"}}, status=405)

@csrf_exempt
def vote_delete(request):
    if request.method != 'POST':
        return JsonResponse({"error": {"code": "405", "message": "Method Not Allowed"}}, status=405)
    try:
        ds = Client3DS.objects.get(consoleid=request.session.get("deviceid") or request.POST.get("device_id"))
    except Client3DS.DoesNotExist:
        return JsonResponse({"error": {"code": "3010", "message": "The connection to the server has timed out due to user inactivity. Please restart Nintendo eShop and try again."}}, status=400)
    title_id = request.POST.get("id") or request.POST.get("title_id")
    qs = Vote.objects.filter(client=ds)
    if title_id:
        try:
            qs = qs.filter(voted_title_id=int(title_id))
        except (TypeError, ValueError):
            pass
    qs.delete()
    return JsonResponse({}, status=200)

@csrf_exempt
def votes(request):
    try:
        ds = Client3DS.objects.get(consoleid=request.session.get("deviceid") or request.POST.get("device_id"))
    except Client3DS.DoesNotExist:
        return JsonResponse({"error": {"code": "3010", "message": "The connection to the server has timed out due to user inactivity. Please restart Nintendo eShop and try again."}}, status=400)

    my_votes = Vote.objects.filter(client=ds).select_related("voted_title")
    content = []
    index = 1
    for v in my_votes:
        content.append({
            "title": {
                "id": v.voted_title_id,
                "name": v.voted_title.name if v.voted_title else None,
                "icon_url": v.voted_title.icon_url if v.voted_title else None,
            },
            "age": v.age,
            "gender": v.gender,
            "q3": v.q3,
            "q4": v.q4,
            "q5": v.q5,
            "index": index
        })
        index += 1
    return JsonResponse({"contents": {"content": content, "length": len(content), "offset": 0, "total": len(content)}})

@csrf_exempt
def current_raw(request):
   try:
      ds = Client3DS.objects.get(consoleid=request.POST.get("device_id"))
   except:
      #If it does not work, placeholder. This is due to chunkencoding. Fuck it :(
      return HttpResponse(str(0))
   return HttpResponse(str(ds.balance))
