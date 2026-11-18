import time
from faster_whisper import WhisperModel

print("Loading WhisperModel tiny...")
t0 = time.time()
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print(f"Loaded in {time.time() - t0:.2f}s")
