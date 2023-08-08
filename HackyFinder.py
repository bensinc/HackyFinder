
import socket
import threading

import subprocess


from astropy.coordinates import SkyCoord
from astropy.coordinates import get_constellation
from astropy import units

import zwoasi as asi



# Camera settings
asi.init('/home/astroberry/ASI_linux_mac_SDK_V1.30/lib/armv7/libASICamera2.so')
image_type = asi.ASI_IMG_RGB24 # asi.ASI_IMG_RAW8, or asi.ASI_IMG_RAW16
exposure = 500 # ms
gain = 450

# Solver settings
scale_low = 1.83
scale_high = 3.24
downsample = 6








port = 5005 # port for SkySafari
RA_hms = "00:00:00.0"
DEC_dms = "+00:00:00.0"
cons = "none"
solving = False






num_cameras = asi.get_num_cameras()
if num_cameras == 0:
	raise ValueError('No cameras found')

camera_id = 0
#cameras_found = asi.list_cameras()
camera = asi.Camera(camera_id)
camera_info = camera.get_camera_property()

camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, camera.get_controls()['BandWidth']['MinValue'])


camera.disable_dark_subtract()
camera.set_control_value(asi.ASI_GAIN, gain)
camera.set_control_value(asi.ASI_EXPOSURE, exposure * 1000) # microseconds
camera.set_control_value(asi.ASI_WB_B, 99)
camera.set_control_value(asi.ASI_WB_R, 75)
camera.set_control_value(asi.ASI_GAMMA, 50)
camera.set_control_value(asi.ASI_BRIGHTNESS, 50)
camera.set_control_value(asi.ASI_FLIP, 0)


def write_html():
	f = open("/var/www/html/finder/index.html", "w")
	f.write("<html><head><title>HackyFinder</title><link rel=\"stylesheet\" href=\"styles.css\"><meta name=\"viewport\" content=\"width=device-width\"/><meta http-equiv=\"refresh\" content=\"3\"></head><body>")
	f.write("<h1>HackyFinder</h1>")

	f.write("<div class=\"status\"><dl><dt>Solving</dt><dd>" + str(solving) + "</dd></dl>")
	f.write("<dl><dt>Exposure</dt><dd>" + str(exposure) + "ms</dd></dl>")
	f.write("<dl><dt>Gain</dt><dd>" + str(gain) + "</dd></dl></div>")
	if cons == "none":
		f.write("<h2>No solution found!</h2>")
	else:
		f.write("<div class=\"solution\"><dl><dt>Solution</dt><dd>" + RA_hms + ", " + DEC_dms + "<br/>" + cons + "</dd></dl></div>")
	f.write("<br/><br/><img src=\"capture.jpg\"/>")
	f.write("</body></html>")
	f.close()

def capture_image(camera, filename):
	global image_type
	print("  + Capturing image...")
	camera.set_control_value(asi.ASI_GAIN, gain)
	camera.set_control_value(asi.ASI_EXPOSURE, exposure * 1000) # microseconds
	try:
		camera.stop_video_capture()
		camera.stop_exposure()
	except (KeyboardInterrupt, SystemExit):
		raise

	camera.set_image_type(image_type)
	camera.capture(filename=filename)
	print('  + Saved to: ' + filename)

	write_html()

	if solving:
		subprocess.Popen("convert /tmp/capture.tiff /var/www/html/finder/capture.jpg", shell=True)
	else:
		subprocess.Popen("convert -resize 1024x588 -gravity Center -draw \"circle 512, 290, 512, 320\" -fill 'rgba(255, 0, 0, 0.0)' -stroke red /tmp/capture.tiff /var/www/html/finder/capture.jpg", shell=True)

	try:
		camera.stop_exposure()
	except (KeyboardInterrupt, SystemExit):
		raise

def solve_images():
	global camera
	global RA_hms
	global DEC_dms
	global cons
	global solving
	global scale_low
	global scale_high
	global downsample

	print("--+ Starting solver thread...")
	filename = "/tmp/capture.tiff"

	while True:
		capture_image(camera, filename)


		command = "/usr/bin/solve-field --no-remove-lines --uniformize 0 --scale-low 1.83 --scale-high 3.24 --overwrite --downsample 6 -p -S none -N none --cpulimit 10 /tmp/img.tiff"
		# command = "/usr/bin/solve-field --no-remove-lines --uniformize 0 --scale-low " + str(scale_low) + " --scale-high " + str(scale_high) + " --overwrite --downsample " + str(downsample) + " -p -S none -N none --cpulimit 10 " + filename
		# print(command)

		if solving:

			p = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
			(output, err) = p.communicate()
			p_status = p.wait()
			output = output.decode('ascii')
			# print("Command output : ", output)
			if "Field center" in output:
				center = output.split("Field center: (RA,Dec) = (")[1].split(")")[0]
				ra = center.split(", ")[0]
				dec = center.split(", ")[1]
				c = SkyCoord(ra, dec, frame='icrs', unit='deg')
				RA_hms = c.ra.to_string(unit=units.hourangle, sep=':',pad=True, precision=1) # format HMS
				DEC_dms = c.dec.to_string(unit=units.degree, sep=':',pad=True, alwayssign= True,precision=1) # format DMS
				cons = get_constellation(c)
				print('  + Solution: ' + RA_hms + ", " + DEC_dms + " in " + get_constellation(c))
				# print("  + Solved: " + ra + ", " + dec)
			else:
				cons = "none"
				print("  + No solution found!")


		# print("Command exit status/return code : ", p_status)





solver_thread = threading.Thread(target=solve_images)
solver_thread.start()



write_html()
print ('--+ Starting LX200 TCP Server...')

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind(('', port))
server.listen(5)

while True:
	client, address = server.accept()
	read_buffer = client.recv(20).decode();
	if read_buffer:
		print("--+ Command received: " + read_buffer)
		if read_buffer[0] == ':':
			if read_buffer[1:4] == 'GR#':
				print ('  + Sending RA: ' + '+' + RA_hms + '#')
				bytes = ('+' + RA_hms + '#').encode('utf-8')
				client.send(bytes)
			elif read_buffer[1:4] == 'Mn#':
				print("  + Move N")
				exposure += 500
				if exposure > 10000:
					exposure = 10000
				print("  + Exposure set to: " + str(exposure))
			elif read_buffer[1:4] == 'Ms#':
				print("  + Move S")
				exposure -= 500
				if exposure < 500:
					exposure = 500
				print("  + Exposure set to: " + str(exposure))
			elif read_buffer[1:4] == 'Me#':
				print("  + Move E")
				gain -= 50
				if gain < 100:
					gain = 100
				print("  + Gain set to: " + str(gain))
			elif read_buffer[1:4] == 'Mw#':
				print("  + Move W")
				gain += 50
				if gain > 1000:
					gain = 1000
				print("  + Gain set to: " + str(gain))
			elif read_buffer[1:4] == 'RG#':
				solving = False
				# Why does SkySafari require this to work?
				# Why does it only work if I send coordinates?
				print("  + Solving disabled")
				bytes = (DEC_dms + '#').encode('utf-8')
				client.send(bytes)
			elif read_buffer[1:4] == 'RS#':
				solving = True
				# Why does SkySafari require this to work?
				# Why does it only work if I send coordinates?
				print("  + Solving enabled")
				bytes = (DEC_dms + '#').encode('utf-8')
				client.send(bytes)
			elif read_buffer[1:4] == 'RM#':
				# Why does SkySafari require this to work?
				# Why does it only work if I send coordinates?
				# print("  + Setting slew speed")
				bytes = (DEC_dms + '#').encode('utf-8')
				client.send(bytes)
			elif read_buffer[1:4] == 'GD#':
				print('  + Sending DEC: ' + DEC_dms + '#')
				bytes = (DEC_dms + '#').encode('utf-8')
				client.send(bytes)
			elif read_buffer[1:2] == 'Q':
				print('  + Stop motion')
				bytes = (DEC_dms + '#').encode('utf-8')
				client.send(bytes)
		else:
			bytes = "??".encode('utf-8')
			client.send(bytes)




server.close()




