\
from typing import Dict
from io import BytesIO
from PIL import Image
import numpy as np
import cv2

def blur_faces(image_bytes: bytes, kernel: int = 31) -> Dict:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)[:, :, ::-1]
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(30,30))
    k = kernel if kernel % 2 == 1 else kernel+1
    for (x,y,w,h) in faces:
        roi = arr[y:y+h, x:x+w]
        arr[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (k,k), 0)
    out = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(out)
    buf = BytesIO(); pil.save(buf, format="PNG")
    return {"image": buf.getvalue(), "faces": len(faces)}
