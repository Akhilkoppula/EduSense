import cv2
import os

print("--- EduSense Phase 1: Native Engine Test ---")

# 1. Load the built-in OpenCV face detector
# This uses a file already included with your opencv installation
cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(cascade_path)

if face_cascade.empty():
    print("Error: Could not load face detector files.")
else:
    print("Face Detector: Successfully Loaded!")

# 2. Open Camera
cap = cv2.VideoCapture(0)
print("Opening camera window... Press 'q' to close.")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    # Convert to grayscale (required for this detector)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Detect faces
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

    # Draw a green box around every face found
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(frame, "STUDENT DETECTED", (x, y-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow('EduSense Phase 1: Native Face Tracking', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("Success! Phase 1 Core is officially running.")
