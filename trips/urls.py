"""
URL Configuration for Trips API
"""

from django.urls import path
from . import views

urlpatterns = [
    path('plan-trip', views.plan_trip, name='plan-trip'),
    path('logs/<str:trip_id>/day/<int:day_number>.png', views.get_log_sheet, name='get-log-sheet'),
    path('geocode', views.geocode, name='geocode'),
    path('reverse-geocode', views.reverse_geocode_endpoint, name='reverse-geocode'),
]
