using System.Collections.Generic;
using UnityEngine;

public static class GroceryStoreBuilder
{
    private static readonly Color[] ShirtPalette = {
        new Color(0.12f, 0.18f, 0.32f), new Color(0.45f, 0.12f, 0.14f), new Color(0.15f, 0.28f, 0.18f),
        new Color(0.75f, 0.73f, 0.68f), new Color(0.22f, 0.22f, 0.24f), new Color(0.55f, 0.38f, 0.24f),
        new Color(0.28f, 0.42f, 0.55f), new Color(0.62f, 0.28f, 0.20f), new Color(0.10f, 0.10f, 0.12f),
        new Color(0.48f, 0.46f, 0.35f)
    };

    private static readonly Color[] PantsPalette = {
        new Color(0.10f, 0.14f, 0.24f), new Color(0.12f, 0.12f, 0.13f), new Color(0.48f, 0.40f, 0.30f),
        new Color(0.25f, 0.26f, 0.28f), new Color(0.22f, 0.32f, 0.46f)
    };

    private static readonly Color[] SkinPalette = {
        new Color(0.88f, 0.72f, 0.62f), new Color(0.78f, 0.58f, 0.45f), new Color(0.62f, 0.44f, 0.32f),
        new Color(0.42f, 0.28f, 0.20f), new Color(0.92f, 0.78f, 0.68f)
    };

    private static readonly Color[] HairPalette = {
        new Color(0.05f, 0.05f, 0.05f), new Color(0.18f, 0.11f, 0.06f), new Color(0.35f, 0.22f, 0.12f),
        new Color(0.55f, 0.42f, 0.22f), new Color(0.45f, 0.45f, 0.45f)
    };

    private static readonly Color[] ProdColors = {
        new Color(0.75f, 0.15f, 0.12f), new Color(0.15f, 0.45f, 0.78f), new Color(0.85f, 0.65f, 0.12f),
        new Color(0.20f, 0.62f, 0.28f), new Color(0.82f, 0.38f, 0.12f), new Color(0.55f, 0.22f, 0.65f)
    };

    public static Vector3 ToUnityPos(float bx, float by, float bz)
    {
        return new Vector3(bx, bz, by);
    }

    public static Material CreateMaterial(Color color, float smoothness = 0.3f, float metallic = 0.0f)
    {
        Shader shader = Shader.Find("Universal Render Pipeline/Lit");
        if (shader == null) shader = Shader.Find("Standard");
        Material mat = new Material(shader);
        mat.color = color;
        if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", smoothness);
        if (mat.HasProperty("_Glossiness")) mat.SetFloat("_Glossiness", smoothness);
        if (mat.HasProperty("_Metallic")) mat.SetFloat("_Metallic", metallic);
        return mat;
    }

    private static Material CreateTiledFloorMaterial(float width, float length)
    {
        Material mat = CreateMaterial(Color.white, 0.65f, 0.0f);
        Texture2D tex = new Texture2D(64, 64, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Point;
        Color c1 = new Color(0.64f, 0.63f, 0.61f);
        Color c2 = new Color(0.56f, 0.55f, 0.53f);
        for (int y = 0; y < 64; y++)
            for (int x = 0; x < 64; x++)
                tex.SetPixel(x, y, (((x / 32) + (y / 32)) % 2 == 0) ? c1 : c2);
        tex.Apply();
        mat.mainTexture = tex;
        mat.mainTextureScale = new Vector2(width / 2f, length / 2f);
        return mat;
    }

    private static GameObject CreateBox(string name, Vector3 blenderCenter, Vector3 blenderHalfExtents, Material mat, Transform parent)
    {
        GameObject go = GameObject.CreatePrimitive(PrimitiveType.Cube);
        go.name = name;
        go.transform.SetParent(parent, false);
        go.transform.position = ToUnityPos(blenderCenter.x, blenderCenter.y, blenderCenter.z);
        go.transform.localScale = new Vector3(blenderHalfExtents.x * 2f, blenderHalfExtents.z * 2f, blenderHalfExtents.y * 2f);
        go.GetComponent<Renderer>().sharedMaterial = mat;
        UnityEngine.Object.Destroy(go.GetComponent<Collider>());
        return go;
    }

    public static void BuildStore(RootConfig cfg, HashSet<int> openCheckouts)
    {
        GameObject root = new GameObject("GroceryStore_Environment");
        float W = cfg.store.width;
        float L = cfg.store.length;
        float H = cfg.store.height;

        Material floorMat = CreateTiledFloorMaterial(W, L);
        Material ceilingMat = CreateMaterial(new Color(0.28f, 0.29f, 0.31f), 0.2f, 0.3f);
        Material wallMat = CreateMaterial(new Color(0.80f, 0.78f, 0.74f), 0.15f, 0.0f);
        Material shelfMetalMat = CreateMaterial(new Color(0.75f, 0.32f, 0.10f), 0.5f, 0.5f); // Costco orange steel racking
        Material counterMat = CreateMaterial(new Color(0.18f, 0.18f, 0.20f), 0.7f, 0.3f);
        Material openSignMat = CreateMaterial(new Color(0.1f, 0.9f, 0.2f), 0.9f, 0.0f);
        Material closedSignMat = CreateMaterial(new Color(0.9f, 0.1f, 0.1f), 0.9f, 0.0f);

        Material[] prodMats = new Material[ProdColors.Length];
        for (int i = 0; i < ProdColors.Length; i++)
            prodMats[i] = CreateMaterial(ProdColors[i], 0.5f, 0.0f);

        // 1. Floor & Industrial Ceiling Slab + Steel Trusses
        CreateBox("Store_Floor", new Vector3(W / 2f, L / 2f, -0.05f), new Vector3(W / 2f, L / 2f, 0.05f), floorMat, root.transform);
        CreateBox("Store_Ceiling", new Vector3(W / 2f, L / 2f, H + 0.08f), new Vector3(W / 2f, L / 2f, 0.08f), ceilingMat, root.transform);

        for (int t = 0; t < 7; t++)
        {
            float tx = Mathf.Lerp(4.0f, W - 4.0f, t / 6f);
            CreateBox($"Roof_Truss_{t}", new Vector3(tx, L / 2f, H - 0.12f), new Vector3(0.12f, L / 2f, 0.12f), ceilingMat, root.transform);
        }

        // 2. Perimeter Walls
        CreateBox("Wall_South", new Vector3(W / 2f, -0.1f, H / 2f), new Vector3(W / 2f, 0.1f, H / 2f), wallMat, root.transform);
        CreateBox("Wall_North", new Vector3(W / 2f, L + 0.1f, H / 2f), new Vector3(W / 2f, 0.1f, H / 2f), wallMat, root.transform);
        CreateBox("Wall_West",  new Vector3(-0.1f, L / 2f, H / 2f), new Vector3(0.1f, L / 2f, H / 2f), wallMat, root.transform);
        CreateBox("Wall_East",  new Vector3(W + 0.1f, L / 2f, H / 2f), new Vector3(0.1f, L / 2f, H / 2f), wallMat, root.transform);

        // 3. Warehouse Racking & Pallet Islands
        System.Random rng = new System.Random(101);
        float[] zTiers = { 0.25f, 0.85f, 1.45f, 2.05f };

        for (int idx = 0; idx < cfg.store.aisles.Count; idx++)
        {
            AisleRect a = cfg.store.aisles[idx];
            float cx = (a.x0 + a.x1) / 2f;
            float cy = (a.y0 + a.y1) / 2f;
            float sx = (a.x1 - a.x0) / 2f;
            float sy = (a.y1 - a.y0) / 2f;

            CreateBox($"Spine_{idx}", new Vector3(cx, cy, 1.15f), new Vector3(0.08f, sy, 1.15f), shelfMetalMat, root.transform);

            foreach (float zTier in zTiers)
            {
                CreateBox($"Tier_{idx}_{zTier}", new Vector3(cx, cy, zTier), new Vector3(sx, sy, 0.03f), shelfMetalMat, root.transform);

                for (int s = 0; s < 3; s++)
                {
                    float py = Mathf.Lerp(a.y0 + 0.8f, a.y1 - 0.8f, s / 2f);
                    for (int side = -1; side <= 1; side += 2)
                    {
                        float px = cx + side * (sx * 0.55f);
                        Material pMat = prodMats[rng.Next(prodMats.Length)];
                        CreateBox($"Prod_{idx}_{zTier}_{s}_{side}",
                            new Vector3(px, py, zTier + 0.22f),
                            new Vector3(sx * 0.35f, sy / 3.6f, 0.19f),
                            pMat, root.transform);
                    }
                }
            }
        }

        // 4. 8 Checkout Lanes with Open (Green) / Closed (Red) Lane Indicators
        for (int i = 0; i < cfg.store.checkouts.Count; i++)
        {
            var chk = cfg.store.checkouts[i];
            CreateBox($"Checkout_Counter_{i + 1}", new Vector3(chk.x, chk.y, 0.48f), new Vector3(0.75f, 0.55f, 0.48f), counterMat, root.transform);
            bool isOpen = openCheckouts.Contains(i);
            CreateBox($"Checkout_Pole_{i + 1}", new Vector3(chk.x - 0.4f, chk.y + 0.45f, 1.4f), new Vector3(0.04f, 0.04f, 0.6f), counterMat, root.transform);
            CreateBox($"Checkout_Sign_{i + 1}", new Vector3(chk.x - 0.4f, chk.y + 0.45f, 2.1f), new Vector3(0.18f, 0.18f, 0.18f), isOpen ? openSignMat : closedSignMat, root.transform);
        }

        // 5. Overhead Ceiling Lights (placed below the H=5.5m ceiling slab)
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
        RenderSettings.ambientLight = new Color(0.58f, 0.58f, 0.60f);

        for (int i = 0; i < 5; i++)
        {
            float lx = Mathf.Lerp(4.5f, W - 4.5f, i / 4f);
            for (int j = 0; j < 4; j++)
            {
                float ly = Mathf.Lerp(4.0f, L - 4.0f, j / 3f);
                GameObject lightGo = new GameObject($"CeilingLight_{i}_{j}");
                lightGo.transform.SetParent(root.transform, false);
                lightGo.transform.position = ToUnityPos(lx, ly, H - 0.35f);
                Light l = lightGo.AddComponent<Light>();
                l.type = LightType.Point;
                l.range = 18f;
                l.intensity = 1.45f;
                l.color = new Color(1.0f, 0.98f, 0.94f);
                l.shadows = ((i + j) % 2 == 0) ? LightShadows.Soft : LightShadows.None;
            }
        }
    }

    public static GameObject CreateHumanoid(int agentId, System.Random rng, out float height)
    {
        height = Mathf.Lerp(1.55f, 1.92f, (float)rng.NextDouble());
        float scaleZ = height / 1.72f;
        float build = Mathf.Lerp(0.85f, 1.18f, (float)rng.NextDouble());

        Material shirtMat = CreateMaterial(ShirtPalette[rng.Next(ShirtPalette.Length)], 0.15f);
        Material pantsMat = CreateMaterial(PantsPalette[rng.Next(PantsPalette.Length)], 0.1f);
        Material skinMat  = CreateMaterial(SkinPalette[rng.Next(SkinPalette.Length)], 0.35f);
        Material hairMat  = CreateMaterial(HairPalette[rng.Next(HairPalette.Length)], 0.1f);

        GameObject root = new GameObject($"Customer_{agentId:D2}");

        for (int side = -1; side <= 1; side += 2)
        {
            GameObject leg = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            leg.transform.SetParent(root.transform, false);
            leg.transform.localPosition = new Vector3(side * 0.10f * build, 0.38f * scaleZ, 0f);
            leg.transform.localScale = new Vector3(0.085f * build * 2f, 0.76f * scaleZ * 0.5f, 0.085f * build * 2f);
            leg.GetComponent<Renderer>().sharedMaterial = pantsMat;
            UnityEngine.Object.Destroy(leg.GetComponent<Collider>());
        }

        GameObject hips = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        hips.transform.SetParent(root.transform, false);
        hips.transform.localPosition = new Vector3(0f, 0.78f * scaleZ, 0f);
        hips.transform.localScale = new Vector3(0.17f * build * 2f, 0.18f * scaleZ * 0.5f, 0.17f * build * 2f);
        hips.GetComponent<Renderer>().sharedMaterial = pantsMat;
        UnityEngine.Object.Destroy(hips.GetComponent<Collider>());

        GameObject torso = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        torso.transform.SetParent(root.transform, false);
        torso.transform.localPosition = new Vector3(0f, 1.12f * scaleZ, 0f);
        torso.transform.localScale = new Vector3(0.185f * build * 2f * 1.15f, 0.56f * scaleZ * 0.5f, 0.185f * build * 2f * 0.78f);
        torso.GetComponent<Renderer>().sharedMaterial = shirtMat;
        UnityEngine.Object.Destroy(torso.GetComponent<Collider>());

        for (int side = -1; side <= 1; side += 2)
        {
            GameObject arm = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            arm.transform.SetParent(root.transform, false);
            arm.transform.localPosition = new Vector3(side * 0.24f * build, 1.10f * scaleZ, 0f);
            arm.transform.localScale = new Vector3(0.055f * build * 2f, 0.54f * scaleZ * 0.5f, 0.055f * build * 2f);
            arm.GetComponent<Renderer>().sharedMaterial = shirtMat;
            UnityEngine.Object.Destroy(arm.GetComponent<Collider>());
        }

        GameObject head = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        head.transform.SetParent(root.transform, false);
        head.transform.localPosition = new Vector3(0f, 1.53f * scaleZ, 0f);
        head.transform.localScale = Vector3.one * (0.125f * 2f);
        head.GetComponent<Renderer>().sharedMaterial = skinMat;
        UnityEngine.Object.Destroy(head.GetComponent<Collider>());

        GameObject hair = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        hair.transform.SetParent(root.transform, false);
        hair.transform.localPosition = new Vector3(0f, 1.58f * scaleZ, -0.01f);
        hair.transform.localScale = new Vector3(0.132f * 2f * 1.02f, 0.132f * 2f * 0.65f, 0.132f * 2f * 1.02f);
        hair.GetComponent<Renderer>().sharedMaterial = hairMat;
        UnityEngine.Object.Destroy(hair.GetComponent<Collider>());

        return root;
    }
}