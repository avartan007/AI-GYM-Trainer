import logging
import os
import sys
import threading
import types
from pathlib import Path

# This project no longer uses OpenCV. MediaPipe's vision package, however, still
# does `import cv2` at import time (in drawing_utils), which loads cv2's bundled
# FFmpeg (libavdevice 61.x). PyAV/WebRTC loads its own FFmpeg (libavdevice 62.x),
# and on macOS having both registers duplicate Objective-C classes
# (AVFFrameReceiver / AVFAudioReceiver), which the loader warns can cause
# "mysterious crashes". Since we never call MediaPipe's drawing helpers, we stub
# cv2 out so its native libraries are never loaded.
if "cv2" not in sys.modules:
    sys.modules["cv2"] = types.ModuleType("cv2")

try:
    import av
except Exception:
    av = None

import numpy as np
import mediapipe as mp

try:
    from streamlit_webrtc import VideoProcessorBase
except Exception:
    class VideoProcessorBase:  # pragma: no cover - fallback used when WebRTC is unavailable
        pass

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

try:
    from detectors.squat import SquatDetector
    from detectors.pushup import PushUpDetector
    from detectors.biceps_curl import BicepsCurlDetector
    from detectors.shoulder_press import ShoulderPressDetector
    from detectors.lunges import LungesDetector
except ImportError:
    from MainApp.detectors.squat import SquatDetector
    from MainApp.detectors.pushup import PushUpDetector
    from MainApp.detectors.biceps_curl import BicepsCurlDetector
    from MainApp.detectors.shoulder_press import ShoulderPressDetector
    from MainApp.detectors.lunges import LungesDetector

from services.config.workout_config import POSE_CONNECTIONS

logger = logging.getLogger(__name__)


class VideoProcessorClass(VideoProcessorBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_metrics = None
        self._exercise_type = "Squats"

        # Dynamically resolve model path regardless of current working directory
        base_dir = Path(__file__).resolve().parent.parent.parent
        possible_paths = [
            base_dir / "ml_models" / "pose_landmarker_full.task",
            Path(os.getcwd()) / "ml_models" / "pose_landmarker_full.task",
            Path(os.getcwd()) / "MainApp" / "ml_models" / "pose_landmarker_full.task",
        ]
        model_path = None
        for p in possible_paths:
            if p.exists():
                model_path = str(p)
                break
        if not model_path:
            model_path = str(base_dir / "ml_models" / "pose_landmarker_full.task")

        base_option = python.BaseOptions(model_asset_path=model_path)

        options = vision.PoseLandmarkerOptions(
            base_options=base_option,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.7,
            min_pose_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            output_segmentation_masks=False
        )

        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        self._detectors = {
            "Squats": SquatDetector(),
            "Push-ups": PushUpDetector(),
            "Biceps Curls (Dumbbell)": BicepsCurlDetector(),
            "Shoulder Press": ShoulderPressDetector(),
            "Lunges": LungesDetector(),
        }

        self._frame_timestamps_ms = 0
    
    def reset(self, exercise_type=None):
        with self._lock:
            self._latest_metrics = None
            if exercise_type and exercise_type in self._detectors:
                self._detectors[exercise_type].reset()
            else:
                for detector in self._detectors.values():
                    detector.reset()

    def set_latest_metrics(self, metrics):
        with self._lock:
            self._latest_metrics = metrics.copy()

    def get_latest_metrics(self):
        with self._lock:
            return None if self._latest_metrics is None else self._latest_metrics.copy()
        
    def set_exercise(self, exercise_type):
        with self._lock:
            if self._exercise_type != exercise_type:
                self._exercise_type = exercise_type
                if exercise_type in self._detectors:
                    self._detectors[exercise_type].reset()

    def get_exercise(self):
        with self._lock:
            return self._exercise_type
        
    def _draw_skeleton(self, img, landmarks):
        h, w = img.shape[:2]

        for start_idx, end_idx in POSE_CONNECTIONS:
            p1 = landmarks[start_idx]
            p2 = landmarks[end_idx]

            if p1.visibility > 0.7 and p2.visibility > 0.7:
                self._draw_line(
                    img,
                    (int(p1.x * w), int(p1.y * h)),
                    (int(p2.x * w), int(p2.y * h)),
                    (0, 255, 0),
                    8,
                )
        
        for lm in landmarks:
            if lm.visibility > 0.7:
                # RGB buffer: (0, 0, 255) renders as blue, matching the old cv2/BGR look.
                self._draw_circle(img, (int(lm.x * w), int(lm.y * h)), 8, (0, 0, 255))

    @staticmethod
    def _draw_line(img, start, end, color, width):
        x1, y1 = start
        x2, y2 = end
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        xs = np.linspace(x1, x2, steps + 1).astype(int)
        ys = np.linspace(y1, y2, steps + 1).astype(int)
        radius = max(1, width // 2)
        for x, y in zip(xs, ys):
            VideoProcessorClass._draw_circle(img, (x, y), radius, color)

    @staticmethod
    def _draw_circle(img, center, radius, color):
        x, y = center
        height, width = img.shape[:2]
        left, right = max(0, x - radius), min(width, x + radius + 1)
        top, bottom = max(0, y - radius), min(height, y + radius + 1)
        yy, xx = np.ogrid[top:bottom, left:right]
        mask = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
        img[top:bottom, left:right][mask] = color
            
    def _draw_no_pose_warnings(self, img):
        height, width = img.shape[:2]
        self._draw_line(img, (20, 20), (min(width - 1, 420), 20), (0, 255, 0), 4)
        self._draw_line(img, (20, min(height - 1, 70)), (min(width - 1, 520), min(height - 1, 70)), (0, 255, 0), 4)

    def _draw_overlays(self, img, metrics, ex_type):
        if ex_type == "Squats":
            self._draw_squats_overlays(img, metrics)
        elif ex_type == "Push-ups":
            self._draw_pushup_overlays(img, metrics)
        elif ex_type == "Biceps Curls (Dumbbell)":
            self._draw_curl_overlays(img, metrics)
        elif ex_type == "Shoulder Press":
            self._draw_press_overlays(img, metrics)
        elif ex_type == "Lunges":
            self._draw_lunge_overlays(img, metrics)


    def _draw_squats_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._draw_line(img, (20, h - 20), (min(img.shape[1] - 1, 260), h - 20), (0, 255, 0), 4)
    
    def _draw_pushup_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._draw_line(img, (20, h - 20), (min(img.shape[1] - 1, 360), h - 20), (0, 255, 0), 4)

    def _draw_curl_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._draw_line(img, (20, h - 20), (min(img.shape[1] - 1, 300), h - 20), (0, 255, 0), 4)

    def _draw_press_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._draw_line(img, (20, h - 20), (min(img.shape[1] - 1, 360), h - 20), (0, 255, 0), 4)

    def _draw_lunge_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._draw_line(img, (20, h - 20), (min(img.shape[1] - 1, 300), h - 20), (0, 255, 0), 4)

    def recv(self, frame):
        try:
            # WebRTC hands us frames in the decoder's native format (usually
            # yuv420p). Request RGB explicitly so the array is always a 3-channel
            # image that MediaPipe and our overlay drawing can work with.
            image = frame.to_ndarray(format="rgb24")

            # Drop any alpha channel, then mirror horizontally for a natural
            # selfie view (landmarks are detected on this same mirrored image).
            if image.ndim == 3 and image.shape[2] == 4:
                image = image[:, :, :3]
            image = np.ascontiguousarray(image[:, ::-1])

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=image
            )

            self._frame_timestamps_ms += 30
            result = self._landmarker.detect_for_video(mp_image, self._frame_timestamps_ms)

            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]

                self._draw_skeleton(image, landmarks)

                ex_type = self.get_exercise()

                detector = self._detectors.get(ex_type)

                if detector:
                    metrics = detector.process(landmarks)

                    metrics["pose_detected"] = True

                    self._draw_overlays(image, metrics, ex_type)

                    self.set_latest_metrics(metrics)
            else:
                self._draw_no_pose_warnings(image)
                
                with self._lock:
                    if self._latest_metrics is not None:
                        self._latest_metrics["pose_detected"] = False
                    else:
                        self._latest_metrics = {"pose_detected": False}

            # Return frame in RGB24 format
            return av.VideoFrame.from_ndarray(image, format="rgb24")
        except Exception:
            # Fallback: return the original frame if processing fails, but make
            # the failure visible instead of silently dropping all overlays.
            logger.exception("Pose processing failed; returning the original frame")
            return frame
    