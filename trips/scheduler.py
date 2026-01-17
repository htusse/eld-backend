"""
Trip Scheduler

Generates HOS-compliant trip schedules including:
- Driving segments
- Pickup/dropoff stops
- Fuel stops (every 1000 miles)
- 30-minute rest breaks (after 8 hours driving)
- 10-hour off-duty resets (when limits reached)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from .hos_rules import (
    HOSState,
    add_driving_time,
    add_on_duty_time,
    add_off_duty_time,
    start_new_shift,
    BREAK_DURATION_MINUTES,
    OFF_DUTY_RESET_HOURS,
    FUEL_STOP_INTERVAL_MILES,
    FUEL_STOP_DURATION_MINUTES,
    PICKUP_DURATION_MINUTES,
    DROPOFF_DURATION_MINUTES,
    AVG_SPEED_MPH,
)
from .routing import RouteResult, Location


class DutyStatus(Enum):
    """ELD duty statuses."""
    OFF_DUTY = "OFF_DUTY"
    SLEEPER_BERTH = "SLEEPER_BERTH"
    DRIVING = "DRIVING"
    ON_DUTY_NOT_DRIVING = "ON_DUTY_NOT_DRIVING"


class StopType(Enum):
    """Types of stops in a trip."""
    PICKUP = "PICKUP"
    DROPOFF = "DROPOFF"
    FUEL = "FUEL"
    REST_BREAK = "REST_BREAK"
    OFF_DUTY = "OFF_DUTY"


@dataclass
class ScheduleEvent:
    """A single event in the trip schedule."""
    start_time: datetime
    end_time: datetime
    status: DutyStatus
    note: str = ""
    location: str = ""
    miles_start: float = 0
    miles_end: float = 0
    
    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600
    
    @property
    def duration_minutes(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 60


@dataclass
class Stop:
    """A stop along the route."""
    stop_type: StopType
    duration_minutes: int
    location: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    mile_marker: Optional[float] = None
    reason: str = ""


@dataclass
class TripSchedule:
    """Complete trip schedule with all events and stops."""
    events: list[ScheduleEvent] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    total_driving_hours: float = 0
    total_on_duty_hours: float = 0
    total_off_duty_hours: float = 0
    total_miles: float = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


def create_trip_schedule(
    route: RouteResult,
    current_location: Location,
    pickup_location: Location,
    dropoff_location: Location,
    cycle_used_hours: float = 0,
    start_time: Optional[datetime] = None,
) -> TripSchedule:
    """
    Create an HOS-compliant trip schedule.
    
    Args:
        route: Calculated route from OSRM
        current_location: Starting location
        pickup_location: Pickup location
        dropoff_location: Dropoff location
        cycle_used_hours: Hours already used in 70hr/8day cycle
        start_time: When to start the trip (default: now + 1 hour)
    
    Returns:
        Complete trip schedule
    """
    # Initialize
    if start_time is None:
        start_time = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    schedule = TripSchedule(start_time=start_time)
    hos_state = HOSState(cycle_hours_used=cycle_used_hours, shift_active=False)
    current_time = start_time
    current_miles = 0
    
    # Start the shift
    hos_state = start_new_shift(hos_state)
    
    # Process each leg of the trip
    legs_data = [
        {
            "leg": route.legs[0],
            "start_location": current_location,
            "end_location": pickup_location,
            "end_type": StopType.PICKUP,
            "end_name": "Pickup",
        },
        {
            "leg": route.legs[1],
            "start_location": pickup_location,
            "end_location": dropoff_location,
            "end_type": StopType.DROPOFF,
            "end_name": "Dropoff",
        },
    ]
    
    for leg_index, leg_data in enumerate(legs_data):
        leg = leg_data["leg"]
        leg_miles = leg.distance_miles
        
        # Calculate fuel stops needed for this leg
        miles_to_drive = leg_miles
        leg_miles_driven = 0
        
        while miles_to_drive > 0:
            # Check if we need a fuel stop
            miles_since_last_fuel = current_miles % FUEL_STOP_INTERVAL_MILES
            miles_to_next_fuel = FUEL_STOP_INTERVAL_MILES - miles_since_last_fuel
            
            if miles_to_next_fuel <= 0:
                miles_to_next_fuel = FUEL_STOP_INTERVAL_MILES
            
            # Determine how far we can drive in this segment
            max_driving_hours = hos_state.get_max_continuous_driving_hours()
            max_miles_hos = max_driving_hours * AVG_SPEED_MPH
            
            # Choose the limiting factor
            miles_this_segment = min(miles_to_drive, max_miles_hos, miles_to_next_fuel)
            
            if miles_this_segment <= 0:
                # Can't drive - need a break or reset
                if hos_state.needs_30_min_break:
                    # Insert 30-min break
                    current_time, hos_state = _add_rest_break(
                        schedule, current_time, hos_state, current_miles,
                        f"Near mile {current_miles:.0f}"
                    )
                elif hos_state.duty_window_remaining <= 0 or hos_state.driving_hours_remaining <= 0:
                    # Need 10-hour off-duty reset
                    current_time, hos_state = _add_off_duty_reset(
                        schedule, current_time, hos_state, current_miles,
                        f"Near mile {current_miles:.0f}"
                    )
                elif hos_state.cycle_hours_remaining <= 0:
                    # Cycle limit reached - this is a problem for very long trips
                    # For now, add off-duty time (in practice, driver would need to wait)
                    current_time, hos_state = _add_off_duty_reset(
                        schedule, current_time, hos_state, current_miles,
                        f"Near mile {current_miles:.0f} (cycle limit)"
                    )
                continue
            
            # Calculate driving time for this segment
            driving_hours = miles_this_segment / AVG_SPEED_MPH
            
            # Add driving event
            end_time = current_time + timedelta(hours=driving_hours)
            schedule.events.append(ScheduleEvent(
                start_time=current_time,
                end_time=end_time,
                status=DutyStatus.DRIVING,
                note=f"Driving to {leg_data['end_name']}",
                location=f"Mile {current_miles:.0f} - {current_miles + miles_this_segment:.0f}",
                miles_start=current_miles,
                miles_end=current_miles + miles_this_segment,
            ))
            
            # Update state
            hos_state = add_driving_time(hos_state, driving_hours)
            current_time = end_time
            current_miles += miles_this_segment
            miles_to_drive -= miles_this_segment
            leg_miles_driven += miles_this_segment
            schedule.total_driving_hours += driving_hours
            schedule.total_on_duty_hours += driving_hours
            
            # Check for fuel stop
            if current_miles % FUEL_STOP_INTERVAL_MILES < miles_this_segment and miles_to_drive > 0:
                current_time, hos_state = _add_fuel_stop(
                    schedule, current_time, hos_state, current_miles,
                    f"Fuel stop at mile {current_miles:.0f}"
                )
            
            # Check if we need a 30-min break before continuing
            if hos_state.needs_30_min_break and miles_to_drive > 0:
                current_time, hos_state = _add_rest_break(
                    schedule, current_time, hos_state, current_miles,
                    f"Near mile {current_miles:.0f}"
                )
            
            # Check if we need a reset before continuing
            if (hos_state.duty_window_remaining <= 0 or hos_state.driving_hours_remaining <= 0) and miles_to_drive > 0:
                current_time, hos_state = _add_off_duty_reset(
                    schedule, current_time, hos_state, current_miles,
                    f"Near mile {current_miles:.0f}"
                )
        
        # Add the stop at end of leg (pickup or dropoff)
        if leg_data["end_type"] == StopType.PICKUP:
            current_time, hos_state = _add_pickup_stop(
                schedule, current_time, hos_state, current_miles,
                pickup_location
            )
        else:
            current_time, hos_state = _add_dropoff_stop(
                schedule, current_time, hos_state, current_miles,
                dropoff_location
            )
    
    schedule.total_miles = current_miles
    schedule.end_time = current_time
    
    return schedule


def _add_pickup_stop(
    schedule: TripSchedule,
    current_time: datetime,
    hos_state: HOSState,
    current_miles: float,
    location: Location,
) -> tuple[datetime, HOSState]:
    """Add pickup stop to schedule."""
    duration_hours = PICKUP_DURATION_MINUTES / 60
    end_time = current_time + timedelta(minutes=PICKUP_DURATION_MINUTES)
    
    schedule.events.append(ScheduleEvent(
        start_time=current_time,
        end_time=end_time,
        status=DutyStatus.ON_DUTY_NOT_DRIVING,
        note="Pickup - Loading",
        location=location.address or f"{location.lat:.4f}, {location.lng:.4f}",
        miles_start=current_miles,
        miles_end=current_miles,
    ))
    
    schedule.stops.append(Stop(
        stop_type=StopType.PICKUP,
        duration_minutes=PICKUP_DURATION_MINUTES,
        location=location.address,
        lat=location.lat,
        lng=location.lng,
        mile_marker=current_miles,
        reason="Loading cargo",
    ))
    
    # Pickup counts as a break if >= 30 minutes
    hos_state = add_on_duty_time(hos_state, duration_hours, counts_as_break=True)
    schedule.total_on_duty_hours += duration_hours
    
    return end_time, hos_state


def _add_dropoff_stop(
    schedule: TripSchedule,
    current_time: datetime,
    hos_state: HOSState,
    current_miles: float,
    location: Location,
) -> tuple[datetime, HOSState]:
    """Add dropoff stop to schedule."""
    duration_hours = DROPOFF_DURATION_MINUTES / 60
    end_time = current_time + timedelta(minutes=DROPOFF_DURATION_MINUTES)
    
    schedule.events.append(ScheduleEvent(
        start_time=current_time,
        end_time=end_time,
        status=DutyStatus.ON_DUTY_NOT_DRIVING,
        note="Dropoff - Unloading",
        location=location.address or f"{location.lat:.4f}, {location.lng:.4f}",
        miles_start=current_miles,
        miles_end=current_miles,
    ))
    
    schedule.stops.append(Stop(
        stop_type=StopType.DROPOFF,
        duration_minutes=DROPOFF_DURATION_MINUTES,
        location=location.address,
        lat=location.lat,
        lng=location.lng,
        mile_marker=current_miles,
        reason="Unloading cargo",
    ))
    
    # Dropoff counts as a break if >= 30 minutes
    hos_state = add_on_duty_time(hos_state, duration_hours, counts_as_break=True)
    schedule.total_on_duty_hours += duration_hours
    
    return end_time, hos_state


def _add_fuel_stop(
    schedule: TripSchedule,
    current_time: datetime,
    hos_state: HOSState,
    current_miles: float,
    location_note: str,
) -> tuple[datetime, HOSState]:
    """Add fuel stop to schedule."""
    duration_hours = FUEL_STOP_DURATION_MINUTES / 60
    end_time = current_time + timedelta(minutes=FUEL_STOP_DURATION_MINUTES)
    
    schedule.events.append(ScheduleEvent(
        start_time=current_time,
        end_time=end_time,
        status=DutyStatus.ON_DUTY_NOT_DRIVING,
        note="Fuel Stop",
        location=location_note,
        miles_start=current_miles,
        miles_end=current_miles,
    ))
    
    schedule.stops.append(Stop(
        stop_type=StopType.FUEL,
        duration_minutes=FUEL_STOP_DURATION_MINUTES,
        location=location_note,
        mile_marker=current_miles,
        reason="Refueling",
    ))
    
    # Fuel stop counts as a break (30 min)
    hos_state = add_on_duty_time(hos_state, duration_hours, counts_as_break=True)
    schedule.total_on_duty_hours += duration_hours
    
    return end_time, hos_state


def _add_rest_break(
    schedule: TripSchedule,
    current_time: datetime,
    hos_state: HOSState,
    current_miles: float,
    location_note: str,
) -> tuple[datetime, HOSState]:
    """Add 30-minute rest break to schedule."""
    duration_hours = BREAK_DURATION_MINUTES / 60
    end_time = current_time + timedelta(minutes=BREAK_DURATION_MINUTES)
    
    schedule.events.append(ScheduleEvent(
        start_time=current_time,
        end_time=end_time,
        status=DutyStatus.OFF_DUTY,
        note="30-min Rest Break (8hr rule)",
        location=location_note,
        miles_start=current_miles,
        miles_end=current_miles,
    ))
    
    schedule.stops.append(Stop(
        stop_type=StopType.REST_BREAK,
        duration_minutes=BREAK_DURATION_MINUTES,
        location=location_note,
        mile_marker=current_miles,
        reason="Required 30-minute break after 8 hours driving",
    ))
    
    # Off-duty time resets break counter
    hos_state = add_off_duty_time(hos_state, duration_hours)
    schedule.total_off_duty_hours += duration_hours
    
    return end_time, hos_state


def _add_off_duty_reset(
    schedule: TripSchedule,
    current_time: datetime,
    hos_state: HOSState,
    current_miles: float,
    location_note: str,
) -> tuple[datetime, HOSState]:
    """Add 10-hour off-duty reset to schedule."""
    duration_hours = OFF_DUTY_RESET_HOURS
    end_time = current_time + timedelta(hours=duration_hours)
    
    schedule.events.append(ScheduleEvent(
        start_time=current_time,
        end_time=end_time,
        status=DutyStatus.OFF_DUTY,
        note="10-hr Off Duty (Shift Reset)",
        location=location_note,
        miles_start=current_miles,
        miles_end=current_miles,
    ))
    
    schedule.stops.append(Stop(
        stop_type=StopType.OFF_DUTY,
        duration_minutes=int(duration_hours * 60),
        location=location_note,
        mile_marker=current_miles,
        reason="Required 10-hour off-duty period to reset driving limits",
    ))
    
    # 10-hour off-duty resets shift
    hos_state = add_off_duty_time(hos_state, duration_hours)
    schedule.total_off_duty_hours += duration_hours
    
    return end_time, hos_state


def get_schedule_by_day(schedule: TripSchedule) -> dict[str, list[ScheduleEvent]]:
    """
    Group schedule events by day.
    
    Args:
        schedule: Trip schedule
    
    Returns:
        Dictionary mapping date strings to events
    """
    by_day: dict[str, list[ScheduleEvent]] = {}
    
    for event in schedule.events:
        # Handle events that span multiple days
        current_start = event.start_time
        event_end = event.end_time
        
        while current_start < event_end:
            day_key = current_start.strftime("%Y-%m-%d")
            day_end = current_start.replace(hour=23, minute=59, second=59)
            
            # Determine end for this day's portion
            segment_end = min(day_end, event_end)
            
            # Create a segment for this day
            day_event = ScheduleEvent(
                start_time=current_start,
                end_time=segment_end,
                status=event.status,
                note=event.note,
                location=event.location,
                miles_start=event.miles_start,
                miles_end=event.miles_end,
            )
            
            if day_key not in by_day:
                by_day[day_key] = []
            by_day[day_key].append(day_event)
            
            # Move to next day
            current_start = (current_start + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    
    return by_day


def calculate_daily_totals(events: list[ScheduleEvent]) -> dict:
    """
    Calculate totals for a day's events.
    
    Args:
        events: List of events for a single day
    
    Returns:
        Dictionary with driving, on_duty, off_duty hours and miles
    """
    totals = {
        "driving_hours": 0,
        "on_duty_hours": 0,
        "off_duty_hours": 0,
        "sleeper_hours": 0,
        "total_miles": 0,
    }
    
    for event in events:
        hours = event.duration_hours
        if event.status == DutyStatus.DRIVING:
            totals["driving_hours"] += hours
            totals["total_miles"] += event.miles_end - event.miles_start
        elif event.status == DutyStatus.ON_DUTY_NOT_DRIVING:
            totals["on_duty_hours"] += hours
        elif event.status == DutyStatus.OFF_DUTY:
            totals["off_duty_hours"] += hours
        elif event.status == DutyStatus.SLEEPER_BERTH:
            totals["sleeper_hours"] += hours
    
    return totals
