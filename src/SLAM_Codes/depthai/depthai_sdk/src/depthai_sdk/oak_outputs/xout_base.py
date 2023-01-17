from abc import ABC, abstractmethod
from queue import Empty, Queue
from typing import List, Callable

import depthai as dai

from depthai_sdk.oak_outputs.fps import FPS
from depthai_sdk.visualize import Visualizer


class StreamXout:
    stream: dai.Node.Output
    name: str  # XLinkOut stream name
    friendly_name: str = None  # Used for eg. recording to a file

    def __init__(self, id: int, out: dai.Node.Output):
        self.stream = out
        self.name = f"{str(id)}_{out.name}"
        self.friendly_name = None


class ReplayStream(StreamXout):
    def __init__(self, name: str):
        self.name = name


class XoutBase(ABC):
    callback: Callable  # User defined callback. Called either after visualization (if vis=True) or after syncing.
    queue: Queue  # Queue to which synced Packets will be added. Main thread will get these
    _streams: List[str]  # Streams to listen for
    _visualizer: Visualizer = None
    _fps: FPS
    name: str  # Other Xouts will override this

    def __init__(self) -> None:
        self._streams = [xout.name for xout in self.xstreams()]


    _packet_name: str = None
    def get_packet_name(self) -> str:
        if self._packet_name is None:
            self._packet_name = ";".join([xout.name for xout in self.xstreams()])
        return self._packet_name

    @abstractmethod
    def xstreams(self) -> List[StreamXout]:
        raise NotImplementedError()

    def setup_base(self, callback: Callable):
        # Gets called when initializing
        self.queue = Queue(maxsize=10)
        self.callback = callback

    def start_fps(self):
        self._fps = FPS()

    @abstractmethod
    def newMsg(self, name: str, msg) -> None:
        raise NotImplementedError()

    @abstractmethod
    def visualize(self, packet) -> None:
        raise NotImplementedError()

    # This approach is used as some functions (eg. imshow()) need to be called from
    # main thread, and calling them from callback thread wouldn't work.
    def checkQueue(self, block=False) -> None:
        """
        Checks queue for any available messages. If available, call callback. Non-blocking by default.
        """
        try:
            packet = self.queue.get(block=block)
            if packet is not None:
                self._fps.next_iter()
                if self._visualizer:
                    try:
                        self._visualizer.frame_shape = packet.frame.shape
                    except AttributeError:
                        pass  # Not all packets have frame attribute

                    self.visualize(packet)
                else:
                    # User defined callback
                    self.callback(packet)
        except Empty:  # Queue empty
            pass
