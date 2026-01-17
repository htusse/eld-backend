"""
Trip Planning API Views
"""

import os
import uuid
import pickle
from pathlib import Path

from django.http import HttpResponse
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import PlanTripRequestSerializer
from .routing import (
    Location,
    calculate_route,
    geocode_address,
    reverse_geocode,
)
from .scheduler import create_trip_schedule
from .log_generator import generate_all_log_sheets


# File-based cache directory for log sheets
CACHE_DIR = Path(settings.BASE_DIR) / 'trip_cache'
CACHE_DIR.mkdir(exist_ok=True)


@api_view(['POST'])
def plan_trip(request):
    """
    Plan a trip with HOS-compliant schedule and log sheets.
    
    Request body:
    {
        "current": {"lat": 0, "lng": 0} or {"address": "..."},
        "pickup": {"lat": 0, "lng": 0} or {"address": "..."},
        "dropoff": {"lat": 0, "lng": 0} or {"address": "..."},
        "cycleUsedHours": 0
    }
    
    Returns:
    {
        "tripId": "...",
        "route": {...},
        "stops": [...],
        "schedule": [...],
        "logSheets": [...],
        "summary": {...}
    }
    """
    serializer = PlanTripRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    # Parse locations (geocode if address provided)
    try:
        current_location = _parse_location(data['current'], 'current')
        pickup_location = _parse_location(data['pickup'], 'pickup')
        dropoff_location = _parse_location(data['dropoff'], 'dropoff')
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Calculate route using OSRM
    route = calculate_route(current_location, pickup_location, dropoff_location)
    if route is None:
        return Response(
            {
                'error': (
                    'Unable to calculate route. Please check locations. '
                    'This may occur if locations are too remote, inaccessible by road, '
                    'or in areas without road connections (e.g., remote Alaska, islands).'
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create HOS-compliant schedule
    cycle_used = data.get('cycleUsedHours', 0)
    schedule = create_trip_schedule(
        route=route,
        current_location=current_location,
        pickup_location=pickup_location,
        dropoff_location=dropoff_location,
        cycle_used_hours=cycle_used,
    )
    
    # Generate log sheets
    log_sheets_data = generate_all_log_sheets(
        schedule,
        current_location.address,
        dropoff_location.address,
    )
    
    # Generate trip ID and store log sheets to disk
    trip_id = str(uuid.uuid4())
    trip_dir = CACHE_DIR / trip_id
    trip_dir.mkdir(exist_ok=True)
    
    for sheet in log_sheets_data:
        day_number = sheet['day_number']
        image_path = trip_dir / f'day_{day_number}.png'
        with open(image_path, 'wb') as f:
            f.write(sheet['image_bytes'])
    
    # Build response
    response_data = {
        'tripId': trip_id,
        'route': {
            'polyline': route.full_polyline,
            'totalDistanceMiles': round(route.total_distance_miles, 1),
            'totalDurationMinutes': round(route.total_duration_minutes, 1),
            'legs': [
                {
                    'fromLocation': leg.from_location,
                    'toLocation': leg.to_location,
                    'distanceMiles': round(leg.distance_miles, 1),
                    'durationMinutes': round(leg.duration_minutes, 1),
                }
                for leg in route.legs
            ],
            'waypoints': [
                {
                    'name': current_location.address,
                    'lat': current_location.lat,
                    'lng': current_location.lng,
                    'type': 'current',
                },
                {
                    'name': pickup_location.address,
                    'lat': pickup_location.lat,
                    'lng': pickup_location.lng,
                    'type': 'pickup',
                },
                {
                    'name': dropoff_location.address,
                    'lat': dropoff_location.lat,
                    'lng': dropoff_location.lng,
                    'type': 'dropoff',
                },
            ],
        },
        'stops': [
            {
                'type': stop.stop_type.value,
                'durationMinutes': stop.duration_minutes,
                'location': stop.location,
                'lat': stop.lat,
                'lng': stop.lng,
                'mileMarker': round(stop.mile_marker, 1) if stop.mile_marker else None,
                'reason': stop.reason,
            }
            for stop in schedule.stops
        ],
        'schedule': [
            {
                'start': event.start_time.isoformat(),
                'end': event.end_time.isoformat(),
                'status': event.status.value,
                'note': event.note,
                'location': event.location,
                'milesStart': round(event.miles_start, 1),
                'milesEnd': round(event.miles_end, 1),
                'durationMinutes': round(event.duration_minutes, 1),
            }
            for event in schedule.events
        ],
        'logSheets': [
            {
                'date': sheet['date'],
                'dayNumber': sheet['day_number'],
                'imageUrl': f'/api/logs/{trip_id}/day/{sheet["day_number"]}.png',
                'totalMiles': round(sheet['total_miles'], 1),
                'drivingHours': round(sheet['driving_hours'], 2),
                'onDutyHours': round(sheet['on_duty_hours'], 2),
                'offDutyHours': round(sheet['off_duty_hours'], 2),
            }
            for sheet in log_sheets_data
        ],
        'summary': {
            'totalDrivingHours': round(schedule.total_driving_hours, 2),
            'totalOnDutyHours': round(schedule.total_on_duty_hours, 2),
            'totalOffDutyHours': round(schedule.total_off_duty_hours, 2),
            'totalMiles': round(schedule.total_miles, 1),
            'startTime': schedule.start_time.isoformat() if schedule.start_time else None,
            'endTime': schedule.end_time.isoformat() if schedule.end_time else None,
            'totalDays': len(log_sheets_data),
            'cycleHoursUsed': cycle_used,
            'cycleHoursRemaining': round(70 - cycle_used - schedule.total_on_duty_hours, 2),
        },
    }
    
    return Response(response_data)


@api_view(['GET'])
def get_log_sheet(request, trip_id, day_number):
    """
    Get a log sheet image for a specific trip and day.
    
    Returns PNG image.
    """
    # Check if trip directory exists
    trip_dir = CACHE_DIR / trip_id
    if not trip_dir.exists():
        return Response(
            {'error': 'Trip not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if log sheet file exists
    image_path = trip_dir / f'day_{day_number}.png'
    if not image_path.exists():
        return Response(
            {'error': f'Day {day_number} not found for this trip'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Read and return the image
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    
    response = HttpResponse(image_bytes, content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="log-sheet-day-{day_number}.png"'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Expose-Headers'] = 'Content-Disposition'
    
    return response


@api_view(['POST'])
def geocode(request):
    """
    Geocode an address to coordinates.
    
    Request body:
    {
        "address": "123 Main St, City, State"
    }
    
    Returns:
    {
        "lat": 0,
        "lng": 0,
        "address": "Full formatted address"
    }
    """
    address = request.data.get('address')
    if not address:
        return Response(
            {'error': 'Address is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    location = geocode_address(address)
    if location is None:
        return Response(
            {'error': 'Unable to geocode address'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    return Response({
        'lat': location.lat,
        'lng': location.lng,
        'address': location.address,
    })


@api_view(['POST'])
def reverse_geocode_endpoint(request):
    """
    Reverse geocode coordinates to an address.
    
    Request body:
    {
        "lat": 0,
        "lng": 0
    }
    
    Returns:
    {
        "address": "City, State"
    }
    """
    lat = request.data.get('lat')
    lng = request.data.get('lng')
    
    if lat is None or lng is None:
        return Response(
            {'error': 'lat and lng are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    address = reverse_geocode(lat, lng)
    
    return Response({
        'lat': lat,
        'lng': lng,
        'address': address,
    })


def _parse_location(data: dict, name: str) -> Location:
    """
    Parse location data, geocoding if necessary.
    
    Args:
        data: Location data dict with lat/lng or address
        name: Name of location for error messages
    
    Returns:
        Location object
    
    Raises:
        ValueError: If location cannot be determined
    """
    lat = data.get('lat')
    lng = data.get('lng')
    address = data.get('address', '')
    
    # If we have coordinates, use them
    if lat is not None and lng is not None:
        # Try to get address from reverse geocoding
        if not address:
            address = reverse_geocode(lat, lng)
        return Location(lat=lat, lng=lng, address=address)
    
    # Otherwise, geocode the address
    if address:
        location = geocode_address(address)
        if location:
            return location
    
    raise ValueError(f"Unable to determine {name} location")
