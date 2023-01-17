import numpy as np
#import pandas as pd
import cv2
from time import sleep
# from picamera import Picamera
# from picamera.array import PiRGBArray
from fastiecm import fastiecm

def takeImage():
    cam = Picamera()       #creating object to for camera class
    cam.resolution = (640,480)
    cam.start_preview()    #Preview of image
    sleep(3)       #Time to warm up
    cam.capture("original.jpg")
    im = cv2.imread("original.jpg")
    return im



def contStretch(image):
    # Applying the contrast stretch 
    minIn = np.percentile(image,1)
    maxIn = np.percentile(image,99)
    contImage = 255*(image-minIn)/(maxIn-minIn)
    return contImage

    # in_min = np.percentile(image, 5)
    # in_max = np.percentile(image, 95)

    # out_min = 0.0
    # out_max = 255.0

    # out = image - in_min
    # out *= ((out_min - out_max) / (in_min - in_max))
    # out += in_min

    # return out


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
    colorImage = cv2.applyColorMap(imageMod, fastiecm) 
    #colorImage = cv2.applyColorMap(imageMod, cv2.COLORMAP_JET)
    return colorImage
#originalImage = takeImage()
originalImage = cv2.imread('C:\Users\singh\OneDrive\Desktop\LAB5\Mural 15%/panimage1.jpg')
print(originalImage.shape)
originalImage = cv2.resize(originalImage,(720,576))
contrastedImage = contStretch(originalImage)
NDVIImage = calNDVI(contrastedImage)
#print(NDVIImage.shape)
NDVIContrast = contStretch(NDVIImage)
colorImage = colorMap(NDVIContrast)
print(colorImage)

pd.DataFrame(NDVIContrast).to_csv('NDVIContrast.csv')
pd.DataFrame(NDVIImage).to_csv('NDVIImage.csv')

# pd.DataFrame(print(colorImage)).to_csv('colorImage.csv')
cv2.imshow('Original image',originalImage)
#cv2.imshow('Contrasted image',contrastedImage)
#cv2.imshow('NDVI image',NDVIContrast)
cv2.imshow('Color NDVI image',colorImage)
cv2.waitKey(0) # wait for key press
cv2.destroyAllWindows()

