from typing import Tuple

import numpy as np

from depthai_sdk.components.nn_helper import AspectRatioResizeMode


class NormalizeBoundingBox:
    """
    Normalized bounding box (BB) received from the device. It will also take into account type of aspect ratio
    resize mode and map coordinates to correct location.
    """

    def __init__(self,
                 aspectRatio: Tuple[float, float],
                 arResizeMode: AspectRatioResizeMode,
                 ):
        """
        @param aspectRatio: NN input size
        @param arResizeMode
        """
        self.aspectRatio = aspectRatio
        self.arResizeMode = arResizeMode

        pass

    def normalize(self, frame, bbox: Tuple[float, float, float, float]) -> np.ndarray:
        """
        Mapps bounding box coordinates (0..1) to pixel values on frame

        Args:
            frame (numpy.ndarray): Frame to which adjust the bounding box
            bbox (list): list of bounding box points in a form of :code:`[x1, y1, x2, y2, ...]`

        Returns:
            list: Bounding box points mapped to pixel values on frame
        """
        bbox = np.array(bbox)

        # Edit the bounding boxes before normalizing them
        if self.arResizeMode == AspectRatioResizeMode.CROP:
            ar_diff = self.aspectRatio[0] / self.aspectRatio[1] - frame.shape[0] / frame.shape[1]
            sel = 0 if 0 < ar_diff else 1
            bbox[sel::2] *= 1 - abs(ar_diff)
            bbox[sel::2] += abs(ar_diff) / 2
        elif self.arResizeMode == AspectRatioResizeMode.STRETCH:
            # No need to edit bounding boxes when stretching
            pass
        elif self.arResizeMode == AspectRatioResizeMode.LETTERBOX:
            # There might be better way of doing this. TODO: test if it works as expected
            ar_diff = self.aspectRatio[0] / self.aspectRatio[1] - frame.shape[1] / frame.shape[0]
            sel = 0 if 0 < ar_diff else 1
            nsel = 0 if sel == 1 else 1
            # Get the divisor
            div = frame.shape[sel] / self.aspectRatio[nsel]
            letterboxing_ratio = 1 - (frame.shape[nsel] / div) / self.aspectRatio[sel]

            bbox[sel::2] -= abs(letterboxing_ratio) / 2
            bbox[sel::2] /= 1 - abs(letterboxing_ratio)

        # Normalize bounding boxes
        normVals = np.full(len(bbox), frame.shape[0])
        normVals[::2] = frame.shape[1]
        return (np.clip(bbox, 0, 1) * normVals).astype(int)
