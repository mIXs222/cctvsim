using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public class RootConfig
{
    public StoreData store;
    public List<ProductItem> products;
    public SimData simulation;
    public List<CameraConfig> cameras;
}

[Serializable]
public class CheckoutPoint
{
    public float x, y;
}

[Serializable]
public class StoreData
{
    public float width;
    public float length;
    public float height;
    public float[] entrance;
    public int open_checkouts_count;
    public List<CheckoutPoint> checkouts;
    public List<AisleRect> aisles;
}

[Serializable]
public class AisleRect
{
    public float x0, y0, x1, y1;
}

[Serializable]
public class ProductCorrelation
{
    public string item;
    public float prob;
}

[Serializable]
public class ProductItem
{
    public string name;
    public float x, y;
    public float base_prob;
    public List<ProductCorrelation> correlations;
}

[Serializable]
public class SimData
{
    public int fps;
    public int num_customers;
    public float[] respawn_delay_range;
    public float speed_mean;
    public float speed_std;
    public string dwell_mode;
    public float dwell_mean;
    public float dwell_max;
    public float social_repulsion_weight;
}

[Serializable]
public class CameraConfig
{
    public string id;
    public float[] location;
    public float[] look_at;
    public float focal_length_mm;
    public int[] resolution;
}