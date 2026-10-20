import json
import yaml
import heapq
import numpy as np

class GrocerySimulator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W = cfg['store']['width']
        self.L = cfg['store']['length']
        self.res = 0.25  # Grid resolution in meters
        self.grid_w = int(self.W / self.res)
        self.grid_l = int(self.L / self.res)
        self.occupancy = self._build_occupancy_grid()
        
        # Create 2 checkouts (if only 1 is in config, offset a second one by 2.5m on Y axis)
        raw_chk = self.cfg['store'].get('checkouts', [self.cfg['store'].get('checkout', [33.0, 4.0])])
        self.checkouts = [np.array(c, dtype=float) for c in raw_chk]
        num_open = min(self.cfg['store'].get('open_checkouts_count', 4), len(self.checkouts))
        self.open_checkout_indices = sorted(np.random.choice(len(self.checkouts), size=num_open, replace=False).tolist())
        print(f"[*] Opened {num_open}/{len(self.checkouts)} random checkout lanes: {[i+1 for i in self.open_checkout_indices]}")
        
        # Track agents in each checkout line
        self.queues = [[] for _ in self.checkouts]

    def _build_occupancy_grid(self):
        grid = np.zeros((self.grid_w, self.grid_l), dtype=bool)
        margin = 0.45  # Agent clearance from shelves
        for x0, y0, x1, y1 in self.cfg['store']['aisles']:
            gx0 = max(0, int((x0 - margin) / self.res))
            gx1 = min(self.grid_w, int((x1 + margin) / self.res))
            gy0 = max(0, int((y0 - margin) / self.res))
            gy1 = min(self.grid_l, int((y1 + margin) / self.res))
            grid[gx0:gx1, gy0:gy1] = True
        return grid

    def sample_shopping_list(self):
        prods = self.cfg['products']
        base_p = prods['base_probabilities']
        corr = prods.get('correlations', {})
        basket = set()

        for item, p in base_p.items():
            if np.random.rand() < p:
                basket.add(item)
                if item in corr:
                    for co_item, co_p in corr[item].items():
                        if np.random.rand() < co_p:
                            basket.add(co_item)

        if not basket:
            basket.add(np.random.choice(list(base_p.keys())))

        curr = np.array(self.cfg['store']['entrance'])
        unvisited = list(basket)
        ordered_waypoints = []
        
        # Nearest-neighbor routing for shopping list
        while unvisited:
            dists = [np.linalg.norm(curr - np.array(prods[item])) for item in unvisited]
            nxt_idx = int(np.argmin(dists))
            nxt_item = unvisited.pop(nxt_idx)
            curr = np.array(prods[nxt_item])
            ordered_waypoints.append((nxt_item, curr))

        return ordered_waypoints

    def astar(self, start_xy, goal_xy):
        s = (np.clip(int(start_xy[0]/self.res), 0, self.grid_w-1),
             np.clip(int(start_xy[1]/self.res), 0, self.grid_l-1))
        g = (np.clip(int(goal_xy[0]/self.res), 0, self.grid_w-1),
             np.clip(int(goal_xy[1]/self.res), 0, self.grid_l-1))

        open_set = [(0, s)]
        came_from = {}
        g_score = {s: 0}
        dirs = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == g:
                path = []
                while current in came_from:
                    path.append((current[0]*self.res, current[1]*self.res))
                    current = came_from[current]
                return path[::-1] if path else [goal_xy]

            for dx, dy in dirs:
                nb = (current[0]+dx, current[1]+dy)
                if 0 <= nb[0] < self.grid_w and 0 <= nb[1] < self.grid_l:
                    if self.occupancy[nb[0], nb[1]] and nb != g:
                        continue
                    tentative_g = g_score[current] + np.hypot(dx, dy)
                    if tentative_g < g_score.get(nb, float('inf')):
                        came_from[nb] = current
                        g_score[nb] = tentative_g
                        f = tentative_g + np.hypot(nb[0]-g[0], nb[1]-g[1])
                        heapq.heappush(open_set, (f, nb))
        return [goal_xy]

    def _create_agent(self, agent_id, spawn_frame):
        """Helper to create a fresh customer agent with distinct paths and speeds."""
        sim_cfg = self.cfg['simulation']
        waypoints = self.sample_shopping_list()
        start_pos = np.array(self.cfg['store']['entrance'], dtype=float) + np.random.uniform(-0.4, 0.4, 2)
        speed = np.clip(np.random.normal(sim_cfg['speed_mean'], sim_cfg['speed_std']), 0.7, 1.9)
        return {
            'id': agent_id,
            'pos': start_pos,
            'vel': np.zeros(2),
            'yaw': 0.0,
            'speed': float(speed),
            'waypoints': waypoints,
            'wp_idx': 0,
            'path': self.astar(start_pos, waypoints[0][1]),
            'dwell_timer': 0.0,
            'spawn_frame': spawn_frame,
            'active': True,
            'just_finished_dwell': False,
            
            # New Checkout & Queue state tracking
            'shopping_done': False,
            'checkout_idx': -1,
            'checkout_timer': 0.0,
            
            'history': {}
        }

    def run_simulation(self):
        sim_cfg = self.cfg['simulation']
        fps = sim_cfg['fps']
        dt = 1.0 / fps
        total_frames = int(sim_cfg['duration_sec'] * fps)
        respawn_delay_range = sim_cfg.get('respawn_delay_range', [2.0, 7.0])

        agents = []
        next_agent_id = 0

        # Initial cohort staggered entry
        for i in range(sim_cfg['num_customers']):
            spawn_frame = int(i * (fps * 1.2))
            agents.append(self._create_agent(next_agent_id, spawn_frame))
            next_agent_id += 1

        for frame in range(total_frames):
            newly_spawned = []

            for ag in agents:
                if frame < ag['spawn_frame'] or not ag['active']:
                    continue

                # 1. Path Management (Consume reached grid nodes)
                while ag['path'] and np.linalg.norm(np.array(ag['path'][0]) - ag['pos']) < 0.35:
                    ag['path'].pop(0)

                # 2. Shopping Logic (Aisles & Products)
                if not ag['shopping_done']:
                    if not ag['path'] and ag['dwell_timer'] <= 0.0:
                        if ag.get('just_finished_dwell', False):
                            ag['just_finished_dwell'] = False
                            ag['wp_idx'] += 1
                            
                            if ag['wp_idx'] >= len(ag['waypoints']):
                                # Finished shopping list! Transition to Checkout mode
                                ag['shopping_done'] = True
                                # Pick the shortest checkout queue ONLY among the 4 randomly opened lanes
                                c_idx = min(self.open_checkout_indices, key=lambda idx: (len(self.queues[idx]), np.linalg.norm(ag['pos'] - self.checkouts[idx])))
                                self.queues[c_idx].append(ag)
                                ag['checkout_idx'] = c_idx
                                ag['checkout_timer'] = np.random.uniform(5.0, 15.0)
                                # Route to the entry of the queue line so agents don't collide with the register
                                q_slot = self.checkouts[c_idx] + np.array([-0.95 * (len(self.queues[c_idx]) - 1), 0.0])
                                ag['path'] = self.astar(ag['pos'], q_slot)
                            else:
                                ag['path'] = self.astar(ag['pos'], ag['waypoints'][ag['wp_idx']][1])
                        else:
                            # Start browsing a product shelf
                            if sim_cfg.get('dwell_mode', 'uniform') == 'lognormal':
                                dwell = float(np.random.lognormal(mean=np.log(sim_cfg.get('dwell_mean', 3.0)), sigma=0.6))
                                ag['dwell_timer'] = float(np.clip(dwell, 1.0, sim_cfg.get('dwell_max', 20.0)))
                            else:
                                ag['dwell_timer'] = float(np.random.uniform(*sim_cfg['dwell_time_range']))
                            ag['just_finished_dwell'] = True

                # 3. Queuing Logic
                if ag['shopping_done']:
                    c_idx = ag['checkout_idx']
                    pos_in_queue = self.queues[c_idx].index(ag)
                    
                    # Queue forms extending to the left (-X direction) from the checkout with 0.85m gaps
                    target_pos = self.checkouts[c_idx] + np.array([-0.85 * pos_in_queue, 0.0])

                    # If close to queue position, drop A* path and move direct to slot
                    if ag['path'] and np.linalg.norm(ag['pos'] - target_pos) < 2.0:
                        ag['path'] = []
                    
                    # If at the front of the line and standing at the register
                    if not ag['path'] and pos_in_queue == 0 and np.linalg.norm(ag['pos'] - target_pos) < 0.4:
                        ag['checkout_timer'] -= dt
                        if ag['checkout_timer'] <= 0:
                            # Done paying! Exit the store
                            self.queues[c_idx].pop(0)
                            ag['active'] = False
                            
                            # Schedule a new replacement customer to enter the store
                            delay_sec = float(np.random.uniform(*respawn_delay_range))
                            respawn_frame = frame + int(delay_sec * fps)
                            if respawn_frame < total_frames:
                                newly_spawned.append(self._create_agent(next_agent_id, respawn_frame))
                                next_agent_id += 1
                            continue

                # 4. Movement Execution (Walking, Browsing, Queuing, Checking out)
                if not ag['shopping_done'] and ag['dwell_timer'] > 0.0:
                    ag['dwell_timer'] -= dt
                    desired_vel = np.zeros(2)
                    state_label = 'browsing'
                elif ag['shopping_done'] and pos_in_queue == 0 and np.linalg.norm(ag['pos'] - target_pos) < 0.4:
                    desired_vel = np.zeros(2)
                    state_label = 'checking_out'
                else:
                    if ag['path']:
                        target_node = np.array(ag['path'][0])
                    elif ag['shopping_done']:
                        target_node = target_pos
                    else:
                        target_node = ag['pos']

                    vec = target_node - ag['pos']
                    dist = max(np.linalg.norm(vec), 1e-4)
                    desired_vel = (vec / dist) * ag['speed']
                    
                    state_label = 'queuing' if ag['shopping_done'] else 'walking'

                # Social Force repulsion between active co-present agents
                repulsion = np.zeros(2)
                for other in agents:
                    if other['id'] != ag['id'] and other['active'] and frame >= other['spawn_frame']:
                        diff = ag['pos'] - other['pos']
                        d = np.linalg.norm(diff)
                        if 0.01 < d < 1.0:
                            repulsion += (diff / d) * np.exp(-d / 0.4) * sim_cfg['social_repulsion_weight']

                ag['vel'] = 0.7 * ag['vel'] + 0.3 * (desired_vel + repulsion)
                ag['pos'] = ag['pos'] + ag['vel'] * dt
                if np.linalg.norm(ag['vel']) > 0.05:
                    ag['yaw'] = float(np.arctan2(ag['vel'][1], ag['vel'][0]))

                # Record frame state
                target_prod = f"Checkout_{ag['checkout_idx']+1}" if ag['shopping_done'] else ag['waypoints'][min(ag['wp_idx'], len(ag['waypoints'])-1)][0]
                ag['history'][frame] = {
                    'pos': ag['pos'].round(3).tolist(),
                    'yaw': round(ag['yaw'], 3),
                    'state': state_label,
                    'target_product': target_prod
                }

            if newly_spawned:
                agents.extend(newly_spawned)

        output = {
            'fps': fps,
            'total_frames': total_frames,
            'agents': [{'id': a['id'], 'basket': [w[0] for w in a['waypoints']], 'frames': a['history']} for a in agents]
        }
        with open("trajectories.json", "w") as f:
            json.dump(output, f, indent=2)
        print(f"[+] Simulated {len(agents)} total customers across {total_frames} frames -> trajectories.json")

if __name__ == "__main__":
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    sim = GrocerySimulator(cfg)
    sim.run_simulation()