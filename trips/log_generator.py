"""
Log Sheet Generator

Generates ELD paper log sheet images with:
- 24-hour duty status grid
- Horizontal lines showing duty status over time
- Header information (date, miles, etc.)
- Remarks section with location changes
"""

import io
import os
from datetime import datetime, date
from PIL import Image, ImageDraw, ImageFont

from .scheduler import ScheduleEvent, DutyStatus, TripSchedule, get_schedule_by_day, calculate_daily_totals


# Log sheet dimensions and layout constants
LOG_WIDTH = 1200
LOG_HEIGHT = 850

# Grid area coordinates
GRID_LEFT = 150
GRID_RIGHT = 1050
GRID_TOP = 280
GRID_BOTTOM = 480
GRID_WIDTH = GRID_RIGHT - GRID_LEFT
GRID_HEIGHT = GRID_BOTTOM - GRID_TOP

# Row heights (4 duty status rows)
ROW_HEIGHT = GRID_HEIGHT / 4
ROW_POSITIONS = {
    DutyStatus.OFF_DUTY: GRID_TOP + ROW_HEIGHT * 0.5,
    DutyStatus.SLEEPER_BERTH: GRID_TOP + ROW_HEIGHT * 1.5,
    DutyStatus.DRIVING: GRID_TOP + ROW_HEIGHT * 2.5,
    DutyStatus.ON_DUTY_NOT_DRIVING: GRID_TOP + ROW_HEIGHT * 3.5,
}

# Time scale (24 hours)
HOURS_IN_DAY = 24
HOUR_WIDTH = GRID_WIDTH / HOURS_IN_DAY

# Colors
COLOR_BLACK = (0, 0, 0)
COLOR_GRAY = (128, 128, 128)
COLOR_LIGHT_GRAY = (200, 200, 200)
COLOR_WHITE = (255, 255, 255)
COLOR_RED = (220, 53, 69)
COLOR_BLUE = (0, 123, 255)
COLOR_LINE = (0, 0, 139)  # Dark blue for duty lines

# Line widths
LINE_WIDTH_GRID = 1
LINE_WIDTH_DUTY = 3
LINE_WIDTH_VERTICAL = 2


def get_font(size: int = 14, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if not available."""
    try:
        # Try common system fonts
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            "C:\\Windows\\Fonts\\arial.ttf",  # Windows
        ]
        for path in font_paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def time_to_x_coordinate(time: datetime) -> float:
    """Convert a datetime to x coordinate on the grid."""
    hour = time.hour + time.minute / 60 + time.second / 3600
    return GRID_LEFT + (hour * HOUR_WIDTH)


def create_blank_log_sheet() -> Image.Image:
    """Create a blank log sheet template."""
    img = Image.new('RGB', (LOG_WIDTH, LOG_HEIGHT), COLOR_WHITE)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(20, bold=True)
    font_header = get_font(14)
    font_small = get_font(12)
    font_grid = get_font(10)
    
    # Title
    draw.text((LOG_WIDTH // 2 - 150, 20), "DRIVER'S DAILY LOG", fill=COLOR_BLACK, font=font_title)
    draw.text((LOG_WIDTH // 2 - 100, 50), "(24-Hour Period)", fill=COLOR_GRAY, font=font_header)
    
    # Header fields - Left side
    header_y = 90
    draw.text((50, header_y), "Date:", fill=COLOR_BLACK, font=font_header)
    draw.line([(100, header_y + 18), (250, header_y + 18)], fill=COLOR_BLACK, width=1)
    
    draw.text((50, header_y + 30), "Total Miles:", fill=COLOR_BLACK, font=font_header)
    draw.line([(140, header_y + 48), (250, header_y + 48)], fill=COLOR_BLACK, width=1)
    
    draw.text((50, header_y + 60), "Carrier:", fill=COLOR_BLACK, font=font_header)
    draw.line([(110, header_y + 78), (350, header_y + 78)], fill=COLOR_BLACK, width=1)
    
    # Header fields - Right side
    draw.text((600, header_y), "From:", fill=COLOR_BLACK, font=font_header)
    draw.line([(650, header_y + 18), (900, header_y + 18)], fill=COLOR_BLACK, width=1)
    
    draw.text((600, header_y + 30), "To:", fill=COLOR_BLACK, font=font_header)
    draw.line([(630, header_y + 48), (900, header_y + 48)], fill=COLOR_BLACK, width=1)
    
    draw.text((950, header_y), "Day:", fill=COLOR_BLACK, font=font_header)
    draw.line([(995, header_y + 18), (1100, header_y + 18)], fill=COLOR_BLACK, width=1)
    
    # Grid labels (left side)
    labels = ["1. Off Duty", "2. Sleeper Berth", "3. Driving", "4. On Duty (Not Driving)"]
    for i, label in enumerate(labels):
        y = GRID_TOP + (i * ROW_HEIGHT) + (ROW_HEIGHT / 2) - 7
        draw.text((10, y), label, fill=COLOR_BLACK, font=font_small)
    
    # Draw grid border
    draw.rectangle(
        [(GRID_LEFT, GRID_TOP), (GRID_RIGHT, GRID_BOTTOM)],
        outline=COLOR_BLACK,
        width=2
    )
    
    # Draw horizontal grid lines (between status rows)
    for i in range(1, 4):
        y = GRID_TOP + (i * ROW_HEIGHT)
        draw.line([(GRID_LEFT, y), (GRID_RIGHT, y)], fill=COLOR_BLACK, width=LINE_WIDTH_GRID)
    
    # Draw vertical grid lines (hours) and hour labels
    for hour in range(HOURS_IN_DAY + 1):
        x = GRID_LEFT + (hour * HOUR_WIDTH)
        
        # Major lines at every hour
        if hour < HOURS_IN_DAY:
            # Full hour line
            draw.line([(x, GRID_TOP), (x, GRID_BOTTOM)], fill=COLOR_GRAY, width=LINE_WIDTH_GRID)
            
            # Quarter hour marks (smaller)
            for quarter in [0.25, 0.5, 0.75]:
                qx = x + (quarter * HOUR_WIDTH)
                draw.line([(qx, GRID_TOP), (qx, GRID_TOP + 5)], fill=COLOR_LIGHT_GRAY, width=1)
                draw.line([(qx, GRID_BOTTOM - 5), (qx, GRID_BOTTOM)], fill=COLOR_LIGHT_GRAY, width=1)
        
        # Hour label
        if hour <= 12:
            label = str(hour) if hour > 0 else "Mid"
        else:
            label = str(hour - 12) if hour < 24 else "Mid"
        
        label_x = x - 8 if len(label) == 1 else x - 12
        draw.text((label_x, GRID_TOP - 20), label, fill=COLOR_BLACK, font=font_grid)
    
    # AM/PM markers
    draw.text((GRID_LEFT + (6 * HOUR_WIDTH) - 10, GRID_TOP - 35), "A.M.", fill=COLOR_BLACK, font=font_small)
    draw.text((GRID_LEFT + (12 * HOUR_WIDTH) - 10, GRID_TOP - 35), "Noon", fill=COLOR_BLACK, font=font_small)
    draw.text((GRID_LEFT + (18 * HOUR_WIDTH) - 10, GRID_TOP - 35), "P.M.", fill=COLOR_BLACK, font=font_small)
    
    # Total hours section (right side of grid)
    totals_x = GRID_RIGHT + 20
    draw.text((totals_x, GRID_TOP - 35), "Total", fill=COLOR_BLACK, font=font_small)
    draw.text((totals_x, GRID_TOP - 22), "Hours", fill=COLOR_BLACK, font=font_small)
    
    for i in range(4):
        y = GRID_TOP + (i * ROW_HEIGHT) + (ROW_HEIGHT / 2) - 10
        draw.rectangle(
            [(totals_x, y), (totals_x + 40, y + 20)],
            outline=COLOR_BLACK,
            width=1
        )
    
    # Remarks section
    remarks_y = GRID_BOTTOM + 30
    draw.text((50, remarks_y), "REMARKS:", fill=COLOR_BLACK, font=font_header)
    draw.line([(50, remarks_y + 25), (1100, remarks_y + 25)], fill=COLOR_LIGHT_GRAY, width=1)
    draw.line([(50, remarks_y + 50), (1100, remarks_y + 50)], fill=COLOR_LIGHT_GRAY, width=1)
    draw.line([(50, remarks_y + 75), (1100, remarks_y + 75)], fill=COLOR_LIGHT_GRAY, width=1)
    draw.line([(50, remarks_y + 100), (1100, remarks_y + 100)], fill=COLOR_LIGHT_GRAY, width=1)
    draw.line([(50, remarks_y + 125), (1100, remarks_y + 125)], fill=COLOR_LIGHT_GRAY, width=1)
    draw.line([(50, remarks_y + 150), (1100, remarks_y + 150)], fill=COLOR_LIGHT_GRAY, width=1)
    
    # Certification text
    cert_y = LOG_HEIGHT - 80
    draw.text(
        (50, cert_y),
        "I certify these entries are true and correct:",
        fill=COLOR_BLACK,
        font=font_small
    )
    draw.line([(350, cert_y + 15), (600, cert_y + 15)], fill=COLOR_BLACK, width=1)
    draw.text((610, cert_y), "Driver's Signature", fill=COLOR_GRAY, font=font_small)
    
    return img


def draw_duty_status_lines(
    img: Image.Image,
    events: list[ScheduleEvent],
    log_date: date,
) -> Image.Image:
    """
    Draw duty status lines on the log sheet.
    
    Args:
        img: Base log sheet image
        events: Schedule events for this day
        log_date: Date of this log sheet
    
    Returns:
        Image with duty lines drawn
    """
    draw = ImageDraw.Draw(img)
    
    # Sort events by start time
    sorted_events = sorted(events, key=lambda e: e.start_time)
    
    prev_status = None
    prev_x = None
    
    for event in sorted_events:
        # Get x coordinates for this event
        start_x = time_to_x_coordinate(event.start_time)
        end_x = time_to_x_coordinate(event.end_time)
        
        # Clamp to grid boundaries
        start_x = max(GRID_LEFT, min(start_x, GRID_RIGHT))
        end_x = max(GRID_LEFT, min(end_x, GRID_RIGHT))
        
        # Get y position for this status
        y = ROW_POSITIONS.get(event.status, ROW_POSITIONS[DutyStatus.OFF_DUTY])
        
        # Draw vertical line if status changed
        if prev_status is not None and prev_status != event.status:
            prev_y = ROW_POSITIONS.get(prev_status, ROW_POSITIONS[DutyStatus.OFF_DUTY])
            if prev_x is not None:
                draw.line(
                    [(prev_x, prev_y), (start_x, y)],
                    fill=COLOR_LINE,
                    width=LINE_WIDTH_VERTICAL
                )
        
        # Draw horizontal line for this duty period
        if start_x < end_x:
            draw.line(
                [(start_x, y), (end_x, y)],
                fill=COLOR_LINE,
                width=LINE_WIDTH_DUTY
            )
        
        prev_status = event.status
        prev_x = end_x
    
    return img


def fill_header_info(
    img: Image.Image,
    log_date: date,
    day_number: int,
    total_miles: float,
    from_location: str,
    to_location: str,
    carrier_name: str = "Sample Carrier Co.",
) -> Image.Image:
    """
    Fill in the header information on the log sheet.
    
    Args:
        img: Log sheet image
        log_date: Date of this log
        day_number: Day number in the trip
        total_miles: Miles driven this day
        from_location: Starting location
        to_location: Ending location
        carrier_name: Carrier company name
    
    Returns:
        Image with header filled
    """
    draw = ImageDraw.Draw(img)
    font_header = get_font(14)
    
    header_y = 90
    
    # Date
    date_str = log_date.strftime("%m/%d/%Y")
    draw.text((105, header_y), date_str, fill=COLOR_BLUE, font=font_header)
    
    # Total miles
    draw.text((145, header_y + 30), f"{total_miles:.0f}", fill=COLOR_BLUE, font=font_header)
    
    # Carrier
    draw.text((115, header_y + 60), carrier_name, fill=COLOR_BLUE, font=font_header)
    
    # From location (truncate if too long)
    from_text = from_location[:35] if len(from_location) > 35 else from_location
    draw.text((655, header_y), from_text, fill=COLOR_BLUE, font=font_header)
    
    # To location
    to_text = to_location[:35] if len(to_location) > 35 else to_location
    draw.text((635, header_y + 30), to_text, fill=COLOR_BLUE, font=font_header)
    
    # Day number
    draw.text((1000, header_y), str(day_number), fill=COLOR_BLUE, font=font_header)
    
    return img


def fill_totals(
    img: Image.Image,
    off_duty_hours: float,
    sleeper_hours: float,
    driving_hours: float,
    on_duty_hours: float,
) -> Image.Image:
    """
    Fill in the total hours boxes.
    
    Args:
        img: Log sheet image
        off_duty_hours: Hours off duty
        sleeper_hours: Hours in sleeper berth
        driving_hours: Hours driving
        on_duty_hours: Hours on duty not driving
    
    Returns:
        Image with totals filled
    """
    draw = ImageDraw.Draw(img)
    font_small = get_font(12)
    
    totals_x = GRID_RIGHT + 25
    totals = [off_duty_hours, sleeper_hours, driving_hours, on_duty_hours]
    
    for i, total in enumerate(totals):
        y = GRID_TOP + (i * ROW_HEIGHT) + (ROW_HEIGHT / 2) - 8
        draw.text((totals_x, y), f"{total:.1f}", fill=COLOR_BLUE, font=font_small)
    
    return img


def fill_remarks(
    img: Image.Image,
    events: list[ScheduleEvent],
) -> Image.Image:
    """
    Fill in the remarks section with duty status changes and locations.
    
    Args:
        img: Log sheet image
        events: Schedule events for this day
    
    Returns:
        Image with remarks filled
    """
    draw = ImageDraw.Draw(img)
    font_small = get_font(11)
    
    remarks_y = GRID_BOTTOM + 30
    
    # Build remarks from events
    remarks = []
    for event in events:
        if event.note or event.location:
            time_str = event.start_time.strftime("%H:%M")
            status_name = {
                DutyStatus.OFF_DUTY: "Off",
                DutyStatus.SLEEPER_BERTH: "SB",
                DutyStatus.DRIVING: "D",
                DutyStatus.ON_DUTY_NOT_DRIVING: "On",
            }.get(event.status, "")
            
            remark = f"{time_str} {status_name}"
            if event.note:
                remark += f" - {event.note}"
            if event.location and event.location not in event.note:
                remark += f" ({event.location})"
            
            remarks.append(remark)
    
    # Draw remarks (up to 6 lines)
    for i, remark in enumerate(remarks[:6]):
        y = remarks_y + 30 + (i * 25)
        # Truncate long remarks
        text = remark[:100] if len(remark) > 100 else remark
        draw.text((50, y), text, fill=COLOR_BLACK, font=font_small)
    
    return img


def generate_log_sheet(
    events: list[ScheduleEvent],
    log_date: date,
    day_number: int,
    from_location: str,
    to_location: str,
) -> bytes:
    """
    Generate a complete log sheet for a single day.
    
    Args:
        events: Schedule events for this day
        log_date: Date of this log
        day_number: Day number in the trip
        from_location: Starting location for the day
        to_location: Ending location for the day
    
    Returns:
        PNG image bytes
    """
    # Calculate daily totals
    totals = calculate_daily_totals(events)
    
    # Create base log sheet
    img = create_blank_log_sheet()
    
    # Draw duty status lines
    img = draw_duty_status_lines(img, events, log_date)
    
    # Fill header information
    img = fill_header_info(
        img,
        log_date,
        day_number,
        totals["total_miles"],
        from_location,
        to_location,
    )
    
    # Fill totals
    img = fill_totals(
        img,
        totals["off_duty_hours"],
        totals["sleeper_hours"],
        totals["driving_hours"],
        totals["on_duty_hours"],
    )
    
    # Fill remarks
    img = fill_remarks(img, events)
    
    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_all_log_sheets(
    schedule: TripSchedule,
    current_address: str,
    dropoff_address: str,
) -> list[dict]:
    """
    Generate log sheets for all days of a trip.
    
    Args:
        schedule: Complete trip schedule
        current_address: Starting location address
        dropoff_address: Final destination address
    
    Returns:
        List of dicts with date, day_number, and image_bytes
    """
    by_day = get_schedule_by_day(schedule)
    log_sheets = []
    
    sorted_days = sorted(by_day.keys())
    
    for i, day_str in enumerate(sorted_days):
        events = by_day[day_str]
        log_date = datetime.strptime(day_str, "%Y-%m-%d").date()
        
        # Determine from/to locations for this day
        if i == 0:
            from_loc = current_address
        else:
            # Use location from first event of the day
            from_loc = events[0].location if events else "On Route"
        
        if i == len(sorted_days) - 1:
            to_loc = dropoff_address
        else:
            # Use location from last event of the day
            to_loc = events[-1].location if events else "On Route"
        
        image_bytes = generate_log_sheet(
            events,
            log_date,
            i + 1,
            from_loc,
            to_loc,
        )
        
        totals = calculate_daily_totals(events)
        
        log_sheets.append({
            "date": day_str,
            "day_number": i + 1,
            "image_bytes": image_bytes,
            "total_miles": totals["total_miles"],
            "driving_hours": totals["driving_hours"],
            "on_duty_hours": totals["on_duty_hours"],
            "off_duty_hours": totals["off_duty_hours"],
            "sleeper_hours": totals["sleeper_hours"],
        })
    
    return log_sheets
