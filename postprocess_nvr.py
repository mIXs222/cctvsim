import os
import glob
import json
import h5py
import yaml
import cv2
import numpy as np
from datetime import datetime, timedelta

def apply_cctv_artifacts(rgb, cam_id, frame_idx, fps):
    h, w, _ = rgb.shape
    # 1. Subtle radial barrel distortion (wide-angle CCTV lens)
    K = np.array([[w, 0, w/2], [0, w, h/2], [0, 0, 1]], dtype=np.float32)
    D = np.array([-0.18, 0.04, 0, 0], dtype=np.float32)
    warped = cv2.undistort(rgb, K, D)

    # 2. Sensor noise & slight chromatic desaturation
    noise = np.random.normal(0, 4.5, warped.shape).astype(np.int16)
    noisy = np.clip(warped.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 3. OSD Timestamp & Camera ID Overlay (handles >60s rollover)
    start_time = datetime(2026, 10, 16, 14, 20, 0)
    current_time = start_time + timedelta(seconds=frame_idx / fps)
    fractional = int((frame_idx / fps % 1) * 100)
    ts = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}.{fractional:02d} | {cam_id}"

    cv2.rectangle(noisy, (15, 12), (510, 42), (0, 0, 0), -1)
    cv2.putText(noisy, ts, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return noisy

def extract_mot_bboxes_from_seg(seg_mask, frame_idx):
    """Extracts [frame, person_id, x, y, w, h] MOTChallenge ground truth from instance masks."""
    annotations = []
    unique_ids = np.unique(seg_mask)
    for uid in unique_ids:
        if uid >= 100:  # Customer IDs start at 100
            person_id = int(uid - 100)
            ys, xs = np.where(seg_mask == uid)
            if len(xs) > 15:
                x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
                annotations.append(f"{frame_idx},{person_id},{x0},{y0},{x1-x0},{y1-y0},1,1,1.0")
    return annotations

def project_3d_bboxes_to_mot(cam, traj_data, frame_idx):
    """
    Fast analytical 3D-to-2D bounding box projection fallback when rendering with Eevee
    (without Cycles segmentation passes).
    """
    res_w, res_h = cam['resolution']
    fov_x = 2.0 * np.arctan(5.6 / (2.0 * cam['focal_length_mm']))
    fx = (res_w / 2.0) / np.tan(fov_x / 2.0)
    fy = fx
    cx, cy = res_w / 2.0, res_h / 2.0

    loc = np.array(cam['location'], dtype=float)
    look = np.array(cam['look_at'], dtype=float)
    forward = look - loc
    forward /= np.linalg.norm(forward)
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, world_up)
    if np.linalg.norm(right) < 1e-5:
        right = np.array([1.0, 0.0, 0.0])
    else:
        right /= np.linalg.norm(right)
    up = np.cross(right, forward)

    annotations = []
    f_str = str(frame_idx)
    for agent in traj_data.get('agents', []):
        if f_str not in agent['frames']:
            continue
        person_id = agent['id']
        x, y = agent['frames'][f_str]['pos']
        # 8 corners of human 3D bounding box (radius ~0.28m, height ~1.75m)
        r, h = 0.28, 1.75
        corners_3d = np.array([
            [x-r, y-r, 0], [x+r, y-r, 0], [x-r, y+r, 0], [x+r, y+r, 0],
            [x-r, y-r, h], [x+r, y-r, h], [x-r, y+r, h], [x+r, y+r, h]
        ])
        rel = corners_3d - loc
        z_cam = rel @ forward
        if np.all(z_cam <= 0.2):  # Behind camera
            continue
        valid = z_cam > 0.2
        rel = rel[valid]
        z_cam = z_cam[valid]
        x_cam = rel @ right
        y_cam = rel @ (-up)

        u = fx * (x_cam / z_cam) + cx
        v = fy * (y_cam / z_cam) + cy

        x0, y0 = int(np.clip(u.min(), 0, res_w - 1)), int(np.clip(v.min(), 0, res_h - 1))
        x1, y1 = int(np.clip(u.max(), 0, res_w - 1)), int(np.clip(v.max(), 0, res_h - 1))
        if (x1 - x0) > 8 and (y1 - y0) > 12:
            annotations.append(f"{frame_idx},{person_id},{x0},{y0},{x1-x0},{y1-y0},1,1,1.0")
    return annotations

def process_outputs():
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    traj_data = {}
    if os.path.exists("trajectories.json"):
        with open("trajectories.json", "r") as f:
            traj_data = json.load(f)

    fps = cfg['simulation']['fps']

    for cam in cfg['cameras']:
        cam_id = cam['id']
        h5_files = sorted(glob.glob(f"output/{cam_id}/*.hdf5"), key=lambda x: int(os.path.basename(x).split('.')[0]))
        if not h5_files:
            continue

        res_w, res_h = cam['resolution']
        mp4_path = f"output/{cam_id}_nvr.mp4"
        mot_path = f"output/{cam_id}_gt_mot.txt"
        writer = cv2.VideoWriter(mp4_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (res_w, res_h))
        mot_lines = []

        for idx, h5_path in enumerate(h5_files):
            with h5py.File(h5_path, 'r') as f:
                keys = list(f.keys())
                if not keys:
                    print(f"[!] Warning: {h5_path} is empty or corrupted. Skipping frame.")
                    continue
                
                # Support both 'colors' and 'image' keys depending on BlenderProc render settings
                key = 'colors' if 'colors' in f else ('image' if 'image' in f else keys[0])
                
                rgb = np.array(f[key])[:, :, ::-1] # RGB to BGR
                frame_bgr = apply_cctv_artifacts(rgb, cam_id, idx, fps)
                writer.write(frame_bgr)

                # Use segmentation mask if present; otherwise project 3D trajectories
                if 'category_id_segmaps' in f:
                    seg = np.array(f['category_id_segmaps'])
                    mot_lines.extend(extract_mot_bboxes_from_seg(seg, idx))
                elif 'instance_segmaps' in f:
                    seg = np.array(f['instance_segmaps'])
                    mot_lines.extend(extract_mot_bboxes_from_seg(seg, idx))
                elif traj_data:
                    mot_lines.extend(project_3d_bboxes_to_mot(cam, traj_data, idx))

        writer.release()
        with open(mot_path, "w") as f:
            f.write("\n".join(mot_lines))
        print(f"[+] Exported {mp4_path} and multi-object tracking GT {mot_path}")

if __name__ == "__main__":
    process_outputs()