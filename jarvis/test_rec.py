import sounddevice as sd
import numpy as np

DEVICE = 25
SR = 48000

print("Recording 3 seconds... speak.")
audio = sd.rec(int(3 * SR), samplerate=SR, channels=1, dtype="float32", device=DEVICE)
sd.wait()

rms = float(np.sqrt(np.mean(audio[:,0]**2)))
peak = float(np.max(np.abs(audio[:,0])))

print("RMS:", rms)
print("PEAK:", peak)
