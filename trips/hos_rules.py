"""
Hours of Service (HOS) Rules Engine

Implements FMCSA HOS regulations for property-carrying drivers:
- 14-hour window + 11-hour driving limit per shift
- 30-minute break after 8 cumulative driving hours
- 70-hour / 8-day rolling cycle limit
- 10-hour off-duty reset requirement
"""

from dataclasses import dataclass


# FMCSA HOS Constants (Property Carrier, 70hr/8days)
MAX_DRIVING_HOURS = 11.0  # Maximum driving hours per shift
MAX_DUTY_WINDOW_HOURS = 14.0  # Maximum on-duty window after coming on duty
BREAK_REQUIRED_AFTER_HOURS = 8.0  # Must take 30-min break after this many driving hours
BREAK_DURATION_MINUTES = 30  # Required break duration
OFF_DUTY_RESET_HOURS = 10.0  # Off-duty hours required to reset shift
CYCLE_LIMIT_HOURS = 70.0  # Rolling 8-day cycle limit
CYCLE_DAYS = 8  # Days in the cycle

# Operational constants
FUEL_STOP_INTERVAL_MILES = 1000  # Fuel stop at least every 1000 miles
FUEL_STOP_DURATION_MINUTES = 30  # Time for fuel stop
PICKUP_DURATION_MINUTES = 60  # Time for pickup
DROPOFF_DURATION_MINUTES = 60  # Time for dropoff
AVG_SPEED_MPH = 55  # Average driving speed for calculations


@dataclass
class HOSState:
    """
    Tracks the current Hours of Service state for a driver.
    """
    # Current shift tracking
    driving_hours_in_shift: float = 0.0  # Driving hours in current shift
    on_duty_hours_in_shift: float = 0.0  # Total on-duty hours in current shift (includes driving)
    duty_window_hours: float = 0.0  # Hours since shift started (14-hr window)
    
    # Break tracking
    driving_since_last_break: float = 0.0  # Driving hours since last 30-min break
    
    # Cycle tracking (70hr/8days)
    cycle_hours_used: float = 0.0  # Total on-duty hours in 8-day cycle
    
    # Status flags
    shift_active: bool = False  # Whether driver is in an active shift
    
    @property
    def driving_hours_remaining(self) -> float:
        """Hours of driving remaining in current shift."""
        return max(0, MAX_DRIVING_HOURS - self.driving_hours_in_shift)
    
    @property
    def duty_window_remaining(self) -> float:
        """Hours remaining in 14-hour window."""
        return max(0, MAX_DUTY_WINDOW_HOURS - self.duty_window_hours)
    
    @property
    def cycle_hours_remaining(self) -> float:
        """Hours remaining in 70-hour cycle."""
        return max(0, CYCLE_LIMIT_HOURS - self.cycle_hours_used)
    
    @property
    def hours_until_break_required(self) -> float:
        """Driving hours until 30-min break is required."""
        return max(0, BREAK_REQUIRED_AFTER_HOURS - self.driving_since_last_break)
    
    @property
    def needs_30_min_break(self) -> bool:
        """Check if 30-min break is required before more driving."""
        return self.driving_since_last_break >= BREAK_REQUIRED_AFTER_HOURS
    
    @property
    def can_drive(self) -> bool:
        """Check if driver can legally drive."""
        return (
            self.driving_hours_remaining > 0 and
            self.duty_window_remaining > 0 and
            self.cycle_hours_remaining > 0 and
            not self.needs_30_min_break
        )
    
    def get_max_continuous_driving_hours(self) -> float:
        """
        Calculate maximum hours driver can drive continuously
        considering all HOS limits.
        """
        limits = [
            self.driving_hours_remaining,  # 11-hour limit
            self.duty_window_remaining,  # 14-hour window
            self.cycle_hours_remaining,  # 70-hour cycle
            self.hours_until_break_required,  # 8-hour break requirement
        ]
        return max(0, min(limits))


def start_new_shift(state: HOSState) -> HOSState:
    """
    Start a new shift after 10-hour off-duty reset.
    Resets shift-specific counters but maintains cycle hours.
    
    Args:
        state: Current HOS state
    
    Returns:
        Updated HOS state
    """
    return HOSState(
        driving_hours_in_shift=0.0,
        on_duty_hours_in_shift=0.0,
        duty_window_hours=0.0,
        driving_since_last_break=0.0,
        cycle_hours_used=state.cycle_hours_used,
        shift_active=True,
    )


def add_driving_time(state: HOSState, hours: float) -> HOSState:
    """
    Add driving time to the HOS state.
    
    Args:
        state: Current HOS state
        hours: Driving hours to add
    
    Returns:
        Updated HOS state
    """
    if not state.shift_active:
        state = start_new_shift(state)
    
    return HOSState(
        driving_hours_in_shift=state.driving_hours_in_shift + hours,
        on_duty_hours_in_shift=state.on_duty_hours_in_shift + hours,
        duty_window_hours=state.duty_window_hours + hours,
        driving_since_last_break=state.driving_since_last_break + hours,
        cycle_hours_used=state.cycle_hours_used + hours,
        shift_active=True,
    )


def add_on_duty_time(state: HOSState, hours: float, counts_as_break: bool = False) -> HOSState:
    """
    Add on-duty (not driving) time to the HOS state.
    
    Args:
        state: Current HOS state
        hours: On-duty hours to add
        counts_as_break: Whether this counts as a 30-min break
    
    Returns:
        Updated HOS state
    """
    if not state.shift_active:
        state = start_new_shift(state)
    
    # If this counts as a break (30+ minutes), reset driving since break counter
    new_driving_since_break = state.driving_since_last_break
    if counts_as_break and hours >= (BREAK_DURATION_MINUTES / 60):
        new_driving_since_break = 0.0
    
    return HOSState(
        driving_hours_in_shift=state.driving_hours_in_shift,
        on_duty_hours_in_shift=state.on_duty_hours_in_shift + hours,
        duty_window_hours=state.duty_window_hours + hours,
        driving_since_last_break=new_driving_since_break,
        cycle_hours_used=state.cycle_hours_used + hours,
        shift_active=True,
    )


def add_off_duty_time(state: HOSState, hours: float) -> HOSState:
    """
    Add off-duty time to the HOS state.
    
    Args:
        state: Current HOS state
        hours: Off-duty hours to add
    
    Returns:
        Updated HOS state (may reset shift if 10+ hours)
    """
    # Off-duty time resets the driving since break counter
    # If 10+ consecutive hours, reset shift entirely
    if hours >= OFF_DUTY_RESET_HOURS:
        return HOSState(
            driving_hours_in_shift=0.0,
            on_duty_hours_in_shift=0.0,
            duty_window_hours=0.0,
            driving_since_last_break=0.0,
            cycle_hours_used=state.cycle_hours_used,  # Cycle doesn't reset
            shift_active=False,
        )
    
    # Shorter off-duty periods still count against 14-hr window
    # but reset the driving since break counter
    return HOSState(
        driving_hours_in_shift=state.driving_hours_in_shift,
        on_duty_hours_in_shift=state.on_duty_hours_in_shift,
        duty_window_hours=state.duty_window_hours + hours,
        driving_since_last_break=0.0,  # Any off-duty counts as break
        cycle_hours_used=state.cycle_hours_used,
        shift_active=state.shift_active,
    )
