# import dependencies
import os
import json
import struct
import numpy as np
import datetime as dt
from flask import Flask, request, redirect, url_for, escape, jsonify, make_response
from flask_mongoengine import MongoEngine
from itertools import chain

app = Flask(__name__)
TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"

# check if running in the cloud and set MongoDB settings accordingly
if 'VCAP_SERVICES' in os.environ:
	vcap_services = json.loads(os.environ['VCAP_SERVICES'])
	mongo_credentials = vcap_services['mongodb'][0]['credentials']
	mongo_uri = mongo_credentials['uri']
else:
	mongo_uri = 'mongodb://localhost/db'

app.config['MONGODB_SETTINGS'] = [
	{
		'host': mongo_uri,
		'alias': 'gps-points'
	},
	{
		'host': mongo_uri,
		'alias': 'gateways'
	}
]

# bootstrap our app
db = MongoEngine(app)

class DataPoint(db.Document):
	devEUI = db.StringField(required=True)
	deviceType = db.StringField()
	track_ID = db.IntField() #test purpose to seperate into different pieces
	timestamp = db.DateTimeField()
	time = db.StringField()
	gps_lat = db.FloatField()
	gps_lon = db.FloatField()
	gps_sat = db.IntField()
	gps_hdop = db.FloatField()
	temperature = db.FloatField()
	humidity = db.FloatField()
	sp_fact = db.IntField()
	channel = db.StringField()
	sub_band = db.StringField()
	sub_band = db.StringField()
	gateway_id = db.ListField(db.StringField())
	gateway_rssi = db.ListField(db.FloatField())
	gateway_snr = db.ListField(db.FloatField())
	gateway_esp = db.ListField(db.FloatField())
	#work in a specific mongoDB collection:
	meta = {'db_alias': 'gps-points'}

class Gateways(db.Document):
	gateway_id = db.StringField(requred=True)
	gateway_lat = db.FloatField()
	gateway_lon = db.FloatField()
	meta = {'db_alias': 'gateways'}

# set the port dynamically with a default of 3000 for local development
port = int(os.getenv('PORT', '3000'))

# functions for decoding payload
def bitshift (payload,lastbyte):
	return 8*(payload-lastbyte-1)

# our base route which just returns a string
@app.route('/')
def hello_world():
	return "<b>Congratulations! Welcome to Spaghetti v1!</b>"

#output a csv file
#To do: debug (correct nested list import)
@app.route('/csv/<track>')
def print_csv(track):

	#make flattened list for export
	response = chain.from_iterable(make_response(DataPoint.objects(track_ID=track)))

	print(response) 
	cd = 'attachment; filename = export.csv'
	response.headers['Content-Disposition'] = cd
	response.mimetype='text/csv'
	return response

#querying the database and giving back a JSON file
@app.route('/query', methods=['GET'])
def db_query():
	query = request.args
	print('args received')
	print(query)

	track = 0
	start = dt.datetime.now() - dt.timedelta(days=365)
	end = dt.datetime.now()

	#enable for deleting objects. Attention, deletes parts of the database! Should be left disabled.
	if 'delete' in query:
		#DataPoint.objects(gps_lat=0.0).delete()
		#return 'objectes deleted'
		return 'delete feature disabled for security reasons'

	if 'track' in query:
		track = int(query['track'])

	if 'start' in query:
		start = dt.datetime.strptime(query['start'], TIME_FORMAT)
	

	if 'end' in query:
		end = dt.datetime.strptime(query['end'], TIME_FORMAT)

	datapoints = DataPoint.objects(track_ID=track,timestamp__lt=end,timestamp__gt=start).to_json()
	return datapoints


# Swisscom LPN listener to POST from actility
@app.route('/sc_lpn', methods=['POST'])
def sc_lpn():
	"""
	This methods handle every messages sent by the LORA sensors
	:return:
	"""
	print("Data received from ThingPark...")
	j = []
	try:
		j = request.json
	except:
		print("Unable to read information or json from sensor...")
	
	#print("Args received:")
	#print(args_received)
	print("JSON received:")
	print(j)

	tuino_list = ['78AF580300000485']
	direxio_list = ['78AF58060000006D']

	#Parse JSON from ThingPark
	size_payload=17
	payload = j['DevEUI_uplink']['payload_hex']
	payload_int = int(j['DevEUI_uplink']['payload_hex'],16)
	bytes = bytearray.fromhex(payload)
	r_deveui = j['DevEUI_uplink']['DevEUI']
	r_time = j['DevEUI_uplink']['Time']
	r_timestamp = dt.datetime.strptime(j['DevEUI_uplink']['Time'],"%Y-%m-%dT%H:%M:%S.%f+01:00")
	r_sp_fact = j['DevEUI_uplink']['SpFact']
	r_channel = j['DevEUI_uplink']['Channel']
	r_band = j['DevEUI_uplink']['SubBand']

	g_id = []
	g_rssi = []
	g_snr = []
	g_esp = []

	#parse array of multiple gateways
	for index, item in enumerate(j['DevEUI_uplink']['Lrrs']['Lrr']):
		g_id.append(item['Lrrid'])
		g_rssi.append(item['LrrRSSI'])
		g_snr.append(item['LrrSNR'])
		g_esp.append(item['LrrESP'])

	if(r_deveui in tuino_list):
		r_devtype = "tuino-v3"
		#r_lat = struct.unpack('<l', bytes.fromhex(payload[10:18]))[0] /10000000.0
		#r_lon = struct.unpack('<l', bytes.fromhex(payload[18:26]))[0] /10000000.0
		#r_temp = struct.unpack('<i', bytes.fromhex(payload[2:6]))[0] /100.0
		#r_hum = struct.unpack('<i', bytes.fromhex(payload[6:10]))[0] /100.0
		r_lat = ((payload_int & 0x0000000000ffffffff0000000000000000) >> bitshift(size_payload,8))/10000000.0
		r_lon = ((payload_int & 0x000000000000000000ffffffff00000000) >> bitshift(size_payload,12))/10000000.0
		r_temp = ((payload_int & 0x00ffff0000000000000000000000000000) >> bitshift(size_payload,2))/100.0
		r_hum = ((payload_int & 0x000000ffff000000000000000000000000) >> bitshift(size_payload,4))/100.0
		r_sat = ((payload_int & 0x00000000000000000000000000ff000000) >> bitshift(size_payload,13))
		r_hdop = ((payload_int & 0x0000000000000000000000000000ffff00) >> bitshift(size_payload,15))
		r_trk = ((payload_int & 0x00000000000000000000000000000000ff) >> bitshift(size_payload,16))

		print('Lat: ' + str(r_lat))
		print('Lon: ' + str(r_lon))
		print('Temp: ' + str(r_temp))
		print('Hum: ' + str(r_hum))
		print('Satellites: ' + str(r_sat))
		print('HDOP: ' + str(r_hdop))
		print('Track: ' + str(r_trk))


	elif (r_deveui in direxio_list):
		r_devtype = "direxio-v1"
		r_lat = struct.unpack('<f', bytes.fromhex(payload[10:18]))[0]
		r_lon = struct.unpack('<f', bytes.fromhex(payload[20:28]))[0]
		r_temp = -99
		r_hum = -99
		r_sat = 0
		r_hdop = 20
		r_trk = 9 #test track number

		print(r_lat)
		print(r_lon)
	else:
		return "device type not recognised"

	#to check if gps coords are available
	gpfix = 1
	
	#TODO: check if gpscord = 0.0
	
	if gpfix:
		datapoint = DataPoint(devEUI=r_deveui, time= r_time, deviceType = r_devtype, gps_sat = r_sat, gps_hdop = r_hdop, track_ID = r_trk, timestamp=r_timestamp, gps_lat=r_lat, gps_lon=r_lon,
			temperature=r_temp, humidity=r_hum, sp_fact=r_sp_fact, channel=r_channel, sub_band=r_band, 
			gateway_id=g_id, gateway_rssi=g_rssi, gateway_snr=g_snr, gateway_esp=g_esp)
		datapoint.save()
		return 'Datapoint DevEUI %s saved' %(r_deveui)
	else:
		print("no gps coords, point not saved")
		return 'Datapoint DevEUI %s not saved because no gps coords available' %(r_deveui)

# post and get gateways to the gateway db collection
@app.route('/gateways', methods=['POST','GET'])
def gateway_data():
	if  request.method == 'POST':
		#print('gateway post method detected')
		#print(request.args)
		gtw_dict = request.args

		#check if the request is valid and contains all the necessary fields
		if ('id' in gtw_dict and 'lat' in gtw_dict and 'lon' in gtw_dict):
			#check if it is delete request
			if('action' in gtw_dict and gtw_dict['action']=='delete'):
				print("it's a delete request")
				#Gateways.objects(gateway_id=gtw_dict['id']).delete()
				#return 'gateway deleted'
				return "delete function disabled for security reasons"

			#print(len(Gateways.objects(gateway_id=gtw_dict['id'])))
			#test if gateway already exists
			if (len(Gateways.objects(gateway_id=gtw_dict['id']))) > 0:
				return 'gateway already exists'
			else:
				gateway = Gateways(gateway_id=gtw_dict['id'], gateway_lat=gtw_dict['lat'], gateway_lon=gtw_dict['lon'])
				gateway.save()
				return 'gateway saved'
		else:
			abort (400) #bad request
	else: 
		inp = request.args
		if('lat' in inp and 'lon' in inp and 'radius' in inp):
			lat1 = (float(inp['lat']) - m_to_coord('lat',float(inp['radius']),float(inp['lat'])))
			lat2 = (float(inp['lat']) + m_to_coord('lat',float(inp['radius']),float(inp['lat'])))
			lon1 = (float(inp['lon']) - m_to_coord('lon',float(inp['radius']),float(inp['lat'])))
			lon2 = (float(inp['lon']) + m_to_coord('lon',float(inp['radius']),float(inp['lat'])))
			gateways = Gateways.objects(gateway_lat__gt=lat1,gateway_lat__lt=lat2,gateway_lon__gt=lon1,gateway_lon__lt=lon2).to_json()
		elif('eui' in inp):
			gateways = Gateways.objects(gateway_id=inp['eui'])
		else:
			gateways = Gateways.objects.to_json()
		
		return gateways

# endpoint to return all kittens
@app.route('/db')
def get_data():
	datapoints = DataPoint.objects.to_json()
	return datapoints


def m_to_coord(latlon, meter, deglat):
	R = 40000000
	if latlon == 'lon':
		return (meter/(np.cos(np.radians(deglat))*R))*360.0
	elif latlon == 'lat':
		return (meter/R)*360.0
	else:
		print('return 0')
		return 0

def coord_to_m(latlon, meter, deglat):
	R = 40000000
	if latlon == 'lon':
		return (meter/360.0)*(np.cos(np.radians(deglat))*R)
	elif latlon == 'lat':
		return (meter/360.0)*R
	else:
		return 0
# start the app
if __name__ == '__main__':
	#print(m_to_coord('lat',10000,46.518718))
	#print(m_to_coord('lon',10000,46.518718))
	app.run(host='0.0.0.0', port=port)