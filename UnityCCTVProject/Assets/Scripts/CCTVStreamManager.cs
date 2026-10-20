using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.UI;

[Serializable]
public class StreamFrameHeader
{
    public string cam_id;
    public int frame_idx;
    public int width;
    public int height;
    public string timestamp;
    public List<string> mot_annotations;
}

public class CameraFeedInstance
{
    public CameraConfig config;
    public Camera unityCam;
    public RenderTexture renderTex;
    public Texture2D readbackTex;
}

public class CCTVStreamManager : MonoBehaviour
{
    public int tcpPort = 9999;
    public int jpegQuality = 80;

    private RootConfig cfg;
    private CrowdSimulator simulator;
    private List<CameraFeedInstance> feeds = new List<CameraFeedInstance>();
    private int frameIdx = 0;
    private float frameTimer = 0f;
    private float captureInterval = 1f / 15f;

    private TcpListener tcpServer;
    private List<TcpClient> clients = new List<TcpClient>();
    private readonly object clientLock = new object();
    private DateTime simStartTime = new DateTime(2026, 10, 16, 14, 20, 0);

    void Start()
    {
        Application.runInBackground = true;
        string cfgPath = Path.Combine(Application.streamingAssetsPath, "unity_config.json");
        if (!File.Exists(cfgPath))
        {
            Debug.LogError($"Missing config at {cfgPath}. Run `make unity-export` first!");
            return;
        }

        cfg = JsonUtility.FromJson<RootConfig>(File.ReadAllText(cfgPath));
        captureInterval = 1f / Mathf.Max(1, cfg.simulation.fps);
        Application.targetFrameRate = 60;

        simulator = new CrowdSimulator(cfg);
        GroceryStoreBuilder.BuildStore(cfg, simulator.OpenCheckoutSet);
        SetupCamerasAndUI();
        StartTcpServer();
    }

    private void SetupCamerasAndUI()
    {
        // Create full-screen A x B Grid Canvas in Unity window
        GameObject canvasGo = new GameObject("CCTV_Monitor_Canvas");
        Canvas canvas = canvasGo.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvasGo.AddComponent<CanvasScaler>();
        canvasGo.AddComponent<GraphicRaycaster>();

        GameObject gridGo = new GameObject("GridContainer");
        gridGo.transform.SetParent(canvasGo.transform, false);
        RectTransform rt = gridGo.AddComponent<RectTransform>();
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = Vector2.zero;
        rt.offsetMax = Vector2.zero;

        int n = cfg.cameras.Count;
        int cols = Mathf.CeilToInt(Mathf.Sqrt(n));
        int rows = Mathf.CeilToInt((float)n / cols);

        GridLayoutGroup grid = gridGo.AddComponent<GridLayoutGroup>();
        grid.constraint = GridLayoutGroup.Constraint.FixedColumnCount;
        grid.constraintCount = cols;
        grid.spacing = new Vector2(4, 4);
        grid.cellSize = new Vector2((Screen.width / (float)cols) - 6f, (Screen.height / (float)rows) - 6f);

        foreach (var camCfg in cfg.cameras)
        {
            int w = camCfg.resolution[0];
            int h = camCfg.resolution[1];

            GameObject camGo = new GameObject(camCfg.id);
            Camera cam = camGo.AddComponent<Camera>();
            Vector3 pos = GroceryStoreBuilder.ToUnityPos(camCfg.location[0], camCfg.location[1], camCfg.location[2]);
            Vector3 look = GroceryStoreBuilder.ToUnityPos(camCfg.look_at[0], camCfg.look_at[1], camCfg.look_at[2]);
            camGo.transform.position = pos;
            camGo.transform.LookAt(look, Vector3.up);

            // Convert 5.6mm sensor horizontal FOV to Unity vertical FOV
            float fovX = 2.0f * Mathf.Atan(5.6f / (2.0f * camCfg.focal_length_mm));
            float fovY = 2.0f * Mathf.Atan(Mathf.Tan(fovX / 2.0f) * ((float)h / w));
            cam.fieldOfView = fovY * Mathf.Rad2Deg;
            cam.nearClipPlane = 0.2f;
            cam.farClipPlane = 45.0f;

            RenderTexture rTex = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32);
            cam.targetTexture = rTex;

            // Add tile to Unity UI Grid
            GameObject tileGo = new GameObject($"Tile_{camCfg.id}");
            tileGo.transform.SetParent(gridGo.transform, false);
            RawImage rawImg = tileGo.AddComponent<RawImage>();
            rawImg.texture = rTex;

            feeds.Add(new CameraFeedInstance
            {
                config = camCfg,
                unityCam = cam,
                renderTex = rTex,
                readbackTex = new Texture2D(w, h, TextureFormat.RGB24, false)
            });
        }
    }

    private void StartTcpServer()
    {
        tcpServer = new TcpListener(IPAddress.Any, tcpPort);
        tcpServer.Start();
        Thread acceptThread = new Thread(() =>
        {
            while (true)
            {
                try
                {
                    TcpClient client = tcpServer.AcceptTcpClient();
                    client.NoDelay = true;
                    lock (clientLock) { clients.Add(client); }
                    Debug.Log("[+] Python streaming receiver connected!");
                }
                catch { break; }
            }
        });
        acceptThread.IsBackground = true;
        acceptThread.Start();
        Debug.Log($"[*] CCTV TCP Stream Server listening on 127.0.0.1:{tcpPort}");
    }

    void Update()
    {
        if (simulator == null) return;
        simulator.Step(Time.deltaTime);

        frameTimer += Time.deltaTime;
        if (frameTimer >= captureInterval)
        {
            frameTimer -= captureInterval;
            CaptureAndStreamAllFeeds();
            frameIdx++;
        }
    }

    private List<string> ComputeMOTAnnotations(Camera cam, int resW, int resH)
    {
        List<string> mot = new List<string>();
        float r = 0.28f;

        foreach (var ag in simulator.agents)
        {
            if (!ag.active || !ag.model.activeSelf) continue;

            Vector3 basePos = ag.model.transform.position;
            float h = ag.height;
            Vector3[] corners = new Vector3[8]
            {
                basePos + new Vector3(-r, 0, -r), basePos + new Vector3(r, 0, -r),
                basePos + new Vector3(-r, 0,  r), basePos + new Vector3(r, 0,  r),
                basePos + new Vector3(-r, h, -r), basePos + new Vector3(r, h, -r),
                basePos + new Vector3(-r, h,  r), basePos + new Vector3(r, h,  r)
            };

            float minX = resW, minY = resH, maxX = 0, maxY = 0;
            int validPts = 0;

            foreach (var c in corners)
            {
                Vector3 sp = cam.WorldToScreenPoint(c);
                if (sp.z > 0.2f)
                {
                    validPts++;
                    float px = sp.x;
                    float py = resH - sp.y; // Flip Y to top-left image origin
                    if (px < minX) minX = px;
                    if (px > maxX) maxX = px;
                    if (py < minY) minY = py;
                    if (py > maxY) maxY = py;
                }
            }

            if (validPts > 0)
            {
                int x0 = Mathf.Clamp(Mathf.RoundToInt(minX), 0, resW - 1);
                int y0 = Mathf.Clamp(Mathf.RoundToInt(minY), 0, resH - 1);
                int x1 = Mathf.Clamp(Mathf.RoundToInt(maxX), 0, resW - 1);
                int y1 = Mathf.Clamp(Mathf.RoundToInt(maxY), 0, resH - 1);
                int bw = x1 - x0;
                int bh = y1 - y0;
                if (bw > 8 && bh > 12)
                    mot.Add($"{frameIdx},{ag.id},{x0},{y0},{bw},{bh},1,1,1.0");
            }
        }
        return mot;
    }

    private void CaptureAndStreamAllFeeds()
    {
        bool hasClients;
        lock (clientLock) { hasClients = clients.Count > 0; }
        if (!hasClients) return;

        DateTime currTime = simStartTime.AddSeconds(frameIdx * captureInterval);
        string ts = currTime.ToString("yyyy-MM-dd HH:mm:ss.ff");

        foreach (var feed in feeds)
        {
            feed.unityCam.Render();
            RenderTexture.active = feed.renderTex;
            feed.readbackTex.ReadPixels(new Rect(0, 0, feed.renderTex.width, feed.renderTex.height), 0, 0);
            feed.readbackTex.Apply();
            RenderTexture.active = null;

            byte[] jpgBytes = feed.readbackTex.EncodeToJPG(jpegQuality);
            StreamFrameHeader header = new StreamFrameHeader
            {
                cam_id = feed.config.id,
                frame_idx = frameIdx,
                width = feed.renderTex.width,
                height = feed.renderTex.height,
                timestamp = ts,
                mot_annotations = ComputeMOTAnnotations(feed.unityCam, feed.renderTex.width, feed.renderTex.height)
            };

            byte[] headerBytes = Encoding.UTF8.GetBytes(JsonUtility.ToJson(header));
            byte[] packet = new byte[8 + headerBytes.Length + jpgBytes.Length];
            Buffer.BlockCopy(BitConverter.GetBytes(headerBytes.Length), 0, packet, 0, 4);
            Buffer.BlockCopy(BitConverter.GetBytes(jpgBytes.Length), 0, packet, 4, 4);
            Buffer.BlockCopy(headerBytes, 0, packet, 8, headerBytes.Length);
            Buffer.BlockCopy(jpgBytes, 0, packet, 8 + headerBytes.Length, jpgBytes.Length);

            lock (clientLock)
            {
                for (int i = clients.Count - 1; i >= 0; i--)
                {
                    try
                    {
                        clients[i].GetStream().Write(packet, 0, packet.Length);
                    }
                    catch
                    {
                        clients[i].Close();
                        clients.RemoveAt(i);
                    }
                }
            }
        }
    }

    void OnApplicationQuit()
    {
        tcpServer?.Stop();
    }
}