"""
API Serializers for Trip Planning
"""

from rest_framework import serializers


class LocationSerializer(serializers.Serializer):
    """Serializer for a location (lat/lng or address)."""
    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    def validate(self, data):
        """Ensure either lat/lng or address is provided."""
        has_coords = data.get('lat') is not None and data.get('lng') is not None
        has_address = data.get('address')
        
        if not has_coords and not has_address:
            raise serializers.ValidationError(
                "Either lat/lng coordinates or an address must be provided."
            )
        return data


class PlanTripRequestSerializer(serializers.Serializer):
    """Serializer for trip planning request."""
    current = LocationSerializer()
    pickup = LocationSerializer()
    dropoff = LocationSerializer()
    cycleUsedHours = serializers.FloatField(min_value=0, max_value=70, default=0)
