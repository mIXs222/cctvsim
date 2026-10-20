import os
import glob
import json
import math
import time
import socket
import struct
import argparse
import cv2
import numpy as np

class RealTimeNVRProcessor:
    """Applies configurable real-time NVR effects and Customer ID bounding boxes."""
    def __init__(self):
        self.maps = {}

    def process(self, bgr, cam_id, timestamp_str, mot_lines, state):
        h, w, _ = bgr.shape
        out = bgr.copy()

        # 1. Wide-angle barrel distortion (toggle with 'd')
        if state['distort']:
            if (w, h) not in self.maps:
                K = np.array([[w, 0, w / 2.0], [0, w, h / 2.0], [0, 0, 1]], dtype=np.float32)
                D = np.array([-0.18, 0.04, 0, 0], dtype=np.float32)
                map1, map2 = cv2.initUndistortRectifyMap(K, D, None, K, (w, h), cv2.CV_16SC2)
                self.maps[(w, h)] = (map1, map2)
            map1, map2 = self.maps[(w, h)]
            out = cv2.remap(out, map1, map2, interpolation=cv2.INTER_LINEAR)

        # 2. Sensor noise (toggle with 'n')
        if state['noise']:
            noise = np.random.normal(0, 4.0, out.shape).astype(np.int16)
            out = np.clip(out.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # 3. Customer ID 2D Bounding Boxes (toggle with 'b')
        if state['bboxes'] and mot_lines:
            for line in mot_lines:
                parts = line.split(",")
                if len(parts) >= 6:
                    pid = int(parts[1])
                    x, y, bw, bh = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                    color = ((pid * 67 + 40) % 255, (pid * 131 + 80) % 255, (pid * 199 + 30) % 255)
                    cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
                    label = f"ID:{pid:02d}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    y_lbl = max(th + 4, y)
                    cv2.rectangle(out, (x, y_lbl - th - 4), (x + tw + 6, y_lbl), color, -1)
                    cv2.putText(out, label, (x + 3, y_lbl - 3),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        # 4. OSD Timestamp & Camera ID Overlay (toggle with 't')
        if state['osd']:
            ts_label = f"{timestamp_str} | {cam_id}"
            cv2.rectangle(out, (10, 8), (465, 34), (0, 0, 0), -1)
            cv2.putText(out, ts_label, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)

        return out


def recv_exact(sock, num_bytes):
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            raise ConnectionError("Socket connection closed by Unity server.")
        buf.extend(chunk)
    return bytes(buf)


def build_grid_canvas(frames_dict, rows, cols, state, tile_w=480, tile_h=270):
    cam_ids = sorted(frames_dict.keys())
    if not cam_ids:
        return np.zeros((tile_h, tile_w, 3), dtype=np.uint8)

    # Check if a single camera is soloed ('1'-'8')
    solo_idx = state['solo_cam']
    if solo_idx is not None and 0 <= solo_idx < len(cam_ids):
        cid = cam_ids[solo_idx]
        canvas = cv2.resize(frames_dict[cid], (tile_w * 2, tile_h * 2))
    else:
        N = len(cam_ids)
        if rows <= 0 and cols <= 0:
            cols = 4 if N == 8 else max(1, math.ceil(math.sqrt(N)))
            rows = max(1, math.ceil(N / cols))
        elif rows <= 0:
            rows = max(1, math.ceil(N / cols))
        elif cols <= 0:
            cols = max(1, math.ceil(N / rows))

        canvas = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)
        for idx, cid in enumerate(cam_ids):
            if idx >= rows * cols:
                break
            r = idx // cols
            c = idx % cols
            resized = cv2.resize(frames_dict[cid], (tile_w, tile_h))
            canvas[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w] = resized

    # Draw bottom Hotkey Status Bar (toggle with 'h')
    if state['help']:
        bar_h = 32
        ch, cw, _ = canvas.shape
        bar = np.zeros((bar_h, cw, 3), dtype=np.uint8)
        bar[:] = (25, 25, 25)
        hud_text = (
            f"[B] ID BBoxes: {'ON' if state['bboxes'] else 'OFF'}  |  "
            f"[D] Lens Distort: {'ON' if state['distort'] else 'OFF'}  |  "
            f"[N] Noise: {'ON' if state['noise'] else 'OFF'}  |  "
            f"[T] OSD: {'ON' if state['osd'] else 'OFF'}  |  "
            f"[1-8] Solo Cam ([0] Grid)  |  "
            f"[SPACE] {'PAUSED' if state['paused'] else 'LIVE'}  |  "
            f"[S] Snapshot  |  [H] Hide Bar  |  [Q] Quit"
        )
        cv2.putText(bar, hud_text, (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 230, 180), 1, cv2.LINE_AA)
        canvas = np.vstack([canvas, bar])

    return canvas


def handle_hotkey(key, state, current_canvas):
    """Processes keyboard hotkeys for stream-ui."""
    if key in (ord('q'), 27):
        return False
    elif key == ord('b'):
        state['bboxes'] = not state['bboxes']
        print(f"[*] Customer ID Bounding Boxes: {'ON' if state['bboxes'] else 'OFF'}")
    elif key == ord('d'):
        state['distort'] = not state['distort']
        print(f"[*] Barrel Lens Distortion: {'ON' if state['distort'] else 'OFF'}")
    elif key == ord('n'):
        state['noise'] = not state['noise']
        print(f"[*] CMOS Sensor Noise: {'ON' if state['noise'] else 'OFF'}")
    elif key == ord('t'):
        state['osd'] = not state['osd']
        print(f"[*] OSD Timestamp Banner: {'ON' if state['osd'] else 'OFF'}")
    elif key == ord('h'):
        state['help'] = not state['help']
    elif key == ord(' '):
        state['paused'] = not state['paused']
        print(f"[*] Stream {'PAUSED' if state['paused'] else 'RESUMED'}")
    elif key == ord('0'):
        state['solo_cam'] = None
        print("[*] Restored Multi-Camera Grid View")
    elif ord('1') <= key <= ord('9'):
        state['solo_cam'] = key - ord('1')
        print(f"[*] Soloing Camera #{state['solo_cam'] + 1} (Press '0' for Grid)")
    elif key == ord('s') and current_canvas is not None:
        os.makedirs("output", exist_ok=True)
        snap_path = f"output/snapshot_{int(time.time())}.png"
        cv2.imwrite(snap_path, current_canvas)
        print(f"[+] Saved snapshot to {snap_path}")
    return True


def run_live_unity_stream(host, port, rows, cols, show_bboxes):
    processor = RealTimeNVRProcessor()
    raw_cache = {}
    processed_frames = {}
    state = {
        'bboxes': show_bboxes,
        'distort': True,
        'noise': False,
        'osd': True,
        'help': True,
        'paused': False,
        'solo_cam': None
    }

    print(f"[*] Connecting to Unity Real-Time CCTV Server at {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            sock.connect((host, port))
            break
        except ConnectionRefusedError:
            time.sleep(0.5)

    print("[+] Connected! Hotkeys: [B] Toggle BBoxes | [1-8] Solo Cam | [0] Grid | [D] Distort | [N] Noise | [SPACE] Pause | [S] Save | [Q] Quit")
    grid_img = None

    try:
        while True:
            lengths = recv_exact(sock, 8)
            header_len, jpg_len = struct.unpack("<II", lengths)
            header_json = recv_exact(sock, header_len).decode("utf-8")
            jpg_bytes = recv_exact(sock, jpg_len)

            if not state['paused']:
                meta = json.loads(header_json)
                cam_id = meta["cam_id"]
                ts = meta["timestamp"]
                mot_lines = meta.get("mot_annotations", [])

                arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                raw_cache[cam_id] = (bgr, ts, mot_lines)
                processed_frames[cam_id] = processor.process(bgr, cam_id, ts, mot_lines, state)
            else:
                # Re-render cached frames when paused so toggling 'b' updates boxes immediately
                for cid, (bgr, ts, mot_lines) in raw_cache.items():
                    processed_frames[cid] = processor.process(bgr, cid, ts, mot_lines, state)

            if processed_frames:
                grid_img = build_grid_canvas(processed_frames, rows, cols, state)
                cv2.imshow("Real-Time Multi-Camera CCTV Matrix (Unity -> Python)", grid_img)
                key = cv2.waitKey(1) & 0xFF
                if key != 255:
                    if not handle_hotkey(key, state, grid_img):
                        break
    finally:
        sock.close()
        cv2.destroyAllWindows()


def load_mot_file(mot_path):
    mot_by_frame = {}
    if os.path.exists(mot_path):
        with open(mot_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                f_idx = int(line.split(",")[0])
                mot_by_frame.setdefault(f_idx, []).append(line)
    return mot_by_frame


def run_mp4_fallback_grid(output_dir, rows, cols, show_bboxes):
    """Replays output/*_nvr.mp4 and overlays *_gt_mot.txt bounding boxes toggled via 'b'."""
    mp4_files = sorted(glob.glob(os.path.join(output_dir, "*_nvr.mp4")))
    if not mp4_files:
        print(f"[!] No *_nvr.mp4 files found in {output_dir}/.")
        return

    caps = {}
    mot_data = {}
    for p in mp4_files:
        cid = os.path.basename(p).replace("_nvr.mp4", "")
        caps[cid] = cv2.VideoCapture(p)
        mot_data[cid] = load_mot_file(os.path.join(output_dir, f"{cid}_gt_mot.txt"))

    state = {
        'bboxes': show_bboxes,
        'distort': False,
        'noise': False,
        'osd': False,
        'help': True,
        'paused': False,
        'solo_cam': None
    }
    processor = RealTimeNVRProcessor()
    frame_idx = 0
    cached_raw = {}
    grid_img = None

    while True:
        if not state['paused']:
            for cid, cap in caps.items():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame_idx = 0
                    ret, frame = cap.read()
                if ret:
                    cached_raw[cid] = frame
            frame_idx += 1

        frames = {}
        for cid, raw_f in cached_raw.items():
            mot_lines = mot_data[cid].get(frame_idx, [])
            frames[cid] = processor.process(raw_f, cid, "", mot_lines, state)

        if frames:
            grid_img = build_grid_canvas(frames, rows, cols, state)
            cv2.imshow("Multi-Camera CCTV Matrix (Replay Mode)", grid_img)

        key = cv2.waitKey(33) & 0xFF
        if key != 255:
            if not handle_hotkey(key, state, grid_img):
                break

    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Python CCTV Stream Receiver & A-by-B Grid Visualizer")
    parser.add_argument("--mode", choices=["live", "replay"], default="live")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--rows", type=int, default=2, help="Grid rows A (default 2 for 2x4 8-camera grid)")
    parser.add_argument("--cols", type=int, default=4, help="Grid cols B (default 4 for 2x4 8-camera grid)")
    parser.add_argument("--no-bboxes", action="store_true", help="Start with 2D MOT bounding boxes hidden")
    args = parser.parse_args()

    if args.mode == "live":
        run_live_unity_stream(args.host, args.port, args.rows, args.cols, not args.no_bboxes)
    else:
        run_mp4_fallback_grid("output", args.rows, args.cols, not args.no_bboxes)