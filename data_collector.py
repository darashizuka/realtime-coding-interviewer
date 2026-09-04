import cv2
import mediapipe as mp
import os
import time

# --- setup ---
SAVE_DIR = "dataset_raw"
CLASSES = ["focused", "distracted"]
IMG_SIZE = 224  # ResNet input size
# ----------------

# create folders
for cls in CLASSES:
    os.makedirs(os.path.join(SAVE_DIR, cls), exist_ok=True)

# Initialize MediaPipe face detection.
mp_face_detection = mp.solutions.face_detection
mp_drawing = mp.solutions.drawing_utils
face_detection = mp_face_detection.FaceDetection(min_detection_confidence=0.5)

cap = cv2.VideoCapture(0) # 0 default camera

count_f = len(os.listdir(os.path.join(SAVE_DIR, "focused")))
count_d = len(os.listdir(os.path.join(SAVE_DIR, "distracted")))

print("=== Data Collection Instructions ===")
print("Press and hold the 'f' key -> Save the [Focused] sample (see screen)")
print("Press and hold the 'd' key -> Save [Distracted] sample (looking at phone/looking down/looking to the side)")
print("Press the 'q' key -> Exit")
print("==================")

while cap.isOpened():
    success, image = cap.read()
    if not success:
        continue

    # 1. Flip the image (like looking in a mirror) and convert it to RGB.
    image = cv2.flip(image, 1)
    img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # 2. Detecting faces
    results = face_detection.process(img_rgb)
    
    face_img = None
    
    if results.detections:
        for detection in results.detections:
            # Obtain the face bounding box.
            bboxC = detection.location_data.relative_bounding_box
            ih, iw, _ = image.shape
            x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
            
            # Slightly increase the padding around the image to prevent cropping off the chin or forehead.
            pad = 20
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(iw - x, w + pad * 2)
            h = min(ih - y, h + pad * 2)

            # The face region is cropped only when a face is detected.
            if w > 0 and h > 0:
                face_img = image[y:y+h, x:x+w]
                # Draw a green box for the user to see.
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # 3. Display screen
    cv2.putText(image, f"Focused: {count_f} | Distracted: {count_d}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow('Data Collector', image)

    # 4. Button press save logic
    key = cv2.waitKey(5) & 0xFF
    if key == ord('q'):
        break
    
    # Only save the image when a face is detected.
    if face_img is not None:
        face_resized = cv2.resize(face_img, (IMG_SIZE, IMG_SIZE))
        
        if key == ord('f'): # Save Focused
            fname = os.path.join(SAVE_DIR, "focused", f"f_{int(time.time()*1000)}.jpg")
            cv2.imwrite(fname, face_resized)
            count_f += 1
            print(f"Saved Focused: {count_f}", end="\r")
            
        elif key == ord('d'): # Save Distracted
            fname = os.path.join(SAVE_DIR, "distracted", f"d_{int(time.time()*1000)}.jpg")
            cv2.imwrite(fname, face_resized)
            count_d += 1
            print(f"Saved Distracted: {count_d}", end="\r")

cap.release()
cv2.destroyAllWindows()