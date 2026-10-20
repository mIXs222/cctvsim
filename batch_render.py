import os
import json
import yaml
import subprocess

CHUNK_SIZE = 40

def main():
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    with open("trajectories.json", "r") as f:
        traj_data = json.load(f)

    total_frames = traj_data['total_frames']
    cameras = [cam['id'] for cam in cfg['cameras']]

    for start_f in range(0, total_frames, CHUNK_SIZE):
        end_f = min(start_f + CHUNK_SIZE, total_frames)
        
        # 1. OS-Level Resumability: Check if chunk is fully rendered BEFORE booting Blender
        needs_render = False
        for cam_id in cameras:
            out_dir = os.path.join("output", cam_id)
            for idx in range(start_f, end_f):
                if not os.path.exists(os.path.join(out_dir, f"{idx}.hdf5")):
                    needs_render = True
                    break
            if needs_render:
                break
        
        if not needs_render:
            print(f"[*] Skipping chunk {start_f}-{end_f-1} (already rendered)")
            continue
            
        print(f"\n=======================================================")
        print(f"[*] Spawning fresh Blender process for frames {start_f} to {end_f-1}")
        print(f"=======================================================\n")
        
        # Pass chunk boundaries via environment variables to BlenderProc
        env = os.environ.copy()
        env["CHUNK_START"] = str(start_f)
        env["CHUNK_END"] = str(end_f)
        
        # 2. Spawn BlenderProc as an isolated subprocess
        result = subprocess.run(["blenderproc", "run", "render_cctv.py"], env=env)
        
        if result.returncode != 0:
            print(f"[!] Blender crashed or was interrupted on chunk {start_f}-{end_f-1}. Exiting.")
            break

if __name__ == "__main__":
    main()