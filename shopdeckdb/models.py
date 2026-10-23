from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import date as _date

# Create your models here.

# Nintendo eShop "content IDs" are 14-digit numbers beginning with 5. Our DB
# uses small integer pks, so we map pk <-> content id for ESHOP:// deep links
# (the 3DS camera rejects anything that isn't "ESHOP://5...").
CONTENT_ID_BASE = 50010000000000


def title_content_id(pk):
    return CONTENT_ID_BASE + int(pk)


def resolve_title_pk(value):
    """Accept either a real pk or a content id and return the pk."""
    n = int(value)
    if n >= CONTENT_ID_BASE:
        return n - CONTENT_ID_BASE
    return n

class Client3DS(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    consoleid = models.CharField(max_length=12, null=False)
    devicecert_consoleid = models.CharField(max_length=8, null=True, blank=True)
    devicetoken = models.CharField(max_length=21, null=False)
    is_terminated = models.BooleanField(default=False)
    balance = models.IntegerField(default=0)
    language = models.CharField(max_length=3, null=False)
    region = models.CharField(max_length=3, null=False)
    country = models.CharField(max_length=3, null=False)
    uniquekey = models.CharField(max_length=21, null=False)
    def __str__(self):
        return "3DS "+self.consoleid

class User(AbstractUser):
    linked_ds = models.ForeignKey(Client3DS, null=True, on_delete=models.CASCADE)

class customTitleID(models.Model):
    tid = models.CharField(max_length=18, null=False)
    related_to = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    def __str__(self):
        return "Title "+self.tid+" for user "+self.related_to.consoleid

class publisher(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    publisher_name = models.CharField(max_length=20)
    def __str__(self):
        return self.publisher_name

class category(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    index = models.IntegerField(default=0, null=False)
    name = models.CharField(max_length=25)
    standard = models.BooleanField(default=False)
    icon_url = models.TextField(null=False)
    banner_url = models.TextField(null=False)
    new = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    def __str__(self):
        return "Category "+self.name

class genre(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    name = models.CharField(max_length=50)
    def __str__(self):
        return self.name

class platform(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    name = models.CharField(max_length=50)
    def __str__(self):
        return self.name

class Title(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    tid = models.CharField(max_length=16, null=False)
    name = models.CharField(max_length=25)
    desc = models.TextField(default="", null=False)
    thumbnail_url = models.TextField(null=False)
    icon_url = models.TextField(null=False)
    banner_url = models.TextField(null=False)
    publisher = models.ForeignKey(publisher, on_delete=models.CASCADE)
    date = models.DateField(default=_date.today, null=False)
    product_code = models.CharField(max_length=30)
    new = models.BooleanField(default=True)
    public = models.BooleanField(default=True)
    category = models.ForeignKey(category, on_delete=models.DO_NOTHING, null=True, blank=True)
    genre = models.ForeignKey(genre, null=False, on_delete=models.CASCADE)
    in_app_purchase = models.BooleanField(default=False)
    platform = models.ForeignKey(platform, null=False, on_delete=models.CASCADE)
    price = models.IntegerField(default=0, null=False)
    version = models.IntegerField(default=1024)
    is_not_downloadable = models.BooleanField(default=False)
    retail_sales = models.BooleanField(default=False)
    size = models.IntegerField(default=0)
    ticket_available = models.BooleanField(default=True)
    demo = models.ForeignKey("Title", on_delete=models.DO_NOTHING, null=True, blank=True)
    top_image_url = models.CharField(max_length=600, blank=True, default="")
    screenshot_upper_url = models.TextField(blank=True, default="")
    screenshot_lower_url = models.TextField(blank=True, default="")
    screenshot_merged_url = models.TextField(blank=True, default="")
    def __str__(self):
        return self.name+" by "+self.publisher.publisher_name+" published on "+str(self.date)  

class item(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    title = models.ForeignKey(Title, null=False, on_delete=models.CASCADE)
    itemcode = models.CharField(max_length=16)
    price = models.IntegerField(default=0, null=False)
    limit = models.IntegerField(default=1, null=False)
    def __str__(self):
        return "Item "+str(self.id)+" for "+self.title.name

class movie(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    name = models.CharField(max_length=25)
    thumbnail_url = models.TextField(null=False)
    banner_url = models.TextField(null=False)
    is_3d = models.BooleanField(default=False)
    moflex_url = models.TextField(null=False)
    time_in_sec = models.IntegerField(null=False)
    date = models.DateField(default=_date.today, null=False)
    category = models.ForeignKey(category, on_delete=models.DO_NOTHING, null=True, blank=True)
    new = models.BooleanField(default=True, null=False)
    price = models.IntegerField(default=0, null=False)
    public = models.BooleanField(default=True, null=False)
    description = models.TextField(null=True, blank=True)
    def __str__(self):
        return self.name

class ownedMovie(models.Model):
    movie = models.ForeignKey(movie, null=False, on_delete=models.CASCADE)
    ticketid = models.CharField(max_length=16, null=False)
    owner = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    def __str__(self):
        return "Movie "+self.movie.name+" owned by "+self.owner.consoleid

class ownedTitle(models.Model):
    title = models.ForeignKey(Title, null=False, on_delete=models.CASCADE)
    ticketid = models.CharField(max_length=16, null=False)
    version = models.IntegerField(null=False)
    owner = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    def __str__(self):
        return "Title "+self.title.name+" owned by "+self.owner.consoleid

class ownedTicket(models.Model):
    item = models.ForeignKey(item, null=False, on_delete=models.CASCADE)
    ticketid = models.CharField(max_length=16, null=False)
    owner = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    def __str__(self):
        return "Ticket "+self.item.itemcode+" owned by "+self.owner.consoleid

class wishlistedTitle(models.Model):
    title = models.ForeignKey(Title, null=False, on_delete=models.CASCADE)
    owner = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    def __str__(self):
        return "Wishlisted title "+self.title.name+" wanted by "+self.owner.consoleid

class announcement(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    title = models.CharField(max_length=50, null=False)
    content = models.TextField(null=False)
    date = models.DateTimeField(auto_now_add=True, null=False)
    publish_date = models.DateTimeField(null=True, blank=True)
    expire_date = models.DateTimeField(null=True, blank=True)
    is_banner = models.BooleanField(default=False)
    banner_url = models.TextField(null=True, blank=True)
    def __str__(self):
        return "Announcement "+self.title
    @property
    def status(self):
        from django.utils import timezone
        now = timezone.now()
        if self.publish_date and self.publish_date > now:
            return "scheduled"
        if self.expire_date and self.expire_date <= now:
            return "expired"
        return "live"

class motd(models.Model):
    content = models.TextField(null=False)
    order = models.IntegerField(default=0)
    def __str__(self):
        return self.content
    
class redeemableCard(models.Model):
    code = models.CharField(max_length=16, null=False)
    used = models.BooleanField(default=False)
    is_money = models.BooleanField(default=True)
    content = models.CharField(max_length=16, null=False)
    def __str__(self):
        return self.code
    
class searchCategory(models.Model):
    id = models.IntegerField(primary_key=True, blank=True)
    name = models.CharField(max_length=35)
    platform_list = models.TextField(verbose_name="Platform List (seperate each platform by a comma)")
    def __str__(self):
        return self.name

class Vote(models.Model):
    client = models.ForeignKey(Client3DS, on_delete=models.CASCADE)
    voted_title = models.ForeignKey(Title, on_delete=models.CASCADE, null=True)
    age = models.IntegerField()
    gender = models.CharField(max_length=10)
    q3 = models.CharField(max_length=10)
    q4 = models.BooleanField()
    q5 = models.BooleanField()


class RtAccount(models.Model):
    """A ReTendo account (our Nintendo Network ID replacement)."""
    user_id = models.CharField(max_length=32, unique=True)
    email = models.EmailField(blank=True, default="")
    password = models.CharField(max_length=128, blank=True, default="")
    pid = models.BigIntegerField(default=0)
    mii_name = models.CharField(max_length=20, blank=True, default="Player")
    mii_id = models.CharField(max_length=16, blank=True, default="")
    mii_hash = models.CharField(max_length=16, blank=True, default="")
    country = models.CharField(max_length=3, blank=True, default="US")
    language = models.CharField(max_length=3, blank=True, default="en")
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, blank=True, default="M")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user_id


class RtConsoleLink(models.Model):
    account = models.ForeignKey(RtAccount, null=False, on_delete=models.CASCADE)
    console = models.ForeignKey(Client3DS, null=False, on_delete=models.CASCADE)
    linked = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.account.user_id + " <-> " + self.console.consoleid


class RtToken(models.Model):
    account = models.ForeignKey(RtAccount, null=False, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=64, unique=True)
    refresh_token = models.CharField(max_length=64, unique=True)
    service_token = models.CharField(max_length=64, unique=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.access_token


class spotpassMessage(models.Model):
    """A Home Menu SpotPass notification (delivered via the BOSS 'basho0' task)."""
    id = models.IntegerField(primary_key=True, blank=True)
    title = models.CharField(max_length=32, null=False)
    message = models.TextField(null=False)
    image_url = models.TextField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True, null=False)

    def __str__(self):
        return "SpotPass " + self.title
