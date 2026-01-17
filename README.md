# ELD Trip Planner - Backend API

Django REST API for HOS-compliant trip planning with route optimization and ELD log sheet generation.

## Features

- **Trip Planning API**: Calculate HOS-compliant routes with break schedules
- **Route Optimization**: Integration with OSRM for accurate routing
- **Geocoding**: Convert addresses to coordinates using Nominatim (OpenStreetMap)
- **Log Sheet Generation**: Auto-generate daily ELD paper logs as images
- **HOS Rules Engine**: Enforce FMCSA Hours of Service regulations

## Tech Stack

- **Django 4.2** - Web framework
- **Django REST Framework** - API development
- **Pillow** - Image generation for log sheets
- **SQLite** - Database (development)
- **OSRM** - Route calculation
- **Nominatim** - Geocoding service

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Virtual environment tool (recommended)

## Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/htusse/eld-backend.git
cd backend
```

### 2. Create Virtual Environment

```bash
python -m venv .venv

# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Create a `.env` file in the `backend/` directory:

```bash
cp .env.example .env
```

Edit `.env` and configure:

```env
DJANGO_SECRET_KEY=your-unique-secret-key-generate-a-new-one
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

**Generate a new secret key** (never use the default in production):
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Run Database Migrations

```bash
python manage.py migrate
```

### 6. Start Development Server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/`

## API Endpoints

### POST /api/plan-trip

Plan a trip with HOS-compliant scheduling.

**Request Body:**
```json
{
  "current": {"lat": 40.7128, "lng": -74.0060},
  "pickup": {"lat": 41.8781, "lng": -87.6298},
  "dropoff": {"lat": 34.0522, "lng": -118.2437}
}
```

Or use addresses:
```json
{
  "current": "New York, NY",
  "pickup": "Chicago, IL",
  "dropoff": "Los Angeles, CA"
}
```

**Response:**
```json
{
  "trip_id": "abc123...",
  "summary": {
    "total_distance_miles": 2789.5,
    "total_duration_hours": 50.75,
    "total_driving_hours": 50.75,
    "num_rest_breaks": 6,
    "estimated_arrival": "2026-01-20T12:45:00Z"
  },
  "schedule": [...],
  "route": {...},
  "log_sheets": [...]
}
```

## Project Structure

```
backend/
├── server/                 # Django project configuration
│   ├── settings.py        # Django settings (env-based)
│   ├── urls.py            # URL routing
│   └── wsgi.py            # WSGI entry point
├── trips/                 # Main application
│   ├── views.py           # API endpoints
│   ├── hos_rules.py       # HOS rules engine
│   ├── scheduler.py       # Trip scheduler
│   ├── log_generator.py   # Log sheet generator
│   ├── models.py          # Database models
│   └── serializers.py     # API serializers
├── manage.py              # Django CLI
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
└── README.md              # This file
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DJANGO_SECRET_KEY` | Django secret key for cryptographic signing | (insecure default) | Yes (prod) |
| `DEBUG` | Enable debug mode | `True` | No |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames | `localhost,127.0.0.1` | Yes (prod) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5173` | Yes (prod) |
| `DATABASE_URL` | PostgreSQL connection string (optional) | SQLite | No |

## Production Deployment

### Prerequisites for Production

1. **Update requirements.txt** with production dependencies:
```bash
pip install gunicorn psycopg2-binary python-decouple
pip freeze > requirements.txt
```

2. **Update settings.py** to use environment variables (already configured)

3. **Configure Production Environment Variables**:
```env
DJANGO_SECRET_KEY=<generate-new-secure-key>
DEBUG=False
ALLOWED_HOSTS=your-domain.com,your-app.railway.app
CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

## Testing

Run tests:
```bash
python manage.py test
```

## HOS Rules Reference

The system implements FMCSA property-carrying driver regulations:

- **11-Hour Driving Limit**: Max 11 hours driving after 10 hours off
- **14-Hour Window**: Max 14-hour on-duty window
- **30-Minute Break**: Required after 8 cumulative hours driving
- **70-Hour/8-Day Cycle**: Max 70 hours on-duty in 8 rolling days
- **10-Hour Reset**: 10 consecutive off-duty hours resets limits

## Troubleshooting

### Common Issues

**Database locked error**:
```bash
rm db.sqlite3
python manage.py migrate
```

**CORS errors**:
- Check `CORS_ALLOWED_ORIGINS` includes your frontend URL
- Ensure no trailing slashes in origins

**Import errors**:
```bash
pip install -r requirements.txt --upgrade
```

## License

MIT License

## Support

For issues and questions, please open a GitHub issue.
