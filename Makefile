# ==============================================================================
# Multi-Camera Grocery Store CCTV Simulator - Makefile
# ==============================================================================

PYTHON       ?= python3
PIP          ?= pip
BLENDERPROC  ?= blenderproc
CONFIG       ?= config.yaml
OUTPUT_DIR   ?= output
ASSETS_DIR   ?= assets
CAM_ID       ?= CAM_01_ENTRANCE
FRAME        ?= 0

# Unity Real-Time Streaming Config
ROWS         ?= 3
COLS         ?= 3
STREAM_MODE  ?= live

.PHONY: help install setup gui sim render debug postprocess grid unity-export unity-open stream-ui clean clean-output clean-unity clean-all

help: ## Show available commands and usage
	@echo "======================================================================"
	@echo " Grocery Store Multi-Camera CCTV Simulator (BlenderProc & Unity)"
	@echo "======================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Environment Setup ---
install: ## Install host Python dependencies + Blender internal Python packages
	$(PIP) install -r requirements.txt
	$(BLENDERPROC) pip install pyyaml scipy

# --- BlenderProc / Offline Pipeline ---
setup: ## Generate 3D procedural grocery store mesh (.obj) from config.yaml
	$(PYTHON) setup_store.py --config $(CONFIG)

gui: ## Launch interactive 2D floorplan GUI to click-and-place CCTV cameras
	$(PYTHON) setup_store.py --config $(CONFIG) --gui

sim: ## Simulate customer shopping baskets, A* paths, and Social Force trajectories
	$(PYTHON) sim_customers.py

render: ## Run headless BlenderProc to render all CCTV cameras (RGB + Seg + Depth)
	$(PYTHON) batch_render.py

debug: ## Open interactive Blender GUI via BlenderProc to inspect scene & camera frustums
	$(BLENDERPROC) debug render_cctv.py

postprocess: ## Convert HDF5 renders into NVR-style MP4s + MOTChallenge ground truth
	$(PYTHON) postprocess_nvr.py

grid: ## Stitch 4 CCTV NVR feeds into a single quad-view surveillance monitor MP4
	ffmpeg -y \
		-i $(OUTPUT_DIR)/CAM_01_ENTRANCE_nvr.mp4 \
		-i $(OUTPUT_DIR)/CAM_02_PALLET_DROP_nvr.mp4 \
		-i $(OUTPUT_DIR)/CAM_03_ACTION_ALLEY_WEST_nvr.mp4 \
		-i $(OUTPUT_DIR)/CAM_04_ACTION_ALLEY_EAST_nvr.mp4 \
		-filter_complex "\
			[0:v][1:v]hstack=inputs=2[top]; \
			[2:v][3:v]hstack=inputs=2[bottom]; \
			[top][bottom]vstack=inputs=2[v]" \
		-map "[v]" -c:v libx264 -crf 23 -pix_fmt yuv420p $(OUTPUT_DIR)/cctv_quad_monitor.mp4
	@echo "[+] Saved CCTV monitor matrix to $(OUTPUT_DIR)/cctv_quad_monitor.mp4"

# --- Unity / Real-Time Pipeline ---
unity-export: ## Convert config.yaml into Unity StreamingAssets JSON for real-time engine
	$(PYTHON) export_unity_config.py

unity-open: ## Open the Unity project in Unity Hub (macOS)
	open -a "Unity Hub" UnityCCTVProject/

stream-ui: ## Launch 2x4 8-camera CCTV UI with interactive hotkeys ([B] BBoxes, [1-8] Solo)
	$(PYTHON) stream_receiver.py --mode $(STREAM_MODE) --rows $(ROWS) --cols $(COLS)

# --- Cleanup ---
clean-output: ## Remove all rendered footages and ground truth in output/
	rm -rf $(OUTPUT_DIR)/*

clean-unity: ## Wipe Unity Library caches to force a clean recompile
	rm -rf UnityCCTVProject/Library UnityCCTVProject/Temp UnityCCTVProject/Obj UnityCCTVProject/Logs UnityCCTVProject/UserSettings

clean: ## Remove generated trajectories, HDF5 renders, and MP4 outputs
	rm -rf $(OUTPUT_DIR) trajectories.json

clean-all: clean clean-unity ## Remove all generated outputs, caches, and procedural 3D store meshes
	rm -rf $(ASSETS_DIR) UnityCCTVProject/Assets/StreamingAssets/unity_config.json