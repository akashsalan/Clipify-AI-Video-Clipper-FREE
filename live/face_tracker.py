"""Face Tracker and Camera Reframer for Clipify AI Live Studio.

Performs smooth horizontal tracking across video clips to produce stable,
jitter-free vertical 9:16 reframing centered on the active subject.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

logger = logging.getLogger("clipify.live.tracker")


class FaceTracker:
    """Tracks subjects across video frames and produces stabilized crop windows."""

    def __init__(
        self,
        smoothing_alpha: float = 0.35,
        deadzone_ratio: float = 0.05,
        target_aspect_w: int = 9,
        target_aspect_h: int = 16,
    ):
        self.smoothing_alpha = smoothing_alpha
        self.deadzone_ratio = deadzone_ratio
        self.target_aspect_w = target_aspect_w
        self.target_aspect_h = target_aspect_h
        self.smoothed_center = 0.5
        self._cv2 = None
        self._haar = None
        self._init_cv()

    def _init_cv(self) -> None:
        try:
            import cv2
            self._cv2 = cv2
            haar_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(haar_path):
                self._haar = cv2.CascadeClassifier(haar_path)
        except Exception as e:
            logger.warning("OpenCV face tracker init warning: %s", e)

    def update_smoothed_center(self, target_cx: float) -> float:
        """Update and return the smoothed center with deadzone & EMA smoothing."""
        diff = abs(target_cx - self.smoothed_center)
        if diff > self.deadzone_ratio:
            self.smoothed_center = round(
                self.smoothed_center * (1.0 - self.smoothing_alpha) + target_cx * self.smoothing_alpha,
                4,
            )
        return self.smoothed_center

    def track_primary_face(
        self,
        video_path: Union[str, Path],
        source_w: int = 1920,
        source_h: int = 1080,
        sample_interval_sec: float = 0.5,
    ) -> List[dict[str, float]]:
        """Sample video frames and return list of smoothed face centroids."""
        p = Path(video_path)
        if not self._cv2 or not p.exists():
            return []

        cv2 = self._cv2
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            return []

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        step_frames = max(1, int(fps * sample_interval_sec))

        raw_positions: List[dict[str, float]] = []

        try:
            current_frame = 0
            while current_frame < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                sec = round(current_frame / fps, 2)
                cx = self._find_primary_face_cx(frame)
                if cx is not None:
                    raw_positions.append({"time": sec, "cx": cx})

                current_frame += step_frames
        finally:
            cap.release()

        if not raw_positions:
            return []

        # Smooth positions with a deadzone filter and EMA
        smoothed: List[dict[str, float]] = []
        self.smoothed_center = raw_positions[0]["cx"]

        for item in raw_positions:
            sm_cx = self.update_smoothed_center(item["cx"])
            smoothed.append({"time": item["time"], "cx": sm_cx})

        return smoothed

    def _find_primary_face_cx(self, frame) -> Optional[float]:
        """Find the most prominent face center in a frame."""
        cv2 = self._cv2
        h, w = frame.shape[:2]

        scale = min(1.0, 480.0 / max(1, w))
        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1.0 else frame
        sw = small.shape[1]

        if self._haar is not None:
            try:
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = self._haar.detectMultiScale(gray, 1.15, 4, minSize=(25, 25))
                if len(faces) > 0:
                    best = max(faces, key=lambda f: f[2] * f[3])
                    cx = (best[0] + best[2] / 2.0) / sw
                    return round(cx, 3)
            except Exception:
                pass

        return None

    def compute_static_crop(
        self,
        source: Union[str, Path, int],
        source_h: Optional[int] = None,
        target_w: int = 1080,
        target_h: int = 1920,
        face_cx: Optional[float] = None,
    ) -> Tuple[float, float, float, float]:
        """Compute normalized 9:16 crop box (nx, ny, nw, nh).

        Accepts either:
        - compute_static_crop(video_path) -> runs quick sample and returns normalized (nx, ny, nw, nh)
        - compute_static_crop(source_w, source_h, target_w, target_h, face_cx) -> returns normalized (nx, ny, nw, nh)
        """
        if isinstance(source, (str, Path)) and source_h is None:
            # Video path supplied
            p = Path(source)
            positions = self.track_primary_face(p, sample_interval_sec=0.8)
            cx = positions[len(positions) // 2]["cx"] if positions else 0.5
            sw, sh = 1920, 1080
            if self._cv2 and p.exists():
                cap = self._cv2.VideoCapture(str(p))
                if cap.isOpened():
                    sw = int(cap.get(self._cv2.CAP_PROP_FRAME_WIDTH) or 1920)
                    sh = int(cap.get(self._cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
                    cap.release()
        else:
            sw = int(source)
            sh = int(source_h or 1080)
            cx = float(face_cx if face_cx is not None else 0.5)

        # 9:16 vertical crop width inside 16:9 canvas
        crop_w = sh * (target_w / target_h)
        crop_h = float(sh)

        desired_x = cx * sw - crop_w / 2.0
        final_x = max(0.0, min(float(sw - crop_w), desired_x))
        final_y = 0.0

        # Return normalized coordinates (0..1)
        return (
            round(final_x / sw, 4),
            round(final_y / sh, 4),
            round(crop_w / sw, 4),
            round(crop_h / sh, 4),
        )
