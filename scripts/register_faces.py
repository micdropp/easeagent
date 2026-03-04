"""Batch face registration CLI tool.

Usage:
    # Register from an image file
    python scripts/register_faces.py --id emp_001 --image photo.jpg

    # Register from webcam (captures one frame)
    python scripts/register_faces.py --id emp_001 --webcam

    # Batch register from a directory of images (filename = employee_id)
    python scripts/register_faces.py --dir data/face_photos/
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import cv2
import numpy as np

from perception.face_recognizer import FaceRecognizer


async def register_from_image(
    recognizer: FaceRecognizer, employee_id: str, image_path: str
) -> bool:
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"[ERROR] Cannot read image: {image_path}")
        return False
    ok = await recognizer.register_face(employee_id, frame)
    if ok:
        print(f"[OK] Registered face for {employee_id} from {image_path}")
    else:
        print(f"[FAIL] No face detected in {image_path}")
    return ok


async def register_from_webcam(
    recognizer: FaceRecognizer, employee_id: str, device: int = 0
) -> bool:
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open webcam device {device}")
        return False

    print("Press SPACE to capture, ESC to cancel...")
    frame_to_use = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow("Register Face - Press SPACE to capture", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break
        if key == 32:  # SPACE
            frame_to_use = frame
            break

    cap.release()
    cv2.destroyAllWindows()

    if frame_to_use is None:
        print("[CANCEL] No frame captured")
        return False

    ok = await recognizer.register_face(employee_id, frame_to_use)
    if ok:
        print(f"[OK] Registered face for {employee_id} from webcam")
    else:
        print(f"[FAIL] No face detected in captured frame")
    return ok


async def register_from_directory(
    recognizer: FaceRecognizer, dir_path: str
) -> tuple[int, int]:
    p = Path(dir_path)
    if not p.is_dir():
        print(f"[ERROR] Not a directory: {dir_path}")
        return 0, 0

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [f for f in p.iterdir() if f.suffix.lower() in exts]
    if not images:
        print(f"[WARN] No image files found in {dir_path}")
        return 0, 0

    success = 0
    total = len(images)
    for img in sorted(images):
        employee_id = img.stem
        ok = await register_from_image(recognizer, employee_id, str(img))
        if ok:
            success += 1

    print(f"\nBatch result: {success}/{total} faces registered")
    return success, total


async def main() -> None:
    parser = argparse.ArgumentParser(description="EaseAgent face registration tool")
    parser.add_argument("--id", help="Employee ID to register")
    parser.add_argument("--image", help="Path to face image")
    parser.add_argument("--webcam", action="store_true", help="Capture from webcam")
    parser.add_argument(
        "--dir", help="Directory of images (filename stem = employee ID)"
    )
    parser.add_argument(
        "--model", default="buffalo_l", help="InsightFace model name"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.6, help="Recognition threshold"
    )
    args = parser.parse_args()

    recognizer = FaceRecognizer(model_name=args.model, threshold=args.threshold)
    await recognizer.load()

    if args.dir:
        await register_from_directory(recognizer, args.dir)
    elif args.id and args.image:
        await register_from_image(recognizer, args.id, args.image)
    elif args.id and args.webcam:
        await register_from_webcam(recognizer, args.id)
    else:
        parser.print_help()
        print(
            "\nExamples:\n"
            "  python scripts/register_faces.py --id emp_001 --image photo.jpg\n"
            "  python scripts/register_faces.py --id emp_001 --webcam\n"
            "  python scripts/register_faces.py --dir data/face_photos/\n"
        )

    await recognizer.unload()


if __name__ == "__main__":
    asyncio.run(main())
