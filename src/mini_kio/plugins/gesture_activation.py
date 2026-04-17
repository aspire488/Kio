import time
import math
import cv2
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.event_bus as event_bus


def dist(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def is_fist(hand_landmarks, wrist):
    """Detect closed fist using fingertip distance from wrist."""
    finger_tips = [4, 8, 12, 16, 20]  # thumb, index, middle, ring, pinky

    for tip_idx in finger_tips:
        tip = hand_landmarks.landmark[tip_idx]
        d = dist(tip, wrist)
        if d > 0.2:
            return False
    return True


def open_camera():
    """Try to open camera with reliable backends."""
    for backend in [cv2.CAP_DSHOW, cv2.CAP_ANY]:
        for index in [0, 1]:
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                print(f"[GESTURE] Camera opened (index={index}, backend={backend})")
                return cap
            cap.release()

    print("[GESTURE] ERROR: Could not open any camera")
    return None


def start_gesture_check(payload=None):
    import mediapipe as mp

    print("[GESTURE] Starting gesture activation...")

    cap = open_camera()
    if cap is None:
        return

    mp_hands = mp.solutions.hands
    hands_detector = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    start_time = time.time()
    fist_detected = False
    frame_count = 0
    hand_detected = False

    try:
        print("[GESTURE] Scanning for fist (5 second window)...")

        while time.time() - start_time < 5.0:
            ret, frame = cap.read()
            if not ret:
                print("[GESTURE] Frame read failed")
                break

            frame_count += 1

            # Show camera window
            cv2.imshow("KIO Gesture Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("[GESTURE] User pressed q to quit")
                break

            # Skip every other frame to reduce CPU
            if frame_count % 2 != 0:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands_detector.process(frame_rgb)

            if results.multi_hand_landmarks:
                if not hand_detected:
                    print("[GESTURE] Hand detected")
                    hand_detected = True

                for hand_landmarks in results.multi_hand_landmarks:
                    wrist = hand_landmarks.landmark[0]
                    if is_fist(hand_landmarks, wrist):
                        fist_detected = True
                        break

            if fist_detected:
                print("[GESTURE] Fist detected")
                print("[GESTURE] Activating KIO")
                event_bus.publish("ACTIVATE_KIO")
                break

            time.sleep(0.03)

        elapsed = time.time() - start_time
        if not fist_detected:
            print(
                f"[GESTURE] Activation window ended ({elapsed:.1f}s, {frame_count} frames)"
            )

    except Exception as e:
        print(f"[GESTURE] Error during gesture check: {e}")

    finally:
        print("[GESTURE] Cleaning up resources...")
        cap.release()
        try:
            cv2.destroyAllWindows()
        except:
            pass
        hands_detector.close()
        print("[GESTURE] Camera closed")


def init_on_startup(event=None):
    """Automatically trigger activation check on startup."""
    print("[GESTURE] Triggering initial activation check...")
    start_gesture_check()


def start_gesture_listener():
    """Start continuous gesture listening."""
    import threading
    import mediapipe as mp

    print("[GESTURE] Starting gesture listener...")

    cap = open_camera()
    if cap is None:
        print("[GESTURE] Could not start listener")
        return

    mp_hands = mp.solutions.hands
    hands_detector = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    def listen_loop():
        fist_detected = False
        hand_detected = False

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                cv2.imshow("KIO Gesture", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands_detector.process(frame_rgb)

                if results.multi_hand_landmarks:
                    if not hand_detected:
                        hand_detected = True

                    for hand_landmarks in results.multi_hand_landmarks:
                        wrist = hand_landmarks.landmark[0]
                        if is_fist(hand_landmarks, wrist):
                            if not fist_detected:
                                fist_detected = True
                                print("[GESTURE] Fist detected - ACTIVATING KIO")
                                event_bus.publish("ACTIVATE_KIO")
                                time.sleep(2)
                                fist_detected = False
                else:
                    hand_detected = False

                time.sleep(0.05)

        except Exception as e:
            print(f"[GESTURE] Listener error: {e}")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            hands_detector.close()

    thread = threading.Thread(target=listen_loop, daemon=True)
    thread.start()
    print("[GESTURE] Listener started")


def register_plugin(handlers, patterns):
    event_bus.subscribe("CHECK_ACTIVATION", start_gesture_check)
    event_bus.subscribe("startup", init_on_startup)
