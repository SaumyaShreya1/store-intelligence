"""
scripts/gen_test_video.py

Generates a synthetic grayscale video with a moving white rectangle,
used as a lightweight fixture in CI to smoke-test the detection pipeline
without needing real camera footage.

Usage
-----
python scripts/gen_test_video.py --frames 60 --output /tmp/test_cam.mp4
"""

import argparse
import cv2
import numpy as np


def generate(frames: int, output: str, width: int = 640, height: int = 480, fps: int = 25):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output, fourcc, fps, (width, height))

    for i in range(frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Move a white rectangle across the frame
        x = int((i / frames) * (width - 80))
        y = height // 2 - 40
        cv2.rectangle(frame, (x, y), (x + 60, y + 80), (255, 255, 255), -1)
        writer.write(frame)

    writer.release()
    print(f"[gen_test_video] Written {frames} frames → {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--output", default="/tmp/test_cam.mp4")
    p.add_argument("--width",  type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps",    type=int, default=25)
    args = p.parse_args()
    generate(args.frames, args.output, args.width, args.height, args.fps)
