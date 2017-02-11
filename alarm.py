import pygame
import datetime
import threading
from time import sleep
import json
import signal
import sys

class Alarm:
	def __init__(self, file_name="alarm.wav", alarm_type="fixed", date_time=datetime.datetime.now(), duration=30, alarm_data=None):
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
			self.initialize(file_name, _alarm_type, _date_time, _duration)
		else:
			self.initialize(file_name, alarm_type, date_time, duration)


	def initialize(self, file_name, alarm_type, date_time, duration):
		self.file_name = file_name
		self.alarm_type = alarm_type
		self.date_time = date_time
		self.duration = duration
		self.end_time = self.compute_endtime()
		self.is_active = False
		self.is_triggered = False
		self.thread = self.AlarmThread(self)

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
				pygame.mixer.music.load(self.alarm.file_name)
				while self.alarm.is_active == True and self.alarm.end_time > datetime.datetime.now():
					if pygame.mixer.music.get_busy():
						sleep(0.1)
					else:
						pygame.mixer.music.rewind()
						pygame.mixer.music.play()
				pygame.mixer.music.stop()
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
		self.thread = self.AlarmManagerThread(self)

	def add_alarm(self, alarm):
		self.alarms.append(alarm)
		self.is_running = False

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
			pygame.mixer.init()
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
					for alarm in self.alarm_manager.alarms:
						if not alarm.is_triggered and alarm.is_active:
							if datetime.datetime.now() >= alarm.date_time:
								self.has_alarm_triggered = True
								alarm.trigger()
				sleep(0.1)

def sigint_handler(signal, frame):
	print('\nCtrl+C received')
	alarm_manager.stop()
	sys.exit(0)

alarm_manager = None

if __name__ == "__main__":
	signal.signal(signal.SIGINT, sigint_handler)
	filename = "alarm.wav"
	alarm_manager = AlarmManager()
	with open('alarms.json', 'r') as json_file:
		json_string = json_file.read()

	json_data = json.loads(json_string)
	alarms = json_data['alarms']

	for alarm_data in alarms:
		alarm = Alarm(file_name=filename, alarm_data=alarm_data)
		alarm.activate()
		alarm_manager.add_alarm(alarm)
	alarm_manager.start()
	print "Press Ctrl+C to close on Linux or Ctrl+Break(Pause) on Windows"
	while True:
		sleep(1)
