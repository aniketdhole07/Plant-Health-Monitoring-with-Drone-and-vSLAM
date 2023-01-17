from abc import abstractmethod
from typing import Dict, List, Any, Optional, Tuple, Union

import cv2
import depthai as dai
import numpy as np

from distinctipy import distinctipy
from pathlib import Path
from matplotlib import pyplot as plt

from depthai_sdk.oak_outputs.normalize_bb import NormalizeBoundingBox
from depthai_sdk.visualize.visualizer import Platform
from depthai_sdk.visualize.visualizer_helper import colorize_disparity, calc_disp_multiplier, draw_mappings, hex_to_bgr
from depthai_sdk.oak_outputs.xout_base import XoutBase, StreamXout
from depthai_sdk.oak_outputs.syncing import SequenceNumSync
from depthai_sdk.classes.packets import (
    FramePacket,
    SpatialBbMappingPacket,
    DetectionPacket,
    TwoStagePacket,
    TrackerPacket,
    IMUPacket, DepthPacket, _Detection
)
from depthai_sdk.visualize.configs import StereoColor
from depthai_sdk.visualize import Visualizer
from depthai_sdk.visualize.configs import TextPosition

"""
Xout classes are abstracting streaming messages to the host computer (via XLinkOut) and syncing those messages
on the host side before sending (synced) messages to message sinks (eg. visualizers, or loggers).
TODO:
- separate syncing logic from the class. XoutTwoStage should extend the XoutNnResults (currently can't as syncing logic is not separated)
"""


class XoutFrames(XoutBase):
    """
    Single message, no syncing required
    """
    name: str = "Frames"
    fps: float
    frames: StreamXout
    _frame_shape: Tuple[int, int] = None
    _scale: Union[None, float, Tuple[int, int]] = None
    _show_fps: bool = False
    _recording_path: Optional[Path] = None
    _video_writer: Optional[cv2.VideoWriter] = None
    _fourcc_codec_code = None
    _frames_buffer: List
    _FRAMES_TO_BUFFER: int = 20

    def __init__(self, frames: StreamXout, fps: float = 30):
        self.frames = frames
        self.fps = fps
        self._frames_buffer = []
        super().__init__()

    def setup_visualize(self, visualizer: Visualizer,
                        name: str = None,
                        recording_path: Optional[str] = None):
        self._visualizer = visualizer
        self.name = name or self.name

        if recording_path:
            self._recording_path = Path(recording_path).resolve()
            video_format = self._recording_path.suffix
            if video_format == ".mp4":
                self._fourcc_codec_code = cv2.VideoWriter_fourcc(*'mp4v')
            elif video_format == ".avi":
                self._fourcc_codec_code = cv2.VideoWriter_fourcc(*'FMP4')
            else:
                print("Selected video format not supported, using mp4 instead.")
                self._fourcc_codec_code = cv2.VideoWriter_fourcc(*'mp4v')

    def visualize(self, packet: FramePacket) -> None:
        """
        Called from main thread if visualizer is not None
        """

        self._visualizer.frame_shape = packet.frame.shape

        if self._visualizer.config.output.show_fps:
            self._visualizer.add_text(
                text=f'FPS: {self._fps.fps():.1f}',
                position=TextPosition.TOP_LEFT
            )

        packet.frame = self._visualizer.draw(packet.frame)

        if self.callback:  # Don't display frame, call the callback
            self.callback(packet, self._visualizer)
        else:
            # TODO: if RH, don't display frame
            # Draw on the frame
            if self._visualizer.platform == Platform.PC:
                cv2.imshow(self.name, packet.frame)
            else:
                pass

        # Record
        if self._recording_path and not self._video_writer:
            if len(self._frames_buffer) < self._FRAMES_TO_BUFFER:
                self._frames_buffer.append(packet.frame)
            else:
                h, w = self._visualizer.frame_shape[:2]
                self._video_writer = cv2.VideoWriter(str(self._recording_path),
                                                     self._fourcc_codec_code,
                                                     self._fps.fps(),
                                                     (w, h)
                                                     )
                # Write all buffered frames
                for frame in self._frames_buffer:
                    self._video_writer.write(frame)
        elif self._video_writer:
            self._video_writer.write(packet.frame)

    def xstreams(self) -> List[StreamXout]:
        return [self.frames]

    def newMsg(self, name: str, msg) -> None:
        if name not in self._streams:
            return

        if self.queue.full():
            self.queue.get()  # Get one, so queue isn't full

        packet = FramePacket(name, msg, msg.getCvFrame())

        self.queue.put(packet, block=False)

    def __del__(self):
        if self._video_writer:
            self._video_writer.release()


class XoutMjpeg(XoutFrames):
    name: str = "MJPEG Stream"
    lossless: bool
    fps: float

    def __init__(self, frames: StreamXout, color: bool, lossless: bool, fps: float):
        super().__init__(frames)
        # We could use cv2.IMREAD_UNCHANGED, but it produces 3 planes (RGB) for mono frame instead of a single plane
        self.flag = cv2.IMREAD_COLOR if color else cv2.IMREAD_GRAYSCALE
        self.lossless = lossless
        self.fps = fps
        if lossless and self._vis:
            raise ValueError('Visualizing Lossless MJPEG stream is not supported!')

    def visualize(self, packet: FramePacket):
        # TODO use PyTurbo
        packet.frame = cv2.imdecode(packet.imgFrame.getData(), self.flag)
        super().visualize(packet)


class XoutH26x(XoutFrames):
    name = "H26x Stream"
    color: bool
    fps: float
    profile: dai.VideoEncoderProperties.Profile

    def __init__(self, frames: StreamXout, color: bool, profile: dai.VideoEncoderProperties.Profile, fps: float):
        super().__init__(frames)
        self.color = color
        self.profile = profile
        self.fps = fps
        fourcc = 'hevc' if profile == dai.VideoEncoderProperties.Profile.H265_MAIN else 'h264'
        import av
        self.codec = av.CodecContext.create(fourcc, "r")

    def visualize(self, packet: FramePacket):
        enc_packets = self.codec.parse(packet.imgFrame.getData())

        if len(enc_packets) == 0:
            return

        frames = self.codec.decode(enc_packets[-1])

        if not frames:
            return

        frame = frames[0].to_ndarray(format='bgr24')

        # If it's Mono, squeeze from 3 planes (height, width, 3) to single plane (height, width)
        if not self.color:
            frame = frame[:, :, 0]

        packet.frame = frame
        super().visualize(packet)


class XoutClickable:
    decay_step: int  # How many packets to wait before text disappears
    buffer: Tuple[int, int, List[int]]

    def __init__(self, decay_step: int = 30):
        super().__init__()
        self.buffer = None
        self.decay_step = decay_step

    def on_click_callback(self, event, x, y, flags, param) -> None:
        if event == cv2.EVENT_MOUSEMOVE:
            self.buffer = ([0, param[0][y, x], [x, y]])


class XoutDisparity(XoutFrames, XoutClickable):
    name: str = "Disparity"
    multiplier: float
    fps: float

    def __init__(self,
                 disparity_frames: StreamXout,
                 mono_frames: StreamXout,
                 max_disp: float,
                 fps: float,
                 colorize: StereoColor = False,
                 colormap: int = None,
                 use_wls_filter: bool = None,
                 wls_lambda: float = None,
                 wls_sigma: float = None):
        self.mono_frames = mono_frames

        self.multiplier = 255.0 / max_disp
        self.fps = fps

        self.colorize = colorize
        self.colormap = colormap
        self.use_wls_filter = use_wls_filter
        if use_wls_filter:
            self.wls_filter = cv2.ximgproc.createDisparityWLSFilterGeneric(False)
            self.wls_filter.setLambda(wls_lambda)
            self.wls_filter.setSigmaColor(wls_sigma)

        self.msgs = dict()

        XoutFrames.__init__(self, frames=disparity_frames, fps=fps)
        XoutClickable.__init__(self, decay_step=int(self.fps))

    def visualize(self, packet: DepthPacket):
        frame = packet.frame
        disparity_frame = (frame * self.multiplier).astype(np.uint8)

        if self.use_wls_filter:
            disparity_frame = self.wls_filter.filter(disparity_frame, packet.mono_frame.getCvFrame())

        if self.colorize == StereoColor.GRAY:
            packet.frame = disparity_frame
        elif self.colorize == StereoColor.RGB:
            packet.frame = cv2.applyColorMap(disparity_frame, self.colormap or cv2.COLORMAP_JET)
        elif self.colorize == StereoColor.RGBD:
            packet.frame = cv2.applyColorMap(
                (disparity_frame * 0.5 + packet.mono_frame.getCvFrame() * 0.5).astype(np.uint8),
                self.colormap or cv2.COLORMAP_JET
            )

        if self._visualizer.config.output.clickable:
            cv2.namedWindow(self.name)
            cv2.setMouseCallback(self.name, self.on_click_callback, param=[disparity_frame])

            if self.buffer:
                x, y = self.buffer[2]
                self._visualizer.add_circle(coords=(x, y), radius=3, color=(255, 255, 255), thickness=-1)
                self._visualizer.add_text(
                    text=f'{self.buffer[1]}',
                    coords=(x, y - 10)
                )

        super().visualize(packet)

    def xstreams(self) -> List[StreamXout]:
        return [self.frames, self.mono_frames]

    def newMsg(self, name: str, msg: dai.Buffer) -> None:
        if name not in self._streams:
            return  # From Replay modules. TODO: better handling?

        # TODO: what if msg doesn't have sequence num?
        seq = str(msg.getSequenceNum())

        if seq not in self.msgs:
            self.msgs[seq] = dict()

        if name == self.frames.name:
            self.msgs[seq][name] = msg
        elif name == self.mono_frames.name:
            self.msgs[seq][name] = msg
        else:
            raise ValueError('Message from unknown stream name received by TwoStageSeqSync!')

        if len(self.msgs[seq]) == len(self.xstreams()):
            # Frames synced!
            if self.queue.full():
                self.queue.get()  # Get one, so queue isn't full

            packet = DepthPacket(
                self.get_packet_name(),
                self.msgs[seq][self.frames.name],
                self.msgs[seq][self.mono_frames.name],
            )
            self.queue.put(packet, block=False)

            newMsgs = {}
            for name, msg in self.msgs.items():
                if int(name) > int(seq):
                    newMsgs[name] = msg
            self.msgs = newMsgs


# TODO can we merge XoutDispariry and XoutDepth?
class XoutDepth(XoutFrames, XoutClickable):
    name: str = "Depth"

    def __init__(self,
                 device: dai.Device,
                 frames: StreamXout,
                 fps: float,
                 mono_frames: StreamXout,
                 colorize: StereoColor = False,
                 colormap: int = None,
                 use_wls_filter: bool = None,
                 wls_lambda: float = None,
                 wls_sigma: float = None):
        self.mono_frames = mono_frames

        self.fps = fps
        self.device = device
        # self.multiplier = 255 / 95.0

        self.colorize = colorize
        self.colormap = colormap
        self.use_wls_filter = use_wls_filter
        if use_wls_filter:
            self.wls_filter = cv2.ximgproc.createDisparityWLSFilterGeneric(False)
            self.wls_filter.setLambda(wls_lambda)
            self.wls_filter.setSigmaColor(wls_sigma)

        self.msgs = dict()

        XoutFrames.__init__(self, frames=frames, fps=fps)
        XoutClickable.__init__(self, decay_step=int(self.fps))

    def visualize(self, packet: DepthPacket):
        depth_frame = packet.imgFrame.getFrame()

        if self.use_wls_filter:
            depth_frame = self.wls_filter.filter(depth_frame, packet.mono_frame.getCvFrame())

        depth_frame_color = cv2.normalize(depth_frame, None, 256, 0, cv2.NORM_INF, cv2.CV_8UC3)
        depth_frame_color = cv2.equalizeHist(depth_frame_color)

        if self.colorize == StereoColor.GRAY:
            packet.frame = depth_frame_color
        elif self.colorize == StereoColor.RGB:
            packet.frame = cv2.applyColorMap(depth_frame_color, self.colormap or cv2.COLORMAP_JET)
        elif self.colorize == StereoColor.RGBD:
            packet.frame = cv2.applyColorMap(
                (depth_frame_color * 0.5 + packet.mono_frame.getCvFrame() * 0.5).astype(np.uint8),
                self.colormap or cv2.COLORMAP_JET
            )

        if self._visualizer.config.output.clickable:
            cv2.namedWindow(self.name)
            cv2.setMouseCallback(self.name, self.on_click_callback, param=[depth_frame])

            if self.buffer:
                x, y = self.buffer[2]
                self._visualizer.add_circle(coords=(x, y), radius=3, color=(255, 255, 255), thickness=-1)
                self._visualizer.add_text(
                    text=f'{self.buffer[1] / 10} cm',
                    coords=(x, y - 10)
                )

        super().visualize(packet)

    def xstreams(self) -> List[StreamXout]:
        return [self.frames, self.mono_frames]

    def newMsg(self, name: str, msg: dai.Buffer) -> None:
        if name not in self._streams:
            return  # From Replay modules. TODO: better handling?

        # TODO: what if msg doesn't have sequence num?
        seq = str(msg.getSequenceNum())

        if seq not in self.msgs:
            self.msgs[seq] = dict()

        if name == self.frames.name:
            self.msgs[seq][name] = msg
        elif name == self.mono_frames.name:
            self.msgs[seq][name] = msg
        else:
            raise ValueError('Message from unknown stream name received by TwoStageSeqSync!')

        if len(self.msgs[seq]) == len(self.xstreams()):
            # Frames synced!
            if self.queue.full():
                self.queue.get()  # Get one, so queue isn't full

            packet = DepthPacket(
                self.get_packet_name(),
                self.msgs[seq][self.frames.name],
                self.msgs[seq][self.mono_frames.name],
            )
            self.queue.put(packet, block=False)

            newMsgs = {}
            for name, msg in self.msgs.items():
                if int(name) > int(seq):
                    newMsgs[name] = msg
            self.msgs = newMsgs


class XoutSeqSync(XoutBase, SequenceNumSync):
    streams: List[StreamXout]

    def xstreams(self) -> List[StreamXout]:
        return self.streams

    def __init__(self, streams: List[StreamXout]):
        self.streams = streams
        # Save StreamXout before initializing super()!
        XoutBase.__init__(self)
        SequenceNumSync.__init__(self, len(streams))
        self.msgs = dict()

    @abstractmethod
    def package(self, msgs: List):
        raise NotImplementedError('XoutSeqSync is an abstract class, you need to override package() method!')

    def newMsg(self, name: str, msg) -> None:
        # Ignore frames that we aren't listening for
        if name not in self._streams: return

        synced = self.sync(msg.getSequenceNum(), name, msg)
        if synced:
            self.package(synced)


class XoutNnResults(XoutSeqSync, XoutFrames):
    name: str = "Object Detection"
    labels: List[Tuple[str, Tuple[int, int, int]]] = None
    normalizer: NormalizeBoundingBox

    def xstreams(self) -> List[StreamXout]:
        return [self.nn_results, self.frames]

    def __init__(self, det_nn, frames: StreamXout, nn_results: StreamXout):
        self.nn_results = nn_results
        self.det_nn = det_nn
        # Multiple inheritance init
        XoutFrames.__init__(self, frames)
        XoutSeqSync.__init__(self, [frames, nn_results])
        # Save StreamXout before initializing super()!

        # TODO: add support for colors, generate new colors for each label that doesn't have colors
        if det_nn._labels:
            self.labels = []
            n_colors = [isinstance(label, str) for label in det_nn._labels].count(True)
            # np.array of (b,g,r), 0..1
            colors = np.array(distinctipy.get_colors(n_colors=n_colors, rng=123123, pastel_factor=0.5))[..., ::-1]
            colors = [distinctipy.get_rgb256(clr) for clr in colors]  # List of (b,g,r), 0..255
            for label in det_nn._labels:
                if isinstance(label, str):
                    text = label
                    color = colors.pop(0)  # Take last row
                elif isinstance(label, list):
                    text = label[0]
                    color = hex_to_bgr(label[1])
                else:
                    raise ValueError('Model JSON config error. Label map list can have either str or list!')

                self.labels.append((text, color))

        self.normalizer = NormalizeBoundingBox(det_nn._size, det_nn._arResizeMode)

    def visualize(self, packet: Union[DetectionPacket, TrackerPacket]):
        # We can't visualize NNData (not decoded)
        if isinstance(packet, DetectionPacket) and isinstance(packet.img_detections, dai.NNData):
            raise Exception(
                "Can't visualize this NN result because it's not an object detection model! Use oak.callback() instead."
            )

        if isinstance(packet, TrackerPacket):
            pass  # TrackerPacket draws detection boxes itself
        else:
            # Add detections to packet
            for detection in packet.img_detections.detections:
                d = _Detection()
                d.img_detection = detection
                d.label = self.labels[detection.label][0] if self.labels else str(detection.label)
                d.color = self.labels[detection.label][1] if self.labels else (255, 255, 255)
                bbox = self.normalizer.normalize(
                    frame=packet.frame,
                    bbox=(detection.xmin, detection.ymin, detection.xmax, detection.ymax)
                )
                d.top_left = (int(bbox[0]), int(bbox[1]))
                d.bottom_right = (int(bbox[2]), int(bbox[3]))
                packet.detections.append(d)

            self._visualizer.add_detections(
                packet.img_detections.detections,
                self.normalizer,
                self.labels,
                is_spatial=packet._is_spatial_detection()
            )

        super().visualize(packet)

    def package(self, msgs: Dict):
        if self.queue.full():
            self.queue.get()  # Get one, so queue isn't full
        packet = DetectionPacket(
            self.get_packet_name(),
            msgs[self.frames.name],
            msgs[self.nn_results.name],
        )
        self.queue.put(packet, block=False)

class XoutSpatialBbMappings(XoutSeqSync, XoutFrames):
    name: str = "Depth & Bounding Boxes"
    # Streams
    frames: StreamXout
    configs: StreamXout

    # Save messages
    depth_msg: Optional[dai.ImgFrame] = None
    config_msg: Optional[dai.SpatialLocationCalculatorConfig] = None

    factor: float = None

    def __init__(self, device: dai.Device, frames: StreamXout, configs: StreamXout):
        self.frames = frames
        self.configs = configs
        self.device = device
        self.multiplier = 255 / 95.0
        XoutFrames.__init__(self, frames)
        XoutSeqSync.__init__(self, [frames, configs])

    def xstreams(self) -> List[StreamXout]:
        return [self.frames, self.configs]

    def visualize(self, packet: SpatialBbMappingPacket):
        if not self.factor:
            size = (packet.imgFrame.getWidth(), packet.imgFrame.getHeight())
            self.factor = calc_disp_multiplier(self.device, size)

        depth = np.array(packet.imgFrame.getFrame())
        with np.errstate(divide='ignore'):
            disp = (self.factor / depth).astype(np.uint8)

        packet.frame = colorize_disparity(disp, multiplier=self.multiplier)
        draw_mappings(packet)

        super().visualize(packet)

    def package(self, msgs: Dict):
        if self.queue.full():
            self.queue.get()  # Get one, so queue isn't full
        packet = SpatialBbMappingPacket(
            self.get_packet_name(),
            msgs[self.frames.name],
            msgs[self.configs.name],
        )
        self.queue.put(packet, block=False)



class XoutTracker(XoutNnResults):
    name: str = "Object Tracker"
    # TODO: hold tracklets for a few frames so we can draw breadcrumb trail
    packets: List[TrackerPacket]

    def __init__(self, det_nn, frames: StreamXout, tracklets: StreamXout):
        super().__init__(det_nn, frames, tracklets)
        self.packets = []

    def visualize(self, packet: TrackerPacket):
        try:
            if packet._is_spatial_detection():
                spatial_points = [packet._get_spatials(det.srcImgDetection)
                                  for det in
                                  packet.daiTracklets.tracklets]
            else:
                spatial_points = None
        except IndexError:
            spatial_points = None

        self._visualizer.add_detections(packet.daiTracklets.tracklets,
                                        self.normalizer,
                                        self.labels,
                                        spatial_points=spatial_points)

        # Add to local storage
        self.packets.append(packet)
        if 10 < len(self.packets):
            self.packets.pop(0)

        self._visualizer.add_trail(
            tracklets=[t for p in self.packets for t in p.daiTracklets.tracklets],
            label_map=self.labels
        )

        # Add trail id
        h, w = packet.frame.shape[:2]
        for tracklet in packet.daiTracklets.tracklets:
            det = tracklet.srcImgDetection
            bbox = (w * det.xmin, h * det.ymin, w * det.xmax, h * det.ymax)
            bbox = tuple(map(int, bbox))
            self._visualizer.add_text(
                f'ID: {tracklet.id}',
                bbox=bbox,
                position=TextPosition.MID
            )

        super().visualize(packet)

    def package(self, msgs: Dict):
        if self.queue.full():
            self.queue.get()  # Get one, so queue isn't full
        packet = TrackerPacket(
            self.get_packet_name(),
            msgs[self.frames.name],
            msgs[self.nn_results.name],
        )
        self.queue.put(packet, block=False)


# class TimestampSycn(BaseSync):
#     """
#     Timestamp sync will sync all streams based on the timestamp
#     """
#     msgs: Dict[str, List[dai.Buffer]] = dict()  # List of messages
#
#     def newMsg(self, name: str, msg) -> None:
#         # Ignore frames that we aren't listening for
#         if name not in self.streams: return
#         # Return all latest msgs (not synced)
#         if name not in self.msgs: self.msgs[name] = []
#
#         self.msgs[name].append(msg)
#         msgsAvailableCnt = [0 < len(arr) for _, arr in self.msgs.items()].count(True)
#
#         if len(self.streams) == msgsAvailableCnt:
#             # We have at least 1 msg for each stream. Get the latest, remove all others.
#             ret = {}
#             for name, arr in self.msgs.items():
#                 # print(f'len(msgs[{name}])', len(self.msgs[name]))
#                 self.msgs[name] = self.msgs[name][-1:]  # Remove older msgs
#                 # print(f'After removing - len(msgs[{name}])', len(self.msgs[name]))
#                 ret[name] = arr[-1]
#
#             if self.queue.full():
#                 self.queue.get()  # Get one, so queue isn't full
#
#             # print(time.time(),' Putting msg batch into queue. queue size', self.queue.qsize(), 'self.msgs len')
#
#             self.queue.put(ret, block=False)


class XoutTwoStage(XoutNnResults):
    """
    Two stage syncing based on sequence number. Each frame produces ImgDetections msg that contains X detections.
    Each detection (if not on blacklist) will crop the original frame and forward it to the second (stage) NN for
    inferencing.
    """
    name: str = "TwoStage Detection"
    msgs: Dict[str, Dict[str, Any]] = dict()  # List of messages
    """
    msgs = {
        '1': TwoStageSyncPacket(),
        '2': TwoStageSyncPacket(), 
    }
    """
    whitelist_labels: Optional[List[int]] = None
    scaleBb: Optional[Tuple[int, int]] = None

    second_nn: StreamXout

    def __init__(self, det_nn, secondNn, frames: StreamXout, detections: StreamXout, second_nn: StreamXout):
        self.second_nn = second_nn
        # Save StreamXout before initializing super()!
        super().__init__(det_nn, frames, detections)

        self.detNn = det_nn
        self.secondNn = secondNn

        conf = det_nn._multi_stage_config  # No types due to circular import...
        if conf is not None:
            self.labels = conf._labels
            self.scaleBb = conf.scaleBb

    def xstreams(self) -> List[StreamXout]:
        return [self.frames, self.nn_results, self.second_nn]

    # No need for `def visualize()` as `XoutNnResults.visualize()` does what we want

    def newMsg(self, name: str, msg: dai.Buffer) -> None:
        if name not in self._streams: return  # From Replay modules. TODO: better handling?

        # TODO: what if msg doesn't have sequence num?
        seq = str(msg.getSequenceNum())

        if seq not in self.msgs:
            self.msgs[seq] = dict()
            self.msgs[seq][self.second_nn.name] = []
            self.msgs[seq][self.nn_results.name] = None

        if name == self.second_nn.name:
            self.msgs[seq][name].append(msg)
            # print(f'Added recognition seq {seq}, total len {len(self.msgs[seq]["recognition"])}')
        elif name == self.nn_results.name:
            self.add_detections(seq, msg)
            # print(f'Added detection seq {seq}')
        elif name in self.frames.name:
            self.msgs[seq][name] = msg
            # print(f'Added frame seq {seq}')
        else:
            raise ValueError('Message from unknown stream name received by TwoStageSeqSync!')

        if self.synced(seq):
            # Frames synced!
            if self.queue.full():
                self.queue.get()  # Get one, so queue isn't full

            packet = TwoStagePacket(
                self.get_packet_name(),
                self.msgs[seq][self.frames.name],
                self.msgs[seq][self.nn_results.name],
                self.msgs[seq][self.second_nn.name],
                self.whitelist_labels
            )
            self.queue.put(packet, block=False)

            # Throws RuntimeError: dictionary changed size during iteration
            # for s in self.msgs:
            #     if int(s) <= int(seq):
            #         del self.msgs[s]

            newMsgs = {}
            for name, msg in self.msgs.items():
                if int(name) > int(seq):
                    newMsgs[name] = msg
            self.msgs = newMsgs

    def add_detections(self, seq: str, dets: dai.ImgDetections):
        # Used to match the scaled bounding boxes by the 2-stage NN script node
        self.msgs[seq][self.nn_results.name] = dets

        if self.scaleBb is None: return  # No scaling required, ignore

        for det in dets.detections:
            # Skip resizing BBs if we have whitelist and the detection label is not on it
            if self.labels and det.label not in self.labels: continue
            det.xmin -= self.scaleBb[0] / 100
            det.ymin -= self.scaleBb[1] / 100
            det.xmax += self.scaleBb[0] / 100
            det.ymax += self.scaleBb[1] / 100

    def synced(self, seq: str) -> bool:
        """
        Messages are in sync if:
            - dets is not None
            - We have at least one ImgFrame
            - number of recognition msgs is sufficient
        """
        packet = self.msgs[seq]

        if self.frames.name not in packet:
            return False  # We don't have required ImgFrames

        if not packet[self.nn_results.name]:
            return False  # We don't have dai.ImgDetections

        if len(packet[self.second_nn.name]) < self.required_recognitions(seq):
            return False  # We don't have enough 2nd stage NN results

        return True

    def required_recognitions(self, seq: str) -> int:
        """
        Required recognition results for this packet, which depends on number of detections (and white-list labels)
        """
        dets: List[dai.ImgDetection] = self.msgs[seq][self.nn_results.name].detections
        if self.whitelist_labels:
            return len([det for det in dets if det.label in self.whitelist_labels])
        else:
            return len(dets)


class XoutIMU(XoutBase):
    name: str = 'IMU'
    imu_out: StreamXout

    packets: List[IMUPacket]
    start_time: float

    def __init__(self, imu_xout: StreamXout):
        self.imu_out = imu_xout
        self.packets = []
        self.start_time = 0.0

        self.fig, self.axes = plt.subplots(2, 1, figsize=(10, 10), constrained_layout=True)
        labels = ['x', 'y', 'z']

        self.acceleration_lines = []
        for i in range(3):
            self.acceleration_lines.append(self.axes[0].plot([], [], label=f'Acceleration {labels[i]}')[0])
            self.axes[0].set_ylabel('Acceleration (m/s^2)')
            self.axes[0].set_xlabel('Time (s)')
            self.axes[0].legend()

        self.gyroscope_lines = []
        for i in range(3):
            self.gyroscope_lines.append(self.axes[1].plot([], [], label=f'Gyroscope {labels[i]}')[0])
            self.axes[1].set_ylabel('Gyroscope (rad/s)')
            self.axes[1].set_xlabel('Time (s)')
            self.axes[1].legend()

        self.acceleration_buffer = []
        self.gyroscope_buffer = []

        super().__init__()

    def setup_visualize(self, visualizer: Visualizer, name: str = None, _=None):
        self._visualizer = visualizer
        self.name = name or self.name

    def visualize(self, packet: IMUPacket):
        if self.start_time == 0.0:
            self.start_time = packet.data[0].acceleroMeter.timestamp.get()

        acceleration_x = [el.acceleroMeter.x for el in packet.data]
        acceleration_z = [el.acceleroMeter.y for el in packet.data]
        acceleration_y = [el.acceleroMeter.z for el in packet.data]

        t_acceleration = [(el.acceleroMeter.timestamp.get() - self.start_time).total_seconds() for el in packet.data]

        # Keep only last 100 values
        if len(self.acceleration_buffer) > 100:
            self.acceleration_buffer.pop(0)

        self.acceleration_buffer.append([t_acceleration, acceleration_x, acceleration_y, acceleration_z])

        gyroscope_x = [el.gyroscope.x for el in packet.data]
        gyroscope_y = [el.gyroscope.y for el in packet.data]
        gyroscope_z = [el.gyroscope.z for el in packet.data]

        t_gyroscope = [(el.gyroscope.timestamp.get() - self.start_time).total_seconds() for el in packet.data]

        # Keep only last 100 values
        if len(self.gyroscope_buffer) > 100:
            self.gyroscope_buffer.pop(0)

        self.gyroscope_buffer.append([t_gyroscope, gyroscope_x, gyroscope_y, gyroscope_z])

        # Plot acceleration
        for i in range(3):
            self.acceleration_lines[i].set_xdata([el[0] for el in self.acceleration_buffer])
            self.acceleration_lines[i].set_ydata([el[i + 1] for el in self.acceleration_buffer])

        self.axes[0].set_xlim(self.acceleration_buffer[0][0][0], t_acceleration[-1])
        self.axes[0].set_ylim(-20, 20)

        # Plot gyroscope
        for i in range(3):
            self.gyroscope_lines[i].set_xdata([el[0] for el in self.gyroscope_buffer])
            self.gyroscope_lines[i].set_ydata([el[i + 1] for el in self.gyroscope_buffer])

        self.axes[1].set_xlim(self.gyroscope_buffer[0][0][0], t_acceleration[-1])
        self.axes[1].set_ylim(-20, 20)

        self.fig.canvas.draw()

        # Convert plot to numpy array
        img = np.fromstring(self.fig.canvas.tostring_rgb(), dtype=np.uint8, sep='')
        img = img.reshape(self.fig.canvas.get_width_height()[::-1] + (3,))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        packet.frame = img
        self._visualizer.draw(packet.frame)

        if self.callback:  # Don't display frame, call the callback
            self.callback(packet)
        else:
            cv2.imshow(self.name, packet.frame)

    def xstreams(self) -> List[StreamXout]:
        return [self.imu_out]

    def newMsg(self, name: str, msg: dai.IMUData) -> None:
        if name not in self._streams:
            return

        if self.queue.full():
            self.queue.get()  # Get one, so queue isn't full

        packet = IMUPacket(msg.packets)

        self.queue.put(packet, block=False)
