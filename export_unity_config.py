import os
import json
import yaml

def convert_config(yaml_path="config.yaml", out_path="UnityCCTVProject/Assets/StreamingAssets/unity_config.json"):
    with open(yaml_path, "r") as f:
        cfg = yaml.safe_load(f)

    aisles = [{"x0": a[0], "y0": a[1], "x1": a[2], "y1": a[3]} for a in cfg["store"]["aisles"]]
    
    raw_chk = cfg["store"].get("checkouts", [cfg["store"].get("checkout", [33.0, 4.0])])
    checkouts = [{"x": float(c[0]), "y": float(c[1])} for c in raw_chk]

    prods_raw = cfg["products"]
    base_probs = prods_raw.get("base_probabilities", {})
    corrs_raw = prods_raw.get("correlations", {})

    products = []
    for name, prob in base_probs.items():
        pos = prods_raw[name]
        corr_list = []
        if name in corrs_raw:
            for co_item, co_p in corrs_raw[name].items():
                corr_list.append({"item": co_item, "prob": float(co_p)})
        products.append({
            "name": name,
            "x": float(pos[0]),
            "y": float(pos[1]),
            "base_prob": float(prob),
            "correlations": corr_list
        })

    unity_cfg = {
        "store": {
            "width": float(cfg["store"]["width"]),
            "length": float(cfg["store"]["length"]),
            "height": float(cfg["store"]["height"]),
            "entrance": cfg["store"]["entrance"],
            "open_checkouts_count": int(cfg["store"].get("open_checkouts_count", 4)),
            "checkouts": checkouts,
            "aisles": aisles
        },
        "products": products,
        "simulation": {
            "fps": int(cfg["simulation"].get("fps", 15)),
            "num_customers": int(cfg["simulation"]["num_customers"]),
            "respawn_delay_range": cfg["simulation"].get("respawn_delay_range", [1.0, 4.0]),
            "speed_mean": float(cfg["simulation"]["speed_mean"]),
            "speed_std": float(cfg["simulation"]["speed_std"]),
            "dwell_mode": cfg["simulation"].get("dwell_mode", "lognormal"),
            "dwell_mean": float(cfg["simulation"].get("dwell_mean", 3.0)),
            "dwell_max": float(cfg["simulation"].get("dwell_max", 16.0)),
            "social_repulsion_weight": float(cfg["simulation"]["social_repulsion_weight"])
        },
        "cameras": cfg.get("cameras", [])
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(unity_cfg, f, indent=2)
    print(f"[+] Exported Unity configuration ({len(checkouts)} checkouts, {len(unity_cfg['cameras'])} cameras) -> {out_path}")

if __name__ == "__main__":
    convert_config()