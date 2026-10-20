import blenderproc as bproc
import os
import gc
import json
import yaml
import h5py
import glob
import tempfile
import numpy as np
import bpy


# Realistic clothing & skin color palettes
SHIRT_PALETTE = [
    (0.12, 0.18, 0.32), (0.45, 0.12, 0.14), (0.15, 0.28, 0.18),
    (0.75, 0.73, 0.68), (0.22, 0.22, 0.24), (0.55, 0.38, 0.24),
    (0.28, 0.42, 0.55), (0.62, 0.28, 0.20), (0.10, 0.10, 0.12),
    (0.48, 0.46, 0.35),
]

PANTS_PALETTE = [
    (0.10, 0.14, 0.24), (0.12, 0.12, 0.13), (0.48, 0.40, 0.30),
    (0.25, 0.26, 0.28), (0.22, 0.32, 0.46),
]

SKIN_PALETTE = [
    (0.88, 0.72, 0.62), (0.78, 0.58, 0.45), (0.62, 0.44, 0.32),
    (0.42, 0.28, 0.20), (0.92, 0.78, 0.68),
]

HAIR_PALETTE = [
    (0.05, 0.05, 0.05), (0.18, 0.11, 0.06), (0.35, 0.22, 0.12),
    (0.55, 0.42, 0.22), (0.45, 0.45, 0.45),
]

def make_solid_mat(name, rgba, roughness=0.7, metallic=0.0):
    mat = bproc.material.create(name)
    mat.set_principled_shader_value("Base Color", list(rgba))
    mat.set_principled_shader_value("Roughness", roughness)
    mat.set_principled_shader_value("Metallic", metallic)
    return mat

def make_tiled_floor_material():
    mat = bproc.material.create("Supermarket_Tiled_Floor")
    nodes, links = mat.nodes, mat.links
    bsdf = mat.get_the_one_node_with_type("BsdfPrincipled")

    tex_coord = nodes.new("ShaderNodeTexCoord")
    checker = nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 36.0
    checker.inputs["Color1"].default_value = (0.68, 0.67, 0.64, 1.0)
    checker.inputs["Color2"].default_value = (0.54, 0.53, 0.50, 1.0)

    links.new(tex_coord.outputs["Generated"], checker.inputs["Vector"])
    links.new(checker.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.25
    return mat

def make_wall_material():
    mat = bproc.material.create("Store_Wall_Mat")
    nodes, links = mat.nodes, mat.links
    bsdf = mat.get_the_one_node_with_type("BsdfPrincipled")

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 4.0

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.76, 0.74, 0.70, 1.0)
    ramp.color_ramp.elements[1].color = (0.84, 0.82, 0.78, 1.0)

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat

def build_textured_grocery_store(cfg):
    """Builds store architecture and joins static shelf meshes to keep Blender scene graph tiny."""
    W, L, H = cfg['store']['width'], cfg['store']['length'], cfg['store']['height']

    floor_mat = make_tiled_floor_material()
    wall_mat = make_wall_material()
    shelf_metal_mat = make_solid_mat("Shelf_Metal", (0.22, 0.23, 0.25, 1.0), roughness=0.4, metallic=0.6)
    counter_mat = make_solid_mat("Checkout_Mat", (0.18, 0.18, 0.20, 1.0), roughness=0.3, metallic=0.3)

    # 1. Tiled Floor
    floor = bproc.object.create_primitive("CUBE", scale=[W/2, L/2, 0.05], location=[W/2, L/2, -0.05])
    floor.set_name("Store_Floor")
    floor.set_cp("category_id", 1)
    floor.replace_materials(floor_mat)

    # 1B. Industrial Ceiling Slab + Steel Roof Trusses (Inside build_textured_grocery_store)
    ceiling_mat = make_solid_mat("Store_Ceiling_Mat", (0.32, 0.33, 0.35, 1.0), roughness=0.8, metallic=0.3)
    ceiling = bproc.object.create_primitive("CUBE", scale=[W/2, L/2, 0.08], location=[W/2, L/2, H + 0.08])
    ceiling.set_name("Store_Ceiling")
    ceiling.set_cp("category_id", 2)
    ceiling.replace_materials(ceiling_mat)

    for tx in np.linspace(4.0, W - 4.0, 7):
        truss = bproc.object.create_primitive("CUBE", scale=[0.12, L/2, 0.12], location=[tx, L/2, H - 0.12])
        truss.replace_materials(shelf_metal_mat)
        static_shelf_objs.append(truss)

    # 2. Perimeter Walls
    wall_specs = [
        ("Wall_South", [W/2, -0.1, H/2], [W/2, 0.1, H/2]),
        ("Wall_North", [W/2, L+0.1, H/2], [W/2, 0.1, H/2]),
        ("Wall_West",  [-0.1, L/2, H/2], [0.1, L/2, H/2]),
        ("Wall_East",  [W+0.1, L/2, H/2], [0.1, L/2, H/2]),
    ]
    for w_name, loc, scale in wall_specs:
        w_obj = bproc.object.create_primitive("CUBE", scale=scale, location=loc)
        w_obj.set_name(w_name)
        w_obj.set_cp("category_id", 2)
        w_obj.replace_materials(wall_mat)

    # 3. Gondola Shelving Aisles + Merged Product Row Blocks (avoids 500+ tiny objects)
    prod_colors = [
        (0.75, 0.15, 0.12, 1.0), (0.15, 0.45, 0.78, 1.0), (0.85, 0.65, 0.12, 1.0),
        (0.20, 0.62, 0.28, 1.0), (0.82, 0.38, 0.12, 1.0), (0.55, 0.22, 0.65, 1.0)
    ]
    prod_mats = [make_solid_mat(f"Prod_Mat_{i}", c, roughness=0.5) for i, c in enumerate(prod_colors)]

    rng = np.random.default_rng(101)
    static_shelf_objs = []

    for idx, (x0, y0, x1, y1) in enumerate(cfg['store']['aisles']):
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        sx, sy = (x1 - x0) / 2.0, (y1 - y0) / 2.0

        spine = bproc.object.create_primitive("CUBE", scale=[0.08, sy, 1.05], location=[cx, cy, 1.05])
        spine.replace_materials(shelf_metal_mat)
        static_shelf_objs.append(spine)

        for z_tier in [0.25, 0.75, 1.25, 1.75]:
            tier = bproc.object.create_primitive("CUBE", scale=[sx, sy, 0.03], location=[cx, cy, z_tier])
            tier.replace_materials(shelf_metal_mat)
            static_shelf_objs.append(tier)

            # Use 3 longer product blocks per shelf side instead of dozens of tiny cubes
            for seg_idx, py in enumerate(np.linspace(y0 + 1.5, y1 - 1.5, 3)):
                for side in [-1, 1]:
                    px = cx + side * (sx * 0.55)
                    p_box = bproc.object.create_primitive(
                        "CUBE",
                        scale=[sx * 0.35, (sy / 3.4), 0.16],
                        location=[px, py, z_tier + 0.19]
                    )
                    p_box.replace_materials(prod_mats[rng.integers(0, len(prod_mats))])
                    static_shelf_objs.append(p_box)

    # Join all static shelf/product meshes into a single mesh to slash Blender depsgraph RAM
    if len(static_shelf_objs) > 1:
        main_shelf = static_shelf_objs[0]
        main_shelf.join_with_other_objects(static_shelf_objs[1:])
        main_shelf.set_name("Merged_Store_Shelves")
        main_shelf.set_cp("category_id", 3)

    # 4. 8 Checkout Counters
    checkouts = cfg['store'].get('checkouts', [cfg['store'].get('checkout', [33.0, 4.0])])
    for idx, (chk_x, chk_y) in enumerate(checkouts):
        counter = bproc.object.create_primitive("CUBE", scale=[0.6, 0.85, 0.48], location=[chk_x, chk_y, 0.48])
        counter.set_name(f"Checkout_Counter_{idx+1}")
        counter.set_cp("category_id", 5)
        counter.replace_materials(counter_mat)

def create_realistic_humanoid(agent_id, rng):
    """Creates a multi-part humanoid and merges its mesh parts so each customer is 1 Blender object."""
    height = float(rng.uniform(1.55, 1.92))
    scale_z = height / 1.72
    build = float(rng.uniform(0.85, 1.18))
    cat_id = 100 + agent_id

    shirt_mat = make_solid_mat(f"shirt_{agent_id}", (*SHIRT_PALETTE[rng.integers(len(SHIRT_PALETTE))], 1.0), roughness=0.85)
    pants_mat = make_solid_mat(f"pants_{agent_id}", (*PANTS_PALETTE[rng.integers(len(PANTS_PALETTE))], 1.0), roughness=0.90)
    skin_mat  = make_solid_mat(f"skin_{agent_id}",  (*SKIN_PALETTE[rng.integers(len(SKIN_PALETTE))], 1.0),  roughness=0.65)
    hair_mat  = make_solid_mat(f"hair_{agent_id}",  (*HAIR_PALETTE[rng.integers(len(HAIR_PALETTE))], 1.0),  roughness=0.90)

    parts = []
    for side in [-1, 1]:
        leg = bproc.object.create_primitive("CYLINDER", radius=0.085 * build, depth=0.76 * scale_z, vertices=12)
        leg.set_location([0.0, side * 0.10 * build, 0.38 * scale_z])
        leg.replace_materials(pants_mat)
        parts.append(leg)

    hips = bproc.object.create_primitive("CYLINDER", radius=0.17 * build, depth=0.18 * scale_z, vertices=12)
    hips.set_location([0.0, 0.0, 0.78 * scale_z])
    hips.replace_materials(pants_mat)
    parts.append(hips)

    torso = bproc.object.create_primitive("CYLINDER", radius=0.185 * build, depth=0.56 * scale_z, vertices=14)
    torso.set_scale([0.78, 1.15, 1.0])
    torso.set_location([0.0, 0.0, 1.12 * scale_z])
    torso.replace_materials(shirt_mat)
    parts.append(torso)

    for side in [-1, 1]:
        arm = bproc.object.create_primitive("CYLINDER", radius=0.055 * build, depth=0.54 * scale_z, vertices=10)
        arm.set_location([0.0, side * 0.24 * build, 1.10 * scale_z])
        arm.replace_materials(shirt_mat)
        parts.append(arm)

    head = bproc.object.create_primitive("SPHERE", radius=0.125, segments=12, ring_count=8)
    head.set_location([0.0, 0.0, 1.53 * scale_z])
    head.replace_materials(skin_mat)
    parts.append(head)

    hair = bproc.object.create_primitive("SPHERE", radius=0.132, segments=12, ring_count=8)
    hair.set_scale([1.02, 1.02, 0.65])
    hair.set_location([-0.01, 0.0, 1.58 * scale_z])
    hair.replace_materials(hair_mat)
    parts.append(hair)

    # Invisible root anchor at Z=0 so merged origin stays at floor level
    root = bproc.object.create_primitive("CUBE", scale=[0.005, 0.005, 0.005], location=[0, 0, 0])
    root.join_with_other_objects(parts)
    root.set_name(f"Customer_{agent_id:02d}")
    root.set_cp("category_id", cat_id)
    return root

def main():
    try:
        bproc.init()
    except RuntimeError:
        bproc.clean_up(clean_up_camera=True)

    # Disable Undo memory cache to prevent background RAM leaks
    bpy.context.preferences.edit.use_global_undo = False

    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    with open("trajectories.json", "r") as f:
        traj_data = json.load(f)

    total_frames = traj_data['total_frames']

    # Read chunk bounds (supports both OS-orchestrator and standalone native run)
    chunk_start = int(os.environ.get("CHUNK_START", 0))
    chunk_end = int(os.environ.get("CHUNK_END", 0))
    if chunk_end == 0:
        chunk_start = 0
        chunk_end = total_frames

    print(f"\n[*] Blender script active. Target frame range: {chunk_start} to {chunk_end-1}\n")

    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 32
    if hasattr(scene.eevee, "use_raytracing"):
        scene.eevee.use_raytracing = False

    build_textured_grocery_store(cfg)

    # Overhead Area Lights
    W, L, H = cfg['store']['width'], cfg['store']['length'], cfg['store']['height']
    for i, lx in enumerate(np.linspace(4.0, W - 4.0, 4)):
        for j, ly in enumerate(np.linspace(4.0, L - 4.0, 3)):
            light = bproc.types.Light()
            light.set_type("AREA")
            light.set_location([lx, ly, H - 0.15])
            light.set_energy(320)
            light.blender_obj.data.use_shadow = ((i + j) % 2 == 0)

    # Populate customer animations
    rng = np.random.default_rng(42)
    for agent in traj_data['agents']:
        aid = agent['id']
        cust_root = create_realistic_humanoid(aid, rng)
        stride_phase = float(rng.uniform(0, 2 * np.pi))

        for f_idx in range(chunk_start, chunk_end):
            f_str = str(f_idx)
            if f_str in agent['frames']:
                st = agent['frames'][f_str]
                x, y = st['pos']
                yaw = st['yaw']
                bob = 0.022 * abs(np.sin(f_idx * 0.65 + stride_phase)) if st['state'] == 'walking' else 0.0
                cust_root.set_location([x, y, bob], frame=f_idx)
                cust_root.set_rotation_euler([0.0, 0.0, yaw], frame=f_idx)
            else:
                cust_root.set_location([0.0, 0.0, -20.0], frame=f_idx)

    CHUNK_SIZE = 40
    cam_ob = bpy.context.scene.camera

    for cam in cfg['cameras']:
        cam_id = cam['id']
        res_w, res_h = cam['resolution']
        bproc.camera.set_resolution(res_w, res_h)

        fov_rad = 2.0 * np.arctan(5.6 / (2.0 * cam['focal_length_mm']))
        bproc.camera.set_intrinsics_from_blender_params(lens=fov_rad, lens_unit="FOV")

        loc = np.array(cam['location'])
        look = np.array(cam['look_at'])
        rot_mat = bproc.camera.rotation_from_forward_vec(look - loc, up_axis='Y')
        cam2world = bproc.math.build_transformation_mat(loc, rot_mat)

        if cam_ob.animation_data and cam_ob.animation_data.action:
            bpy.data.actions.remove(cam_ob.animation_data.action)

        # Set poses for all frames in our target range
        for f_idx in range(chunk_start, chunk_end):
            bproc.camera.add_camera_pose(cam2world, frame=f_idx)

        out_dir = os.path.join("output", cam_id)
        os.makedirs(out_dir, exist_ok=True)

        for start_f in range(chunk_start, chunk_end, CHUNK_SIZE):
            end_f = min(start_f + CHUNK_SIZE, chunk_end)

            # 1. Resumability / Skip Logic
            missing_frames = [
                idx for idx in range(start_f, end_f) 
                if not os.path.exists(os.path.join(out_dir, f"{idx}.hdf5"))
            ]
            
            if not missing_frames:
                print(f"[*] Skipping {cam_id} frames {start_f} to {end_f-1} (already rendered)")
                continue

            # 2. Isolate Render Layers (fixes Compositor node leaks)
            if scene.use_nodes and scene.node_tree:
                for node in list(scene.node_tree.nodes):
                    if node.type != 'R_LAYERS':
                        scene.node_tree.nodes.remove(node)

            # 3. Shrink timeline to only the missing frames
            actual_start_f = missing_frames[0]
            scene.frame_start = actual_start_f
            scene.frame_end = end_f  # Exclusive bound

            print(f"[*] Rendering {cam_id} frames {actual_start_f} to {end_f-1}...")
            data = bproc.renderer.render()

            colors = data.get('colors', [])
            for local_idx in range(len(colors)):
                global_idx = actual_start_f + local_idx
                h5_file = os.path.join(out_dir, f"{global_idx}.hdf5")
                tmp_file = h5_file + ".tmp"
                
                with h5py.File(tmp_file, 'w') as f:
                    for key, val in data.items():
                        if len(val) > local_idx:
                            try:
                                f.create_dataset(key, data=val[local_idx], compression='gzip')
                            except Exception:
                                f.create_dataset(key, data=val[local_idx])
                os.replace(tmp_file, h5_file)

            # --- 4. AGGRESSIVE MEMORY PURGE ---
            del data
            del colors
            gc.collect()

            # Purge internal image caches
            for img in list(bpy.data.images):
                if img.users == 0 or img.name in ['Render Result', 'Viewer Node']:
                    bpy.data.images.remove(img)

            # Force recursive C++ orphan deletion (Run 3x to clear linked trees)
            for _ in range(3):
                bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

            # Wipe tmpfs disk buffers
            temp_base = tempfile.gettempdir()
            for bproc_temp in glob.glob(os.path.join(temp_base, "blender_proc_*")):
                for temp_file in glob.glob(os.path.join(bproc_temp, "*")):
                    if os.path.isfile(temp_file):
                        try:
                            os.remove(temp_file)
                        except Exception:
                            pass

if __name__ == "__main__":
    main()