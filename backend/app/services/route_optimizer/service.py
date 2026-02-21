"""Route Optimizer using OSRM (free, open-source routing).

Uses Open Source Routing Machine for distance/duration calculations
and NetworkX for graph-based optimization.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import networkx as nx
import numpy as np
from numpy.typing import NDArray

from app.models import POI, Route, RouteLeg, TransportMode, TimeConstraint
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

# Time constraint mappings in seconds
TIME_LIMITS = {
    TimeConstraint.HALF_DAY: 21600,   # 6 hours
    TimeConstraint.DAY: 28800,        # 8 hours
    TimeConstraint.TWO_DAYS: 57600,   # 16 hours (2 x 8h)
    TimeConstraint.THREE_DAYS: 86400, # 24 hours (3 x 8h)
    TimeConstraint.FIVE_DAYS: 144000, # 40 hours (5 x 8h)
}

# OSRM profile mapping
OSRM_PROFILES = {
    TransportMode.WALKING: "foot",
    TransportMode.DRIVING: "car",
    TransportMode.TRANSIT: "foot",  # OSRM doesn't have transit, fallback to walking
}


@dataclass
class DistanceMatrix:
    """Distance/duration matrix for POIs."""
    pois: list[POI]
    distances: NDArray[np.float64]
    durations: NDArray[np.float64]


class RouteOptimizerService(ABC):
    """Abstract base class for route optimization."""

    @abstractmethod
    async def build_distance_matrix(self, pois: list[POI], mode: TransportMode) -> DistanceMatrix:
        pass

    @abstractmethod
    def optimize_order(self, matrix: DistanceMatrix, start_index: int | None = None) -> list[int]:
        pass

    @abstractmethod
    async def get_route_geometry(self, ordered_pois: list[POI], mode: TransportMode) -> Route:
        pass

    @abstractmethod
    async def create_optimized_route(
        self,
        pois: list[POI],
        mode: TransportMode,
        time_constraint: TimeConstraint | None = None,
        start_index: int | None = None,
    ) -> Route:
        pass


class OSRMRouteOptimizerService(RouteOptimizerService):
    """OSRM-based route optimizer"""

    OSRM_URL = "https://router.project-osrm.org"
    
    MAX_POIS_BY_TIME = {
        "6h": 25,
        "day": 30,
        "2days": 40,
        "3days": 50,
        "5days": 50,
    }
    DEFAULT_MAX_POIS = 30

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        # Create a fresh client for each request to avoid connection pool issues
        return httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        pass  # No persistent client to close

    async def build_distance_matrix(self, pois: list[POI], mode: TransportMode) -> DistanceMatrix:
        """Build distance matrix using OSRM table service."""
        n = len(pois)
        distances = np.zeros((n, n), dtype=np.float64)
        durations = np.zeros((n, n), dtype=np.float64)

        if n <= 1:
            return DistanceMatrix(pois=pois, distances=distances, durations=durations)

        profile = OSRM_PROFILES.get(mode, "foot")

        # Build coordinates string
        coords = ";".join(f"{poi.coordinates.lng},{poi.coordinates.lat}" for poi in pois)
        url = f"{self.OSRM_URL}/table/v1/{profile}/{coords}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params={"annotations": "duration,distance"})
                response.raise_for_status()
                data = response.json()

                if data.get("code") == "Ok":
                    durations = np.array(data.get("durations", []), dtype=np.float64)
                    distances = np.array(data.get("distances", []), dtype=np.float64)
        except Exception:
            # Fallback: calculate straight-line distances
            for i in range(n):
                for j in range(n):
                    if i != j:
                        dist = haversine_distance(
                            pois[i].coordinates.lat, pois[i].coordinates.lng,
                            pois[j].coordinates.lat, pois[j].coordinates.lng
                        )
                        distances[i][j] = dist * 1000  # km to meters
                        # Estimate duration based on mode
                        speed = {"walking": 5, "driving": 40, "transit": 20}[mode.value]
                        durations[i][j] = (dist / speed) * 3600  # hours to seconds

        return DistanceMatrix(pois=pois, distances=distances, durations=durations)


    def optimize_order(self, matrix: DistanceMatrix, start_index: int | None = None) -> list[int]:
        """Find optimal visit order using nearest neighbor + 2-opt + best start.
        
        For walking tours, we want to minimize total walking distance.
        We try multiple starting points and pick the best overall route.
        """
        n = len(matrix.pois)
        if n <= 1:
            return list(range(n))
        if n == 2:
            return [0, 1] if start_index != 1 else [1, 0]

        def build_tour_from_start(start: int) -> tuple[list[int], float]:
            """Build a tour starting from given index using nearest neighbor."""
            visited = [start]
            current = start
            total_dist = 0.0

            while len(visited) < n:
                neighbors = [
                    (j, matrix.distances[current][j]) 
                    for j in range(n) 
                    if j not in visited and matrix.distances[current][j] > 0
                ]
                if not neighbors:
                    # Add remaining unvisited nodes
                    for j in range(n):
                        if j not in visited:
                            visited.append(j)
                    break
                next_node, dist = min(neighbors, key=lambda x: x[1])
                visited.append(next_node)
                total_dist += dist
                current = next_node

            return visited, total_dist

        def calculate_tour_distance(tour: list[int]) -> float:
            """Calculate total distance of a tour."""
            return sum(
                matrix.distances[tour[i]][tour[i + 1]]
                for i in range(len(tour) - 1)
            )

        def two_opt_improve(tour: list[int]) -> list[int]:
            """Apply 2-opt improvement until no improvement found."""
            improved = True
            best_tour = tour.copy()
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while improved and iteration < max_iterations:
                improved = False
                iteration += 1
                for i in range(1, n - 1):
                    for j in range(i + 1, n):
                        # Calculate gain from reversing segment [i, j]
                        if self._two_opt_gain(best_tour, matrix.distances, i, j) < -0.1:
                            best_tour[i:j+1] = list(reversed(best_tour[i:j+1]))
                            improved = True
                            break  # Restart from beginning after improvement
                    if improved:
                        break  # Restart outer loop
            
            return best_tour

        # If start_index is specified, use it
        if start_index is not None:
            tour, _ = build_tour_from_start(start_index)
            return two_opt_improve(tour)

        # Try all starting points and pick the best
        best_tour = None
        best_distance = float('inf')

        for start in range(n):
            tour, _ = build_tour_from_start(start)
            tour = two_opt_improve(tour)
            dist = calculate_tour_distance(tour)
            
            if dist < best_distance:
                best_distance = dist
                best_tour = tour

        return best_tour if best_tour else list(range(n))

    def _two_opt_gain(self, tour: list[int], durations: NDArray, i: int, j: int) -> float:
        """Calculate gain from 2-opt swap."""
        n = len(tour)
        a, b = tour[i - 1], tour[i]
        c, d = tour[j], tour[(j + 1) % n]
        current = durations[a][b] + durations[c][d]
        new = durations[a][c] + durations[b][d]
        return new - current

    async def get_route_geometry(self, ordered_pois: list[POI], mode: TransportMode) -> Route:
        """Get route with polyline from OSRM.
        
        Note: OSRM public server's foot profile returns unrealistic speeds,
        so we calculate walking duration ourselves based on 5 km/h average.
        
        For routes with many POIs, we batch requests to stay within OSRM limits.
        """
        if not ordered_pois:
            raise ValueError("No POIs provided")

        # OSRM has a practical limit of ~100 waypoints, but we handle any number
        # by batching if needed
        profile = "foot"
        
        # If we have many POIs, we need to batch the requests
        max_waypoints_per_request = 25
        
        if len(ordered_pois) <= max_waypoints_per_request:
            # Single request - simple case
            return await self._get_single_route(ordered_pois, mode, profile)
        else:
            # Multiple batches - stitch together
            return await self._get_batched_route(ordered_pois, mode, profile, max_waypoints_per_request)

    async def _get_single_route(self, ordered_pois: list[POI], mode: TransportMode, profile: str) -> Route:
        """Get route for a single batch of POIs."""
        coords = ";".join(f"{poi.coordinates.lng},{poi.coordinates.lat}" for poi in ordered_pois)
        url = f"{self.OSRM_URL}/route/v1/{profile}/{coords}"
        logger.info(f"[ROUTE] OSRM request: {len(ordered_pois)} POIs, profile={profile}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params={
                    "overview": "full",
                    "geometries": "polyline",
                    "steps": "false",
                })
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "Ok" or not data.get("routes"):
                    logger.info(f"[ROUTE] OSRM returned no route: {data.get('code')}")
                    raise ValueError("No route found")

                route_data = data["routes"][0]
                total_distance = int(route_data.get("distance", 0))
                polyline = route_data.get("geometry", "")
                logger.info(f"[ROUTE] OSRM success: distance={total_distance}m, polyline_length={len(polyline)}")
                
                speed_kmh = {
                    TransportMode.WALKING: 5.0,
                    TransportMode.DRIVING: 30.0,
                    TransportMode.TRANSIT: 15.0,
                }[mode]
                
                total_duration = int((total_distance / 1000) / speed_kmh * 3600)
                
                legs = []
                leg_data = route_data.get("legs", [])
                for i, leg in enumerate(leg_data):
                    if i < len(ordered_pois) - 1:
                        leg_distance = int(leg.get("distance", 0))
                        leg_duration = int((leg_distance / 1000) / speed_kmh * 3600)
                        legs.append(RouteLeg(
                            from_poi=ordered_pois[i],
                            to_poi=ordered_pois[i + 1],
                            distance=leg_distance,
                            duration=leg_duration,
                            polyline="",
                        ))

                return Route(
                    ordered_pois=ordered_pois,
                    polyline=route_data.get("geometry", ""),
                    total_distance=total_distance,
                    total_duration=total_duration,
                    transport_mode=mode,
                    legs=legs,
                )
        except Exception as e:
            logger.info(f"[ROUTE] OSRM error: {e}, using fallback")
            return self._create_fallback_route(ordered_pois, mode)

    async def _get_batched_route(self, ordered_pois: list[POI], mode: TransportMode, profile: str, batch_size: int) -> Route:
        """Get route for many POIs by batching requests and stitching polylines."""
        all_polylines = []
        total_distance = 0
        total_duration = 0
        all_legs = []
        
        speed_kmh = {
            TransportMode.WALKING: 5.0,
            TransportMode.DRIVING: 30.0,
            TransportMode.TRANSIT: 15.0,
        }[mode]

        # Process in overlapping batches (overlap by 1 to connect segments)
        i = 0
        while i < len(ordered_pois):
            end = min(i + batch_size, len(ordered_pois))
            batch = ordered_pois[i:end]
            
            if len(batch) < 2:
                break
            
            coords = ";".join(f"{poi.coordinates.lng},{poi.coordinates.lat}" for poi in batch)
            url = f"{self.OSRM_URL}/route/v1/{profile}/{coords}"

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params={
                        "overview": "full",
                        "geometries": "polyline",
                        "steps": "false",
                    })
                    response.raise_for_status()
                    data = response.json()

                    if data.get("code") == "Ok" and data.get("routes"):
                        route_data = data["routes"][0]
                        all_polylines.append(route_data.get("geometry", ""))
                        total_distance += int(route_data.get("distance", 0))
                        
                        # Build legs for this batch
                        leg_data = route_data.get("legs", [])
                        for j, leg in enumerate(leg_data):
                            if j < len(batch) - 1:
                                leg_distance = int(leg.get("distance", 0))
                                leg_duration = int((leg_distance / 1000) / speed_kmh * 3600)
                                all_legs.append(RouteLeg(
                                    from_poi=batch[j],
                                    to_poi=batch[j + 1],
                                    distance=leg_distance,
                                    duration=leg_duration,
                                    polyline="",
                                ))
            except Exception as e:
                logger.info(f"[ROUTE] Batch {i}-{end} error: {e}")
            
            # Move to next batch, overlapping by 1
            i = end - 1 if end < len(ordered_pois) else end

        total_duration = int((total_distance / 1000) / speed_kmh * 3600)
        
        # Combine polylines (simple concatenation - they should connect)
        combined_polyline = self._combine_polylines(all_polylines) if all_polylines else ""

        return Route(
            ordered_pois=ordered_pois,
            polyline=combined_polyline,
            total_distance=total_distance,
            total_duration=total_duration,
            transport_mode=mode,
            legs=all_legs,
        )

    def _combine_polylines(self, polylines: list[str]) -> str:
        """Combine multiple polylines into one by decoding, merging, and re-encoding."""
        if not polylines:
            return ""
        if len(polylines) == 1:
            return polylines[0]
        
        # Decode all polylines
        all_points = []
        for polyline in polylines:
            points = self._decode_polyline(polyline)
            if points:
                # Skip first point of subsequent polylines (it's the same as last of previous)
                if all_points and points:
                    points = points[1:]
                all_points.extend(points)
        
        # Re-encode
        return self._encode_polyline(all_points)

    def _decode_polyline(self, encoded: str) -> list[tuple[float, float]]:
        """Decode a polyline string into coordinates."""
        if not encoded:
            return []
        
        points = []
        index = 0
        lat = 0
        lng = 0

        while index < len(encoded):
            shift = 0
            result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            lat += (~(result >> 1) if result & 1 else result >> 1)

            shift = 0
            result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            lng += (~(result >> 1) if result & 1 else result >> 1)

            points.append((lat / 1e5, lng / 1e5))

        return points

    def _encode_polyline(self, points: list[tuple[float, float]]) -> str:
        """Encode coordinates into a polyline string."""
        if not points:
            return ""
        
        result = []
        prev_lat = 0
        prev_lng = 0

        for lat, lng in points:
            lat_int = int(round(lat * 1e5))
            lng_int = int(round(lng * 1e5))
            
            d_lat = lat_int - prev_lat
            d_lng = lng_int - prev_lng
            
            prev_lat = lat_int
            prev_lng = lng_int

            for val in [d_lat, d_lng]:
                val = ~(val << 1) if val < 0 else val << 1
                while val >= 0x20:
                    result.append(chr((0x20 | (val & 0x1f)) + 63))
                    val >>= 5
                result.append(chr(val + 63))

        return ''.join(result)

    def _create_fallback_route(self, ordered_pois: list[POI], mode: TransportMode) -> Route:
        """Create a route without OSRM geometry (fallback)."""
        total_dist = sum(
            haversine_distance(
                ordered_pois[i].coordinates.lat, ordered_pois[i].coordinates.lng,
                ordered_pois[i+1].coordinates.lat, ordered_pois[i+1].coordinates.lng
            ) * 1000
            for i in range(len(ordered_pois) - 1)
        ) if len(ordered_pois) > 1 else 0
        
        speed = {"walking": 5, "driving": 30, "transit": 15}[mode.value]
        total_dur = (total_dist / 1000 / speed) * 3600 if total_dist > 0 else 0

        return Route(
            ordered_pois=ordered_pois,
            polyline="",
            total_distance=int(total_dist),
            total_duration=int(total_dur),
            transport_mode=mode,
            legs=[],
        )

    async def create_optimized_route(
        self,
        pois: list[POI],
        mode: TransportMode,
        time_constraint: TimeConstraint | None = None,
        start_index: int | None = None,
        starting_point: tuple[float, float] | None = None,
        is_round_trip: bool = False,
        skip_optimization: bool = False,
    ) -> Route:
        """Full optimization pipeline with proper starting point support.
        
        Args:
            pois: List of POIs to visit (attractions only, not starting point)
            mode: Transport mode
            time_constraint: Optional time limit (if None, use all POIs)
            start_index: Deprecated - use starting_point instead
            starting_point: (lat, lng) tuple for user's starting location
            is_round_trip: Whether to return to starting point
            skip_optimization: If True, keep POI order as-is (use when POIs are already optimized)
        """
        from app.models import Coordinates
        
        # Only truncate POIs if we have a time constraint
        # For day routes (no time_constraint), use all POIs provided
        if time_constraint:
            max_pois = self.MAX_POIS_BY_TIME.get(time_constraint.value, self.DEFAULT_MAX_POIS)
            logger.info(f"[ROUTE] Starting optimization with {len(pois)} POIs (max: {max_pois})")
            if len(pois) > max_pois:
                pois = pois[:max_pois]
        else:
            logger.info(f"[ROUTE] Starting optimization with {len(pois)} POIs (no limit)")

        logger.info("[ROUTE] Building distance matrix...")
        matrix = await self.build_distance_matrix(pois, mode)
        logger.info("[ROUTE] Distance matrix built")
        
        # Skip optimization if POIs are already in optimal order
        if skip_optimization:
            logger.info(f"[ROUTE] Skipping optimization (already ordered)")
            ordered_pois = pois
        else:
            # If we have a starting point, find the nearest POI to start from
            first_poi_index = None
            if starting_point:
                start_lat, start_lng = starting_point
                logger.info(f"[ROUTE] Finding nearest POI to starting point ({start_lat:.4f}, {start_lng:.4f})...")
                
                # Calculate distance from starting point to each POI
                distances_from_start = []
                for i, poi in enumerate(pois):
                    dist = haversine_distance(start_lat, start_lng, 
                                           poi.coordinates.lat, poi.coordinates.lng)
                    distances_from_start.append((i, dist))
                
                # Sort by distance and pick the nearest
                distances_from_start.sort(key=lambda x: x[1])
                first_poi_index = distances_from_start[0][0]
                logger.info(f"[ROUTE] Nearest POI is #{first_poi_index + 1}: {pois[first_poi_index].name}")
            
            logger.info("[ROUTE] Optimizing order...")
            order = self.optimize_order(matrix, first_poi_index)
            logger.info(f"[ROUTE] Order optimized: {order}")
            ordered_pois = [pois[i] for i in order]

            if time_constraint:
                time_limit = TIME_LIMITS[time_constraint]
                ordered_pois = self._trim_to_time_limit(ordered_pois, matrix, order, time_limit)

        logger.info("[ROUTE] Getting route geometry...")
        
        # Build the full route including starting point
        if starting_point:
            result = await self._get_route_with_starting_point(
                ordered_pois, mode, starting_point, is_round_trip
            )
        else:
            result = await self.get_route_geometry(ordered_pois, mode)
        
        # Set starting point and round trip flag on the route
        if starting_point:
            result.starting_point = Coordinates(lat=starting_point[0], lng=starting_point[1])
            result.is_round_trip = is_round_trip
        
        logger.info("[ROUTE] Route geometry obtained")
        return result

    async def _get_route_with_starting_point(
        self,
        ordered_pois: list[POI],
        mode: TransportMode,
        starting_point: tuple[float, float],
        is_round_trip: bool,
    ) -> Route:
        """Get route geometry including starting point.
        
        Route: start → POI1 → POI2 → ... → POIn [→ start if round trip]
        """
        if not ordered_pois:
            raise ValueError("No POIs provided")

        start_lat, start_lng = starting_point
        profile = "foot"

        # Build coordinates: start + all POIs + (start again if round trip)
        coords_list = [f"{start_lng},{start_lat}"]
        coords_list.extend(f"{poi.coordinates.lng},{poi.coordinates.lat}" for poi in ordered_pois)
        if is_round_trip:
            coords_list.append(f"{start_lng},{start_lat}")
        
        coords = ";".join(coords_list)
        url = f"{self.OSRM_URL}/route/v1/{profile}/{coords}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params={
                    "overview": "full",
                    "geometries": "polyline",
                    "steps": "false",
                })
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "Ok" or not data.get("routes"):
                    raise ValueError("No route found")

                route_data = data["routes"][0]
                total_distance = int(route_data.get("distance", 0))
                
                speed_kmh = {
                    TransportMode.WALKING: 5.0,
                    TransportMode.DRIVING: 30.0,
                    TransportMode.TRANSIT: 15.0,
                }[mode]
                
                total_duration = int((total_distance / 1000) / speed_kmh * 3600)

                return Route(
                    ordered_pois=ordered_pois,
                    polyline=route_data.get("geometry", ""),
                    total_distance=total_distance,
                    total_duration=total_duration,
                    transport_mode=mode,
                    legs=[],  # Simplified - legs would need more work
                )
        except Exception as e:
            logger.info(f"[ROUTE] OSRM error: {e}, using fallback")
            # Fallback calculation
            total_dist = haversine_distance(start_lat, start_lng,
                                         ordered_pois[0].coordinates.lat, 
                                         ordered_pois[0].coordinates.lng) * 1000
            for i in range(len(ordered_pois) - 1):
                total_dist += haversine_distance(
                    ordered_pois[i].coordinates.lat, ordered_pois[i].coordinates.lng,
                    ordered_pois[i+1].coordinates.lat, ordered_pois[i+1].coordinates.lng
                ) * 1000
            if is_round_trip:
                total_dist += haversine_distance(
                    ordered_pois[-1].coordinates.lat, ordered_pois[-1].coordinates.lng,
                    start_lat, start_lng
                ) * 1000
            
            speed = {"walking": 5, "driving": 30, "transit": 15}[mode.value]
            total_dur = (total_dist / 1000 / speed) * 3600

            return Route(
                ordered_pois=ordered_pois,
                polyline="",
                total_distance=int(total_dist),
                total_duration=int(total_dur),
                transport_mode=mode,
                legs=[],
            )

    def _trim_to_time_limit(
        self,
        ordered_pois: list[POI],
        matrix: DistanceMatrix,
        order: list[int],
        time_limit: int,
    ) -> list[POI]:
        """Remove POIs to fit within time constraint."""
        if len(ordered_pois) <= 1:
            return ordered_pois

        total_time = 0
        result = [ordered_pois[0]]

        for i in range(1, len(order)):
            prev_idx = order[i - 1]
            curr_idx = order[i]
            travel_time = matrix.durations[prev_idx][curr_idx]
            
            if total_time + travel_time <= time_limit:
                total_time += travel_time
                result.append(ordered_pois[i])
            else:
                break

        return result


# Alias for backward compatibility — will be removed in a future version
GoogleRouteOptimizerService = OSRMRouteOptimizerService
