import os
import soundfile as sf
import numpy as np
import whisper
import csv

# --- CONFIG ---
input_wav = "interview.wav"  # <-- replace with your WAV path
chunk_length_sec = 5
audio_dir = "dataset/audio"
text_dir = "dataset/texts"
metadata_file = "dataset/metadata.csv"

os.makedirs(audio_dir, exist_ok=True)
os.makedirs(text_dir, exist_ok=True)

# --- LOAD AUDIO ---
data, samplerate = sf.read(input_wav)
total_samples = len(data)
chunk_samples = chunk_length_sec * samplerate

# --- LOAD WHISPER MODEL ---
print("Loading Whisper model...")
model = whisper.load_model("medium")

metadata = []

# --- SPLIT, EXPORT, TRANSCRIBE ---
for i, start in enumerate(range(0, total_samples, chunk_samples)):
    chunk = data[start:start + chunk_samples]
    chunk_path = os.path.join(audio_dir, f"chunk_{i:04d}.wav")
    sf.write(chunk_path, chunk, samplerate)
    print(f"[{i}] Exported: {chunk_path}")
    
    # Transcribe chunk
    result = model.transcribe(chunk_path)
    text = result["text"].strip()
    print(f"[{i}] Transcribed: {text[:50]}...")  # first 50 chars
    
    # Save text file
    text_file = os.path.join(text_dir, f"chunk_{i:04d}.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(text)
    
    # Add to metadata
    metadata.append([chunk_path, text])

# --- SAVE METADATA ---
os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
with open(metadata_file, "w", newline='', encoding="utf-8") as f:
    writer = csv.writer(f, delimiter='|')
    writer.writerows(metadata)

print("✅ Preprocessing and transcription complete!")
print(f"Metadata saved at: {metadata_file}")
