# import dependencies
import os
import json
import struct
import numpy as np
import datetime as dt
from flask import Flask, Response, request, redirect, url_for, escape, jsonify, make_response
from flask_mongoengine import MongoEngine
from itertools import chain

app = Flask(__name__)
TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"

dev_euis = ['78AF580300000485','78AF580300000506']

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
	gps_speed = db.FloatField()
	gps_course = db.IntField()
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
	tx_pow = db.IntField()
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

#some functions for the freeboard interface
@app.route('/freeboard/devices',methods=['GET'])
def freeboard_devices():
	query = request.args
	if 'dev' in query:
		for i, dev in enumerate(dev_euis):
			if dev == query['dev']:
				return json.dumps(latest_values[i],indent=4)
	return json.dumps({})

@app.route('/freeboard/dbmonitor',methods=['GET'])
def freeboard_db():
	db_state = {}
	db_state.update({"Total entries":DataPoint.objects().count()})
	track_array = []
	for i in range (0,31):
		track_array.append(DataPoint.objects(track_ID=i).count())
	db_state.update({"Tracks":track_array})
	return json.dumps(db_state,indent=4)

#output JSON
@app.route('/json', methods=['GET'])
def print_json():
	query = request.args
	if 'track' in query:
		response = DataPoint.objects(track_ID=int(query['track'])).to_json()
	else:
		response = DataPoint.objects().to_json()

	return Response(response,mimetype='application/json',
		headers={'Content-Disposition':'attachment;filename=database.json'})

#querying the database and giving back a JSON file
@app.route('/query', methods=['GET'])
def db_query():
	query = request.args
	track = 0
	hdop = 500
	start = dt.datetime.now() - dt.timedelta(days=365)
	end = dt.datetime.now()
	device = '78AF580300000485'

	#enable for deleting objects. Attention, deletes parts of the database! Should be left disabled.
	if 'delete' in query and 'start' in query and 'end' in query:
		end = dt.datetime.strptime(query['end'], TIME_FORMAT)
		start = dt.datetime.strptime(query['start'], TIME_FORMAT)
		#DataPoint.objects(track_ID=query['delete'],timestamp__lt=end,timestamp__gt=start).delete()
		#return 'objects deleted'
		return 'delete feature disabled for security reasons'

	if 'deltrack' in query:
		DataPoint.objects(track_ID=int(query['deltrack'])).delete()
		return 'track deleted'

	if 'delpoint' in query:
		#to do: debug this
		DataPoint.objects(timestamp=query['delpoint']).delete()
		return "ok"

	if 'track' in query:
		track = int(query['track'])

	if 'start' in query:
		start = dt.datetime.strptime(query['start'], TIME_FORMAT)

	if 'end' in query:
		end = dt.datetime.strptime(query['end'], TIME_FORMAT)

	if 'device' in query:
		device = query['device']

	if 'hdop' in query:
		hdop = query['hdop']

	if 'sf' in query and 'txpow' in query:
		sf = int(query['sf'])
		txpow = int(query['txpow'])
		datapoints = DataPoint.objects(track_ID=track,devEUI=device,timestamp__lt=end,timestamp__gt=start,sp_fact=sf,tx_pow=txpow,gps_hdop__lt=hdop).to_json()
		return datapoints
	else:
		datapoints = DataPoint.objects(track_ID=track,devEUI=device,timestamp__lt=end,timestamp__gt=start,gps_hdop__lt=hdop).to_json()
		return datapoints


# Swisscom LPN listener to POST from actility
@app.route('/sc_lpn', methods=['POST'])
def sc_lpn():
	"""
	This methods handle every messages sent by the LORA sensors
	:return:
	"""

	latest_esp = esp_buff

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

	tuino_list = ['78AF580300000485','78AF580300000506']
	direxio_list = ['78AF58060000006D']

	#Parse JSON from ThingPark
	size_payload=20
	payload = j['DevEUI_uplink']['payload_hex']
	payload_int = int(j['DevEUI_uplink']['payload_hex'],16)
	bytes = bytearray.fromhex(payload)
	r_deveui = j['DevEUI_uplink']['DevEUI']
	r_time = j['DevEUI_uplink']['Time']
	#Directive %z not supported in python 2! 
	#Todo: Use Python 3 and remove fixed timezone
	r_timestamp = dt.datetime.strptime(r_time,"%Y-%m-%dT%H:%M:%S.%f+02:00")
	r_sp_fact = j['DevEUI_uplink']['SpFact']
	r_channel = j['DevEUI_uplink']['Channel']
	r_band = j['DevEUI_uplink']['SubBand']

	g_id = []
	g_rssi = []
	g_snr = []
	g_esp = []

	#parse array of multiple gateways
	for item in j['DevEUI_uplink']['Lrrs']['Lrr']:
		g_id.append(item['Lrrid'])
		g_rssi.append(item['LrrRSSI'])
		g_snr.append(item['LrrSNR'])
		g_esp.append(item['LrrESP'])
		if item['Lrrid']=='0B030153':
			latest_esp = item['LrrESP']

	if(r_deveui in tuino_list):
		r_devtype = "tuino-v3"
		#r_lat = struct.unpack('<l', bytes.fromhex(payload[10:18]))[0] /10000000.0
		#r_lon = struct.unpack('<l', bytes.fromhex(payload[18:26]))[0] /10000000.0
		#r_temp = struct.unpack('<i', bytes.fromhex(payload[2:6]))[0] /100.0
		#r_hum = struct.unpack('<i', bytes.fromhex(payload[6:10]))[0] /100.0
		r_lat = ((payload_int & 0x0000000000ffffffff0000000000000000000000) >> bitshift(size_payload,8))/10000000.0
		r_lon = ((payload_int & 0x000000000000000000ffffffff00000000000000) >> bitshift(size_payload,12))/10000000.0
		r_temp = ((payload_int & 0x00ffff0000000000000000000000000000000000) >> bitshift(size_payload,2))/100.0
		r_hum = ((payload_int & 0x000000ffff000000000000000000000000000000) >> bitshift(size_payload,4))/100.0
		r_sat = ((payload_int & 0x00000000000000000000000000ff000000000000) >> bitshift(size_payload,13))
		r_hdop = ((payload_int & 0x0000000000000000000000000000ffff00000000) >> bitshift(size_payload,15))
		r_speed = ((payload_int & 0x00000000000000000000000000000000ff000000) >> bitshift(size_payload,16)) / 2
		r_course = ((payload_int & 0x0000000000000000000000000000000000ff0000) >> bitshift(size_payload,17)) * 2
		r_trk = ((payload_int & 0x000000000000000000000000000000000000ff00) >> bitshift(size_payload,18))
		r_txpow= ((payload_int & 0x00000000000000000000000000000000000000ff) >> bitshift(size_payload,19))

		#update latest values
		for i, dev in enumerate(dev_euis):
			if r_deveui == dev:
				latest_values[i].update({"devEUI":r_deveui,"ESP 0B030153":latest_esp,"Position":(r_lat,r_lon),"Humidity":r_hum,"Temperature":r_temp,
					"Time":r_time,"Track":r_trk,"TXpow":r_txpow,"SF":r_sp_fact,"HDOP":r_hdop})

		print('TXpow: ' + str(r_txpow))
		print('SF: '+ str(r_sp_fact))
		print('Lat: ' + str(r_lat))
		print('Lon: ' + str(r_lon))
		print('Temp: ' + str(r_temp))
		print('Hum: ' + str(r_hum))
		print('Satellites: ' + str(r_sat))
		print('HDOP: ' + str(r_hdop))
		print('Track: ' + str(r_trk))
		print('Speed: ' + str(r_speed))
		print('Course: ' + str(r_course))

	elif (r_deveui in direxio_list):
		r_devtype = "direxio-v1"
		r_lat = struct.unpack('<f', bytes.fromhex(payload[10:18]))[0]
		r_lon = struct.unpack('<f', bytes.fromhex(payload[20:28]))[0]
		r_temp = -99
		r_hum = -99
		r_sat = 0
		r_hdop = 20
		r_speed = 0
		r_course = 0
		r_txpow = 0
		r_trk = 99 #test track number

		print(r_lat)
		print(r_lon)
	else:
		return "device type not recognised"

	#to check if gps coords are available
	gpfix = 1
	
	#TODO: check if gpscord = 0.0
	
	if gpfix:
		datapoint = DataPoint(devEUI=r_deveui, time= r_time, timestamp = r_timestamp, deviceType = r_devtype, gps_sat = r_sat, 
			gps_hdop = r_hdop, track_ID = r_trk, gps_lat=r_lat, gps_lon=r_lon,
			gps_speed = r_speed, gps_course = r_course, temperature=r_temp, humidity=r_hum, sp_fact=r_sp_fact, 
			channel=r_channel, sub_band=r_band, gateway_id=g_id, gateway_rssi=g_rssi, gateway_snr=g_snr, 
			gateway_esp=g_esp, tx_pow = r_txpow)
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
	R = 40030173
	if latlon == 'lon':
		return (meter/(np.cos(np.radians(deglat))*R))*360.0
	elif latlon == 'lat':
		return (meter/R)*360.0
	else:
		print('return 0')
		return 0

def coord_to_m(latlon, meter, deglat):
	R = 40030173
	if latlon == 'lon':
		return (meter/360.0)*(np.cos(np.radians(deglat))*R)
	elif latlon == 'lat':
		return (meter/360.0)*R
	else:
		return 0

# start the app
if __name__ == '__main__':
	global latest_values 
	global esp_buff
	esp_buff = 0
	latest_values = [{},{}]
	app.run(host='0.0.0.0', port=port)
