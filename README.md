# Multi-Camera Grocery Store CCTV Simulator (`BlenderProc`)

A modular, programmable synthetic data pipeline for generating **synchronized multi-camera CCTV surveillance footage** and **Multi-Target Multi-Camera (MTMC) ground truth** inside customizable grocery store layouts.

Built on **Python** and **BlenderProc**, this application decouples behavioral crowd simulation from 3D ray-traced rendering so you can rapidly iterate on store layouts, product placement correlations, customer dynamics, and camera mounts.

---

## Key Features

* **Configurable 3D Store Layouts**: Automatically generates a 3D grocery store `.obj` mesh (floor, walls, gondola aisles, checkout) from `config.yaml`, or ingests custom `.obj`/`.fbx`/`.blend` architectural store models.
* **Interactive & Programmatic CCTV Placement**: Define camera intrinsics/extrinsics in YAML or use the interactive 2D Floorplan GUI (`make gui`) to click-and-drag camera locations and viewing directions.
* **Correlated Product-Seeking Behavior**: Models realistic customer shopping baskets using base item probabilities and a conditional co-occurrence affinity matrix $P(\text{Item}_B \mid \text{Item}_A)$ (e.g., *Pasta $\rightarrow$ Sauce*), ordered via Nearest-Neighbor routing.
* **A\* Pathfinding & Social Force Crowd Dynamics**: Computes obstacle-free paths around store shelves and simulates continuous pedestrian movement, shelf browsing dwell times, and multi-agent repulsive collision avoidance.
* **Synchronized Multi-Modal Ground Truth**: Renders frame-synchronized multi-camera HDF5 containers containing:
  * RGB Color Streams
  * Distance / Depth Maps
  * Instance & Category Segmentation Masks (consistent Person Re-ID labels across all cameras)
  * Automatic **MOTChallenge** (`[frame, id, x, y, w, h]`) 2D bounding box annotations
* **Realistic NVR Post-Processing**: Simulates wide-angle radial barrel distortion, CMOS sensor noise, on-screen display (OSD) timestamps, and H.264 compression artifacts.

---

## Project Structure

```text
grocery_cctv_sim/
├── config.yaml          # Store geometry, product correlation matrix, CCTV & crowd params
├── setup_store.py       # 3D store mesh generator & interactive 2D CCTV placement GUI
├── sim_customers.py     # Correlated basket sampler, A* planner & Social Force simulator
├── render_cctv.py       # Headless BlenderProc multi-camera synchronized renderer
├── postprocess_nvr.py   # HDF5 -> distorted NVR MP4 streams + MOT ground-truth exporter
├── requirements.txt     # Host Python dependencies
├── Makefile             # Automation targets for setup, simulation, rendering & stitching
└── README.md            # Documentation