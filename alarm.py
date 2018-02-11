IS_RASPBERRY = False

import pygame
import sqlite3
import datetime
import threading
from time import sleep
import json
import signal
import sys
import web
import os
import platform
import hashlib

if platform.system() != "Windows":
	import RPi.GPIO

def get_pin_state(pin):
	if platform.system() == "Windows":
		return 1
	else:
		return RPi.GPIO.input(pin)

def setup_pin(pin):
	if platform.system() == "Windows":
		pass
	else:
		RPi.GPIO.setmode(RPi.GPIO.BCM)
		RPi.GPIO.setup(pin, RPi.GPIO.IN, pull_up_down=RPi.GPIO.PUD_DOWN)

urls = ('/', 'AlarmServer')

class AlarmServer:
	def POST(self):
		json_data = json.loads(web.data())
		alarms = json_data['alarms']
		db_remove_alarms()
		web.ctx.globals.alarm_manager.remove_alarms()
		for alarm_data in alarms:
			alarm = Alarm(file_name=web.ctx.globals.file_name, alarm_data=alarm_data, save_to_db=True)
			alarm.activate()
			web.ctx.globals.alarm_manager.add_alarm(alarm)
		if not web.ctx.globals.alarm_manager.is_running:
			web.ctx.globals.alarm_manager.start()
		return self.print_alarms()

	def PUT(self):
		_date_time= datetime.datetime.now() + datetime.timedelta(seconds=1)
		alarm = Alarm(file_name=web.ctx.globals.file_name, date_time=_date_time, save_to_db=False)
		alarm.activate()
		web.ctx.globals.alarm_manager.add_alarm(alarm)
		if not web.ctx.globals.alarm_manager.is_running:
			web.ctx.globals.alarm_manager.start()
		return self.print_alarms()
			
	def GET(self):
		return self.print_alarms()
	
	def print_alarms(self):
		res = 'Registered the following alarms:\n\n'
		for alarm in web.ctx.globals.alarm_manager.alarms:
			res += alarm.get_info()
			res += '\n'
		print res
		return res

class Alarm:
	def __init__(self, file_name="alarm.wav", alarm_type="fixed", date_time=datetime.datetime.now(), duration=1, alarm_data=None, save_to_db = False):
		if alarm_data != None:
			_alarm_type = alarm_data['type']
			_date_time = None
			if _alarm_type == 'fixed':
				dt = alarm_data['datetime'].split(" ")
				date = dt[0].split(".")
				time = dt[1].split(":")
				days = int(date[0])
				months = int(date[1])
				years = int(date[2])
				hours = int(time[0])
				minutes = int(time[1])
				seconds = int(time[2])
				_date_time = datetime.datetime(years, months, days, hours, minutes, seconds)
			else:
				_date_time = datetime.datetime.now()
				time = alarm_data['datetime'].split(":")
				hours = int(time[0])
				minutes = int(time[1])
				seconds = int(time[2])
				_date_time = _date_time.replace(hour=hours, minute=minutes, second=seconds)
			_duration = alarm_data['duration']
			self.initialize(file_name, _alarm_type, _date_time, _duration, save_to_db)
		else:
			self.initialize(file_name, alarm_type, date_time, duration, save_to_db)


	def initialize(self, file_name, alarm_type, date_time, duration, save_to_db):
		self.file_name = file_name
		self.alarm_type = alarm_type
		self.date_time = date_time
		self.duration = duration
		self.end_time = self.compute_endtime()
		self.is_active = False
		self.is_triggered = False
		self.thread = self.AlarmThread(self)
		self.hash = compute_alarm_hash(date_time, alarm_type, duration)

		if save_to_db:
			db_insert_alarm(self.hash, date_time, alarm_type, duration)

	def get_info(self):
		info = 'Alarm options:\nType: {}\nDate-time: {}\nDuration: {}\n'.format(self.alarm_type, self.date_time.ctime(), self.duration)
		return info

	def compute_endtime(self):
		return (self.date_time + datetime.timedelta(seconds = self.duration))

	def activate(self):
		self.is_active = True

	def deactivate(self):
		self.is_active = False

	class AlarmThread(threading.Thread):
		def __init__(self, alarm):
			threading.Thread.__init__(self)
			self.alarm = alarm

		def run(self):
			if self.alarm.is_active:			
				self.alarm.is_triggered = True
				while self.alarm.is_active == True and self.alarm.end_time > datetime.datetime.now() and get_pin_state(gpio_pin) == 1:
					if pygame.mixer.get_init() is None:
						pygame.mixer.init()
						pygame.mixer.music.load(self.alarm.file_name)
					elif pygame.mixer.music.get_busy():
						sleep(0.1)
					else:
						pygame.mixer.music.rewind()
						pygame.mixer.music.play()
				if pygame.mixer.get_init() is not None:
					pygame.mixer.music.stop()
					pygame.mixer.quit()
				self.alarm.is_triggered = False
				if self.alarm.alarm_type == 'repeat':
					self.alarm.date_time = self.alarm.date_time + datetime.timedelta(days = 1)
					self.alarm.end_time = self.alarm.compute_endtime()
				else:
					self.alarm.is_active = False

	def trigger(self):
		if not self.is_triggered:
			self.thread.start()

class AlarmManager:
	def __init__(self):
		self.alarms = []
		self.is_running = False
		self.thread = self.AlarmManagerThread(self)

	def add_alarm(self, alarm):
		self.alarms.append(alarm)

	def remove_alarms(self):
		self.alarms = []

	def start(self):
		if not self.is_running:
			self.is_running = True
			self.thread.start()

	def stop(self):
		self.is_running = False
		for alarm in self.alarms:
			alarm.deactivate()

	class AlarmManagerThread(threading.Thread):
		def __init__(self, alarm_manager):
			threading.Thread.__init__(self)
			self.alarm_manager = alarm_manager
			self.has_alarm_triggered = False

		def run(self):
			while self.alarm_manager.is_running:
				for alarm in self.alarm_manager.alarms:
					if alarm.is_triggered:
						self.has_alarm_triggered = True
						break
					else:
						self.has_alarm_triggered = False

				if not self.has_alarm_triggered:
					deactivated_alarms = [x for x in self.alarm_manager.alarms if x.is_active == False]
					for alarm in deactivated_alarms:
						self.alarm_manager.alarms.remove(alarm)
						db_remove_alarm(alarm.hash)
					for alarm in self.alarm_manager.alarms:
						if not alarm.is_triggered and alarm.is_active:
							if datetime.datetime.now() >= alarm.date_time:
								self.has_alarm_triggered = True
								alarm.trigger()
				sleep(0.1)

def sigint_handler(signal, frame):
	print('\nCtrl+C received. Exiting...')
	alarm_manager.stop()
	webserver.stop()

def add_global_hook():
	g = web.storage({"alarm_manager" : alarm_manager,
					"file_name" : filename})
	def _wrapper(handler):
		web.ctx.globals = g
		return handler()
	return _wrapper

alarm_manager = None
webserver = None
filename = ""
gpio_pin = 4

def db_setup():
	conn = sqlite3.connect("alarms.db")
	c = conn.cursor()
	c.execute('''CREATE TABLE IF NOT EXISTS ALARMS (
				ID BLOB,
				DAY INT,
				MONTH INT,
				YEAR INT,
				HOUR INT,
				MINUTE INT,
				SECOND INT,
				TYPE TEXT,
				DURATION INT
				)''')
	conn.commit()
	conn.close()

def db_remove_alarms():
	conn = sqlite3.connect("alarms.db")
	c = conn.cursor()
	c.execute("DELETE FROM ALARMS")
	conn.commit()
	conn.close()

def db_restore_alarms():
	conn = sqlite3.connect("alarms.db")
	c = conn.cursor()
	c.execute("SELECT * FROM ALARMS")
	rows = c.fetchall()
	conn.close()

	for row in rows:
		day = row[1]
		month = row[2]
		year = row[3]
		hour = row[4]
		minute = row[5]
		second = row[6]
		_type = row[7]
		_duration = row[8]

		_date_time = datetime.datetime(year, month, day, hour, minute, second)
		alarm = Alarm(file_name=filename, date_time=_date_time, alarm_type=_type, duration=_duration, save_to_db=False)
		alarm.activate()
		alarm_manager.add_alarm(alarm)
		
	if not alarm_manager.is_running:
		alarm_manager.start()
	return print_alarms()

def print_alarms():
	res = 'Restored the following alarms:\n\n'
	for alarm in alarm_manager.alarms:
		res += alarm.get_info()
		res += '\n'
	print res
	return res

def db_insert_alarm(hash, date_time, type, duration):
	day = date_time.day
	month = date_time.month
	year = date_time.year
	hour = date_time.hour
	minute = date_time.minute
	second = date_time.second
	conn = sqlite3.connect("alarms.db")
	c = conn.cursor()
	c.execute('''INSERT INTO ALARMS (ID, DAY, MONTH, YEAR, HOUR, MINUTE, SECOND, TYPE, DURATION)
				VALUES ( '{0}', {1}, {2}, {3}, {4}, {5}, {6}, '{7}', {8} )'''.format(hash, day, month, year, hour, minute, second, type, duration))
	conn.commit()
	conn.close()

def db_remove_alarm(hash):
	conn = sqlite3.connect("alarms.db")
	c = conn.cursor()
	c.execute("DELETE FROM ALARMS WHERE ID = '{0}'".format(hash))
	conn.commit()
	conn.close()

def compute_alarm_hash(date_time, alarm_type, duration):
	day = date_time.day
	month = date_time.month
	year = date_time.year
	hour = date_time.hour
	minute = date_time.minute
	second = date_time.second

	hash_string = b"{0}{1}{2}{3}{4}{5}{6}{7}".format(day, month, year, hour, minute, second, alarm_type, duration)
	return hashlib.md5(hash_string).hexdigest()

if __name__ == "__main__":
	db_setup()
	setup_pin(gpio_pin)
	filename = os.path.dirname(os.path.realpath(__file__)) + "/alarm.wav"
	signal.signal(signal.SIGINT, sigint_handler)
	alarm_manager = AlarmManager()
	db_restore_alarms()
	webserver = web.application(urls, globals())
	webserver.add_processor(add_global_hook())
	web.config.debug = False
	print "Press Ctrl+C to close"
	webserver.run()
	sys.exit(0)
