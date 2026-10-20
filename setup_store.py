import os
import yaml
import argparse
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# Unbind 's' from Matplotlib's default "Save Figure PNG" shortcut so we can use it to Save & Quit
if 's' in mpl.rcParams['keymap.save']:
    mpl.rcParams['keymap.save'].remove('s')

def write_box_obj(f, vmin, vmax, v_offset):
    """Writes a 3D axis-aligned bounding box to an OBJ file."""
    x0, y0, z0 = vmin
    x1, y1, z1 = vmax
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)
    ]
    for v in verts:
        f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
    faces = [
        (1,2,3,4), (5,8,7,6), (1,5,6,2),
        (2,6,7,3), (3,7,8,4), (5,1,4,8)
    ]
    for face in faces:
        idx = [i + v_offset for i in face]
        f.write(f"f {idx[0]} {idx[1]} {idx[2]} {idx[3]}\n")
    return v_offset + 8

def generate_store_mesh(cfg):
    os.makedirs(os.path.dirname(cfg['store']['mesh_path']), exist_ok=True)
    W, L, H = cfg['store']['width'], cfg['store']['length'], cfg['store']['height']
    
    with open(cfg['store']['mesh_path'], 'w') as f:
        f.write("# Procedural Grocery Store Layout\n")
        v_off = 0
        # Floor & Ceiling
        f.write("o Floor\n")
        v_off = write_box_obj(f, [0, 0, -0.1], [W, L, 0], v_off)
        f.write("o Ceiling\n")
        v_off = write_box_obj(f, [0, 0, H], [W, L, H + 0.15], v_off)
        # Perimeter Walls (North, South, East, West)
        f.write("o Walls\n")
        v_off = write_box_obj(f, [0, -0.2, 0], [W, 0, H], v_off)
        v_off = write_box_obj(f, [0, L, 0], [W, L+0.2, H], v_off)
        v_off = write_box_obj(f, [-0.2, 0, 0], [0, L, H], v_off)
        v_off = write_box_obj(f, [W, 0, 0], [W+0.2, L, H], v_off)
        # Gondola Shelving Aisles
        for idx, (x0, y0, x1, y1) in enumerate(cfg['store']['aisles']):
            f.write(f"o Shelf_Aisle_{idx+1}\n")
            v_off = write_box_obj(f, [x0, y0, 0], [x1, y1, 2.1], v_off)
        # Checkout Counter
        checkouts = cfg['store'].get('checkouts', [cfg['store'].get('checkout', [33.0, 4.0])])
        for idx, (cx, cy) in enumerate(checkouts):
            f.write(f"o Checkout_Counter_{idx+1}\n")
            v_off = write_box_obj(f, [cx-0.6, cy-0.9, 0], [cx+0.6, cy+0.9, 1.0], v_off)

    print(f"[+] Wrote 3D grocery store mesh to {cfg['store']['mesh_path']}")

def next_camera_id(cameras):
    """Generates a non-colliding camera ID."""
    existing_ids = {c['id'] for c in cameras}
    idx = 1
    while True:
        candidate = f"CAM_{idx:02d}_USER"
        if candidate not in existing_ids:
            return candidate
        idx += 1

def launch_camera_gui(cfg_path, cfg):
    fig, ax = plt.subplots(figsize=(11, 8))
    W, L = cfg['store']['width'], cfg['store']['length']
    state = {
        'press_pt': None,
        'save_requested': False
    }

    def redraw():
        ax.clear()
        ax.set_xlim(-1, W + 1)
        ax.set_ylim(-1, L + 1)
        ax.set_aspect('equal')
        ax.set_title(
            "L-Click & Drag: Add | R-Click: Delete | 'u': Undo | 'c': Clear | 's': SAVE & QUIT | Close/Esc: CANCEL",
            fontsize=9.5, fontweight='bold'
        )
        ax.grid(True, linestyle='--', alpha=0.4)

        # Draw floor & aisles
        ax.add_patch(Rectangle((0, 0), W, L, fill=False, edgecolor='black', lw=2))
        for x0, y0, x1, y1 in cfg['store']['aisles']:
            ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, color='#8c8c8c', alpha=0.8))

        # Draw Entrance & Checkout markers
        ex, ey = cfg['store']['entrance']
        ax.plot(ex, ey, 'g^', markersize=10, label='Entrance')
        checkouts = cfg['store'].get('checkouts', [cfg['store'].get('checkout', [33.0, 4.0])])
        for idx, (cx, cy) in enumerate(checkouts):
            ax.plot(cx, cy, 'mD', markersize=10, label=f'Checkout_{idx}')

        # Draw products
        for prod, pos in cfg['products'].items():
            if isinstance(pos, list) and len(pos) == 2:
                ax.plot(pos[0], pos[1], 'go', markersize=7)
                ax.text(pos[0]+0.3, pos[1], prod, fontsize=8, color='darkgreen')

        # Draw cameras
        for cam in cfg.get('cameras', []):
            loc, look = cam['location'], cam['look_at']
            color = 'blue' if cam['id'].endswith('_USER') else 'red'
            ax.annotate("", xy=(look[0], look[1]), xytext=(loc[0], loc[1]),
                        arrowprops=dict(arrowstyle="->", color=color, lw=1.8))
            ax.plot(loc[0], loc[1], 's', color=color, markersize=8)
            ax.text(loc[0], loc[1]+0.4, cam['id'], color=color, fontsize=8, weight='bold')

        fig.canvas.draw_idle()

    def on_press(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        # Left click (button 1): start placing camera
        if event.button == 1:
            state['press_pt'] = (event.xdata, event.ydata)
        # Right click (button 3): delete nearest camera within 1.5m radius
        elif event.button == 3:
            cams = cfg.get('cameras', [])
            if not cams:
                return
            click_xy = np.array([event.xdata, event.ydata])
            dists = [np.linalg.norm(click_xy - np.array(c['location'][:2])) for c in cams]
            min_idx = int(np.argmin(dists))
            if dists[min_idx] <= 1.5:
                removed = cams.pop(min_idx)
                print(f"[-] Removed camera: {removed['id']}")
                redraw()
            else:
                print("[!] Right-click closer to a camera square (within 1.5m) to remove it.")

    def on_release(event):
        if event.button == 1 and event.inaxes == ax and state['press_pt'] is not None:
            if event.xdata is None or event.ydata is None:
                state['press_pt'] = None
                return
            x0, y0 = state['press_pt']
            x1, y1 = event.xdata, event.ydata
            if np.hypot(x1 - x0, y1 - y0) < 0.2:
                x1, y1 = x0 + 2.0, y0 + 2.0

            cam_id = next_camera_id(cfg.setdefault('cameras', []))
            cfg['cameras'].append({
                'id': cam_id,
                'location': [round(float(x0), 2), round(float(y0), 2), 4.0],
                'look_at': [round(float(x1), 2), round(float(y1), 2), 1.0],
                'focal_length_mm': 3.2,
                'resolution': [1280, 720]
            })
            print(f"[+] Staged camera: {cam_id} at ({x0:.2f}, {y0:.2f}) -> ({x1:.2f}, {y1:.2f})")
            state['press_pt'] = None
            redraw()

    def on_key(event):
        cams = cfg.get('cameras', [])
        if event.key == 's':
            state['save_requested'] = True
            plt.close(fig)
        elif event.key in ('escape', 'q'):
            state['save_requested'] = False
            plt.close(fig)
        elif event.key in ('u', 'backspace') and cams:
            removed = cams.pop()
            print(f"[-] Undid/Removed last camera: {removed['id']}")
            redraw()
        elif event.key == 'c' and cams:
            cfg['cameras'] = []
            print("[-] Cleared all staged cameras.")
            redraw()

    fig.canvas.mpl_connect('button_press_event', on_press)
    fig.canvas.mpl_connect('button_release_event', on_release)
    fig.canvas.mpl_connect('key_press_event', on_key)

    redraw()
    plt.show()

    if state['save_requested']:
        with open(cfg_path, 'w') as f:
            yaml.dump(cfg, f, sort_keys=False)
        print(f"[+] Saved {len(cfg.get('cameras', []))} cameras to {cfg_path}")
    else:
        print("[!] GUI closed without pressing 's' — discarded camera changes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup 3D store mesh and manage CCTV cameras.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration")
    parser.add_argument("--gui", action="store_true", help="Launch interactive 2D CCTV placement/removal GUI")
    parser.add_argument("--remove-cam", nargs="+", metavar="CAM_ID", help="Remove specific camera ID(s) via CLI")
    parser.add_argument("--clear-cams", action="store_true", help="Remove all cameras via CLI")
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        cfg = yaml.safe_load(f)

    # Handle CLI camera removal
    config_modified = False
    if args.clear_cams:
        cfg['cameras'] = []
        config_modified = True
        print("[-] Cleared all cameras from config.")
    elif args.remove_cam:
        to_remove = set(args.remove_cam)
        before_count = len(cfg.get('cameras', []))
        cfg['cameras'] = [c for c in cfg.get('cameras', []) if c['id'] not in to_remove]
        removed_count = before_count - len(cfg['cameras'])
        config_modified = True
        print(f"[-] Removed {removed_count} camera(s): {', '.join(to_remove)}")

    if config_modified:
        with open(args.config, 'w') as f:
            yaml.dump(cfg, f, sort_keys=False)

    generate_store_mesh(cfg)
    if args.gui:
        launch_camera_gui(args.config, cfg)