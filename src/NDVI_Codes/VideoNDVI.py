import numpy as np
import cv2
from time import sleep
# from picamera import Picamera
# from picamera.array import PiRGBArray
from falseColor import FalseColor


def contStretch(image):
    # Applying the contrast stretch 
    minIn = np.percentile(image,5)
    maxIn = np.percentile(image,95)
    contImage = 255*(image-minIn)/(maxIn-minIn)
    return contImage

def calNDVI(image):
    b, g, r = cv2.split(image)
    # Taking visible light as blue and near-infrared light as red
    NIR = r.astype(float)
    vis = b.astype(float)
    # Calculating NDVI using NIR and visible light
    num = NIR - vis  
    den = NIR + vis
    den[den==0] = 0.001
    ndvi = num/den
    return ndvi

def colorMap(image):
    imageMod = image.astype(np.uint8)
    colorImage = cv2.applyColorMap(imageMod, FalseColor) 
    return colorImage

# There area different types of main progrma which needs to be tzaken under consideration to make sure we get thed esireed result 

# Main program
def videoStreamNDVI():

## Alternate method
    # video = cv2.VideoCapture(0)

    # while True:
    #     ret, frame = video.read() #returns ret and the frame
    #     originalImage = frame
    #     contrastedImage = contStretch(originalImage)
    #     #NDVIImage = calNDVI(originalImage)
    #     NDVIImage = calNDVI(contrastedImage)
    #     #print(NDVIImage.shape)
    #     colorImage = colorMap(NDVIImage)

    #     cv2.imshow('Original image',originalImage)
    #     cv2.imshow('Contrasted image',contrastedImage)
    #     cv2.imshow('NDVI image',NDVIImage)
    #     cv2.imshow('Color NDVI image',colorImage)

    #     if cv2.waitKey(1) & 0xFF == ord('q'):
    #         break

    cam = Picamera()
    vid = PiRGBArray(cam)
    cam.resolution = (640,480)
    while True:
        cam.capture(vid,'bgr')
        originalImage = vid.array
        contrastedImage = contStretch(originalImage)
        #NDVIImage = calNDVI(originalImage)
        NDVIImage = calNDVI(contrastedImage)
        #print(NDVIImage.shape)
        NDVIContrast = contStretch(NDVIImage)
        colorImage = colorMap(NDVIContrast)

        cv2.imshow('Original image',originalImage)
        cv2.imshow('Contrasted image',contrastedImage)
        cv2.imshow('NDVI image',NDVIImage)
        cv2.imshow('Color NDVI image',colorImage)

        if cv2.waitKey(1) and 0xFF == ord('q'):
            break

cv2.destroyAllWindows()

if __name__ == '__main__':
    videoStreamNDVI()