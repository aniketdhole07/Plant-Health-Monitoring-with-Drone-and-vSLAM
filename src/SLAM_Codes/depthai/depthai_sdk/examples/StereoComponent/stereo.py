import cv2
import depthai

from depthai_sdk import OakCamera
from depthai_sdk.visualize.configs import StereoColor

with OakCamera(usbSpeed=depthai.UsbSpeed.HIGH) as oak:
    stereo = oak.create_stereo('400p', fps=30)
    stereo.configure_postprocessing(
        colorize=StereoColor.RGB,
        colormap=cv2.COLORMAP_BONE,
        wls_filter=True,
        wls_lambda=8000,
        wls_sigma=1.5
    )

    oak.visualize(stereo.out.depth)
    oak.start(blocking=True)
