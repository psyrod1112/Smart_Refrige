from picamera2 import Picamera2
cam = Picamera2()
cam.start()
print('camera on')
cam.stop()
