using System;
using System.Collections.Generic;
using UnityEngine;

public class CustomerAgent
{
    public int id;
    public Vector2 pos;
    public Vector2 vel;
    public float yaw;
    public float speed;
    public float height;
    public float stridePhase;
    public List<Tuple<string, Vector2>> waypoints;
    public int wpIdx;
    public List<Vector2> path;
    public float dwellTimer;
    public float spawnTime;
    public bool active;
    public bool justFinishedDwell;
    public bool shoppingDone;
    public int checkoutIdx;
    public float checkoutTimer;
    public string stateLabel;
    public GameObject model;
}

public class CrowdSimulator
{
    private RootConfig cfg;
    private float res = 0.25f;
    private int gridW, gridL;
    private bool[,] occupancy;
    private Vector2[] checkouts;
    private List<int> openCheckoutIndices = new List<int>();
    public HashSet<int> OpenCheckoutSet { get; private set; } = new HashSet<int>();
    private List<CustomerAgent>[] queues;
    public List<CustomerAgent> agents = new List<CustomerAgent>();
    private int nextAgentId = 0;
    private System.Random rng = new System.Random();
    private float simTime = 0f;

    public CrowdSimulator(RootConfig config)
    {
        cfg = config;
        gridW = Mathf.RoundToInt(cfg.store.width / res);
        gridL = Mathf.RoundToInt(cfg.store.length / res);
        occupancy = BuildOccupancyGrid();

        int numC = cfg.store.checkouts.Count;
        checkouts = new Vector2[numC];
        queues = new List<CustomerAgent>[numC];
        List<int> allIndices = new List<int>();

        for (int i = 0; i < numC; i++)
        {
            checkouts[i] = new Vector2(cfg.store.checkouts[i].x, cfg.store.checkouts[i].y);
            queues[i] = new List<CustomerAgent>();
            allIndices.Add(i);
        }

        // Randomly pick 4 open checkout lines out of 8
        int openCount = Mathf.Clamp(cfg.store.open_checkouts_count > 0 ? cfg.store.open_checkouts_count : 4, 1, numC);
        for (int i = 0; i < openCount; i++)
        {
            int pick = rng.Next(allIndices.Count);
            int chosenIdx = allIndices[pick];
            allIndices.RemoveAt(pick);
            openCheckoutIndices.Add(chosenIdx);
            OpenCheckoutSet.Add(chosenIdx);
        }
        openCheckoutIndices.Sort();
        Debug.Log($"[*] Opened {openCount}/{numC} random checkout lanes: [{string.Join(", ", openCheckoutIndices)}]");

        for (int i = 0; i < cfg.simulation.num_customers; i++)
        {
            float spawnT = i * 1.1f;
            agents.Add(CreateAgent(nextAgentId++, spawnT));
        }
    }

    private bool[,] BuildOccupancyGrid()
    {
        bool[,] grid = new bool[gridW, gridL];
        float margin = 0.45f;
        foreach (var a in cfg.store.aisles)
        {
            int gx0 = Mathf.Max(0, Mathf.FloorToInt((a.x0 - margin) / res));
            int gx1 = Mathf.Min(gridW, Mathf.FloorToInt((a.x1 + margin) / res));
            int gy0 = Mathf.Max(0, Mathf.FloorToInt((a.y0 - margin) / res));
            int gy1 = Mathf.Min(gridL, Mathf.FloorToInt((a.y1 + margin) / res));
            for (int x = gx0; x < gx1; x++)
                for (int y = gy0; y < gy1; y++)
                    grid[x, y] = true;
        }
        return grid;
    }

    private float NextGaussian(float mean, float std)
    {
        double u1 = 1.0 - rng.NextDouble();
        double u2 = 1.0 - rng.NextDouble();
        double randStdNormal = Math.Sqrt(-2.0 * Math.Log(u1)) * Math.Sin(2.0 * Math.PI * u2);
        return mean + std * (float)randStdNormal;
    }

    private List<Tuple<string, Vector2>> SampleShoppingList()
    {
        Dictionary<string, ProductItem> prodMap = new Dictionary<string, ProductItem>();
        foreach (var p in cfg.products) prodMap[p.name] = p;

        HashSet<string> basket = new HashSet<string>();
        foreach (var p in cfg.products)
        {
            if (rng.NextDouble() < p.base_prob)
            {
                basket.Add(p.name);
                if (p.correlations != null)
                {
                    foreach (var co in p.correlations)
                    {
                        if (rng.NextDouble() < co.prob)
                            basket.Add(co.item);
                    }
                }
            }
        }

        if (basket.Count == 0 && cfg.products.Count > 0)
            basket.Add(cfg.products[rng.Next(cfg.products.Count)].name);

        Vector2 curr = new Vector2(cfg.store.entrance[0], cfg.store.entrance[1]);
        List<string> unvisited = new List<string>(basket);
        List<Tuple<string, Vector2>> ordered = new List<Tuple<string, Vector2>>();

        while (unvisited.Count > 0)
        {
            int bestIdx = 0;
            float bestDist = float.MaxValue;
            for (int i = 0; i < unvisited.Count; i++)
            {
                var p = prodMap[unvisited[i]];
                float d = Vector2.Distance(curr, new Vector2(p.x, p.y));
                if (d < bestDist) { bestDist = d; bestIdx = i; }
            }
            string chosen = unvisited[bestIdx];
            unvisited.RemoveAt(bestIdx);
            curr = new Vector2(prodMap[chosen].x, prodMap[chosen].y);
            ordered.Add(new Tuple<string, Vector2>(chosen, curr));
        }
        return ordered;
    }

    public List<Vector2> AStar(Vector2 startXY, Vector2 goalXY)
    {
        Vector2Int s = new Vector2Int(Mathf.Clamp((int)(startXY.x / res), 0, gridW - 1), Mathf.Clamp((int)(startXY.y / res), 0, gridL - 1));
        Vector2Int g = new Vector2Int(Mathf.Clamp((int)(goalXY.x / res), 0, gridW - 1), Mathf.Clamp((int)(goalXY.y / res), 0, gridL - 1));

        List<Tuple<float, Vector2Int>> openSet = new List<Tuple<float, Vector2Int>> { new Tuple<float, Vector2Int>(0f, s) };
        Dictionary<Vector2Int, Vector2Int> cameFrom = new Dictionary<Vector2Int, Vector2Int>();
        Dictionary<Vector2Int, float> gScore = new Dictionary<Vector2Int, float> { { s, 0f } };

        int[] dx = { -1, 1, 0, 0, -1, -1, 1, 1 };
        int[] dy = { 0, 0, -1, 1, -1, 1, -1, 1 };

        while (openSet.Count > 0)
        {
            openSet.Sort((a, b) => a.Item1.CompareTo(b.Item1));
            Vector2Int current = openSet[0].Item2;
            openSet.RemoveAt(0);

            if (current == g)
            {
                List<Vector2> path = new List<Vector2>();
                while (cameFrom.ContainsKey(current))
                {
                    path.Add(new Vector2(current.x * res, current.y * res));
                    current = cameFrom[current];
                }
                path.Reverse();
                return path.Count > 0 ? path : new List<Vector2> { goalXY };
            }

            for (int i = 0; i < 8; i++)
            {
                Vector2Int nb = new Vector2Int(current.x + dx[i], current.y + dy[i]);
                if (nb.x >= 0 && nb.x < gridW && nb.y >= 0 && nb.y < gridL)
                {
                    if (occupancy[nb.x, nb.y] && nb != g) continue;
                    float stepCost = (dx[i] != 0 && dy[i] != 0) ? 1.4142f : 1.0f;
                    float tentativeG = gScore[current] + stepCost;
                    if (!gScore.ContainsKey(nb) || tentativeG < gScore[nb])
                    {
                        cameFrom[nb] = current;
                        gScore[nb] = tentativeG;
                        float f = tentativeG + Vector2Int.Distance(nb, g);
                        openSet.Add(new Tuple<float, Vector2Int>(f, nb));
                    }
                }
            }
        }
        return new List<Vector2> { goalXY };
    }

    private int PickBestOpenCheckout(Vector2 agentPos)
    {
        int bestIdx = openCheckoutIndices[0];
        float bestScore = float.MaxValue;
        foreach (int idx in openCheckoutIndices)
        {
            // Combine queue length penalty with physical distance
            float score = queues[idx].Count * 4.0f + Vector2.Distance(agentPos, checkouts[idx]) * 0.25f;
            if (score < bestScore)
            {
                bestScore = score;
                bestIdx = idx;
            }
        }
        return bestIdx;
    }

    private CustomerAgent CreateAgent(int id, float spawnTime)
    {
        var waypoints = SampleShoppingList();
        Vector2 startPos = new Vector2(
            cfg.store.entrance[0] + Mathf.Lerp(-0.4f, 0.4f, (float)rng.NextDouble()),
            cfg.store.entrance[1] + Mathf.Lerp(-0.4f, 0.4f, (float)rng.NextDouble())
        );
        float speed = Mathf.Clamp(NextGaussian(cfg.simulation.speed_mean, cfg.simulation.speed_std), 0.7f, 1.9f);
        float height;
        GameObject model = GroceryStoreBuilder.CreateHumanoid(id, rng, out height);
        model.SetActive(false);

        return new CustomerAgent
        {
            id = id,
            pos = startPos,
            vel = Vector2.zero,
            yaw = 0f,
            speed = speed,
            height = height,
            stridePhase = (float)(rng.NextDouble() * Math.PI * 2.0),
            waypoints = waypoints,
            wpIdx = 0,
            path = AStar(startPos, waypoints[0].Item2),
            dwellTimer = 0f,
            spawnTime = spawnTime,
            active = true,
            justFinishedDwell = false,
            shoppingDone = false,
            checkoutIdx = -1,
            checkoutTimer = 0f,
            stateLabel = "walking",
            model = model
        };
    }

    public void Step(float dt)
    {
        simTime += dt;
        List<CustomerAgent> newlySpawned = new List<CustomerAgent>();

        foreach (var ag in agents)
        {
            if (simTime < ag.spawnTime || !ag.active)
            {
                if (ag.model.activeSelf) ag.model.SetActive(false);
                continue;
            }
            if (!ag.model.activeSelf) ag.model.SetActive(true);

            while (ag.path.Count > 0 && Vector2.Distance(ag.path[0], ag.pos) < 0.35f)
                ag.path.RemoveAt(0);

            if (!ag.shoppingDone)
            {
                if (ag.path.Count == 0 && ag.dwellTimer <= 0f)
                {
                    if (ag.justFinishedDwell)
                    {
                        ag.justFinishedDwell = false;
                        ag.wpIdx++;
                        if (ag.wpIdx >= ag.waypoints.Count)
                        {
                            ag.shoppingDone = true;
                            int cIdx = PickBestOpenCheckout(ag.pos);
                            queues[cIdx].Add(ag);
                            ag.checkoutIdx = cIdx;
                            ag.checkoutTimer = Mathf.Lerp(6.0f, 15.0f, (float)rng.NextDouble());
                            int qPos = queues[cIdx].Count - 1;
                            Vector2 tailSlot = checkouts[cIdx] + new Vector2(-0.95f * qPos, 0f);
                            ag.path = AStar(ag.pos, tailSlot);
                        }
                        else
                        {
                            ag.path = AStar(ag.pos, ag.waypoints[ag.wpIdx].Item2);
                        }
                    }
                    else
                    {
                        float dwell = Mathf.Exp(NextGaussian(Mathf.Log(cfg.simulation.dwell_mean), 0.6f));
                        ag.dwellTimer = Mathf.Clamp(dwell, 1.0f, cfg.simulation.dwell_max);
                        ag.justFinishedDwell = true;
                    }
                }
            }

            Vector2 targetPos = ag.pos;
            int posInQueue = -1;

            if (ag.shoppingDone)
            {
                int cIdx = ag.checkoutIdx;
                posInQueue = queues[cIdx].IndexOf(ag);
                targetPos = checkouts[cIdx] + new Vector2(-0.95f * posInQueue, 0f);

                if (ag.path.Count > 0 && Vector2.Distance(ag.pos, targetPos) < 2.2f)
                    ag.path.Clear();

                if (ag.path.Count == 0 && posInQueue == 0 && Vector2.Distance(ag.pos, targetPos) < 0.45f)
                {
                    ag.checkoutTimer -= dt;
                    if (ag.checkoutTimer <= 0f)
                    {
                        queues[cIdx].RemoveAt(0);
                        ag.active = false;
                        ag.model.SetActive(false);

                        float delay = Mathf.Lerp(cfg.simulation.respawn_delay_range[0], cfg.simulation.respawn_delay_range[1], (float)rng.NextDouble());
                        newlySpawned.Add(CreateAgent(nextAgentId++, simTime + delay));
                        continue;
                    }
                }
            }

            Vector2 desiredVel = Vector2.zero;
            if (!ag.shoppingDone && ag.dwellTimer > 0f)
            {
                ag.dwellTimer -= dt;
                ag.stateLabel = "browsing";
            }
            else if (ag.shoppingDone && posInQueue == 0 && Vector2.Distance(ag.pos, targetPos) < 0.45f)
            {
                ag.stateLabel = "checking_out";
                ag.yaw = 0f; // Face the checkout register (+X)
            }
            else
            {
                Vector2 targetNode = (ag.path.Count > 0) ? ag.path[0] : (ag.shoppingDone ? targetPos : ag.pos);
                Vector2 vec = targetNode - ag.pos;
                float dist = vec.magnitude;
                if (dist > 0.12f)
                    desiredVel = (vec / dist) * ag.speed;
                ag.stateLabel = ag.shoppingDone ? "queuing" : "walking";
            }

            Vector2 repulsion = Vector2.zero;
            foreach (var other in agents)
            {
                if (other.id != ag.id && other.active && simTime >= other.spawnTime)
                {
                    Vector2 diff = ag.pos - other.pos;
                    float d = diff.magnitude;
                    if (d > 0.01f && d < 0.9f)
                        repulsion += (diff / d) * Mathf.Exp(-d / 0.35f) * cfg.simulation.social_repulsion_weight;
                }
            }

            ag.vel = 0.7f * ag.vel + 0.3f * (desiredVel + repulsion);
            ag.pos += ag.vel * dt;
            if (ag.vel.magnitude > 0.08f)
                ag.yaw = Mathf.Atan2(ag.vel.y, ag.vel.x);

            float bob = (ag.stateLabel == "walking") ? 0.022f * Mathf.Abs(Mathf.Sin(simTime * 6.5f + ag.stridePhase)) : 0f;
            ag.model.transform.position = GroceryStoreBuilder.ToUnityPos(ag.pos.x, ag.pos.y, bob);
            float unityYawDeg = 90f - (ag.yaw * Mathf.Rad2Deg);
            ag.model.transform.rotation = Quaternion.Euler(0f, unityYawDeg, 0f);
        }

        if (newlySpawned.Count > 0)
            agents.AddRange(newlySpawned);
    }
}