"""
Route Planning Service

Provides routing and geocoding functionality using:
- OSRM (Open Source Routing Machine) for route calculation
- Nominatim (OpenStreetMap) for geocoding addresses
"""

import requests
from typing import Optional
from dataclasses import dataclass
import urllib3

# Disable SSL warnings for older Python versions
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API endpoints - using http for compatibility with older SSL
OSRM_API_URL = "http://router.project-osrm.org/route/v1/driving"
NOMINATIM_API_URL = "https://nominatim.openstreetmap.org"

# Constants
METERS_TO_MILES = 0.000621371
SECONDS_TO_MINUTES = 1 / 60

# Request headers (be polite to free APIs)
HEADERS = {
    "User-Agent": "ELD-Trip-Planner/1.0 (Assessment Project)"
}


@dataclass
class Location:
    """Represents a geographic location."""
    lat: float
    lng: float
    address: str = ""
    
    def to_osrm_string(self) -> str:
        """Format for OSRM API (lng,lat order)."""
        return f"{self.lng},{self.lat}"


@dataclass
class RouteLeg:
    """Represents a leg of a route."""
    from_location: str
    to_location: str
    distance_miles: float
    duration_minutes: float
    polyline: str


@dataclass
class RouteResult:
    """Complete route calculation result."""
    legs: list[RouteLeg]
    total_distance_miles: float
    total_duration_minutes: float
    full_polyline: str
    waypoints: list[dict]


def geocode_address(address: str) -> Optional[Location]:
    """
    Convert an address string to coordinates using Nominatim.
    
    Args:
        address: Address string to geocode
    
    Returns:
        Location with coordinates, or None if not found
    """
    try:
        response = requests.get(
            f"{NOMINATIM_API_URL}/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",  # Limit to US for trucking routes
            },
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        
        data = response.json()
        if data:
            result = data[0]
            return Location(
                lat=float(result["lat"]),
                lng=float(result["lon"]),
                address=result.get("display_name", address),
            )
        return None
    except Exception as e:
        return None


def reverse_geocode(lat: float, lng: float) -> str:
    """
    Convert coordinates to an address using Nominatim.
    
    Args:
        lat: Latitude
        lng: Longitude
    
    Returns:
        Address string, or coordinates if reverse geocoding fails
    """
    try:
        response = requests.get(
            f"{NOMINATIM_API_URL}/reverse",
            params={
                "lat": lat,
                "lon": lng,
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        
        data = response.json()
        if data and "address" in data:
            addr = data["address"]
            # Build a short address (city, state)
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county", "")
            state = addr.get("state", "")
            if city and state:
                return f"{city}, {state}"
            return data.get("display_name", f"{lat:.4f}, {lng:.4f}")
        return f"{lat:.4f}, {lng:.4f}"
    except Exception as e:
        return f"{lat:.4f}, {lng:.4f}"


def calculate_route(
    current: Location,
    pickup: Location,
    dropoff: Location,
) -> Optional[RouteResult]:
    """
    Calculate a driving route through waypoints using OSRM.
    
    Args:
        current: Starting location
        pickup: Pickup location
        dropoff: Drop-off location
    
    Returns:
        RouteResult with legs and total distance/duration
    """
    try:
        # Build coordinates string for OSRM
        coordinates = ";".join([
            current.to_osrm_string(),
            pickup.to_osrm_string(),
            dropoff.to_osrm_string(),
        ])
        
        response = requests.get(
            f"{OSRM_API_URL}/{coordinates}",
            params={
                "overview": "full",  # Full polyline
                "geometries": "polyline",  # Encoded polyline format
                "steps": "false",
                "annotations": "false",
            },
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") != "Ok":
            return None
        
        route = data["routes"][0]
        osrm_legs = route["legs"]
        waypoints = data["waypoints"]
        
        legs = []
        location_names = ["current", "pickup", "dropoff"]
        
        for i, leg in enumerate(osrm_legs):
            legs.append(RouteLeg(
                from_location=location_names[i],
                to_location=location_names[i + 1],
                distance_miles=leg["distance"] * METERS_TO_MILES,
                duration_minutes=leg["duration"] * SECONDS_TO_MINUTES,
                polyline="",  # Individual leg polylines not needed
            ))
        
        total_distance = route["distance"] * METERS_TO_MILES
        total_duration = route["duration"] * SECONDS_TO_MINUTES
        
        return RouteResult(
            legs=legs,
            total_distance_miles=total_distance,
            total_duration_minutes=total_duration,
            full_polyline=route["geometry"],
            waypoints=[
                {"name": w.get("name", ""), "location": w["location"]}
                for w in waypoints
            ],
        )
    except Exception as e:
        return None
