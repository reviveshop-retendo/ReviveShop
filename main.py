'''
SOAP Server
Made by Let's Shop! 2024
'''
print("ReviveShop Server - SOAP XML Services\n\nMade for the 3DS/Wii U eShop revival")
print("----------------------------------")

from flask import Flask
import ecs, ias, cas, cdn, assetcdn, nus, npns, npdl, nppl, retendo, nasc
import notifier_srv

app = Flask(__name__)
app.register_blueprint(ecs.ecs)
app.register_blueprint(ias.ias)
app.register_blueprint(cas.cas)
app.register_blueprint(cdn.ccs)
app.register_blueprint(assetcdn.cdn)
app.register_blueprint(nus.nus)
app.register_blueprint(npns.npns)
app.register_blueprint(npdl.npdl)
app.register_blueprint(nppl.nppl)
app.register_blueprint(retendo.retendo)
app.register_blueprint(nasc.nasc)

notifier_srv.start()

print("READY!")
