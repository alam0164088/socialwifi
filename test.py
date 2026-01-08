import asyncio
import json
import os
import django
import websockets
from datetime import datetime
from asgiref.sync import sync_to_async
import math

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from apps.navigation.models import SavedRoute

User = get_user_model()

# Bangladesh real locations
BANGLADESH_ROUTES = [
    {"name": "Dhaka", "lat": 23.8103, "lng": 90.4125},
    {"name": "Mirpur", "lat": 23.8147, "lng": 90.3675},
    {"name": "Gulshan", "lat": 23.7872, "lng": 90.4142},
    {"name": "Dhanmondi", "lat": 23.7612, "lng": 90.3792},
    {"name": "Motijheel", "lat": 23.7633, "lng": 90.4101},
    {"name": "Badda", "lat": 23.8069, "lng": 90.4303},
]

# ============================================
# Get user from token (sync_to_async)
# ============================================
@sync_to_async
def get_user_from_token(token_str):
    """Extract user from JWT access token."""
    try:
        access_token_obj = AccessToken(token_str)
        user_id = access_token_obj["user_id"]
        user = User.objects.get(id=user_id)
        print(f"✅ User found: {user.email} (ID: {user.id})")
        return user
    except Exception as e:
        print(f"❌ Error extracting user: {e}")
        return None

# ============================================
# Check location before WebSocket (sync_to_async)
# ============================================
@sync_to_async
def check_location_before(user):
    """Check user location before WebSocket update."""
    try:
        route = SavedRoute.objects.filter(user=user, name="Current Location").first()
        if route:
            print(f"\n📍 Location BEFORE WebSocket:")
            print(f"   Latitude: {route.latitude}")
            print(f"   Longitude: {route.longitude}")
        else:
            print(f"\n⚠️  No saved route found for user {user.email}")
    except Exception as e:
        print(f"❌ Error checking location: {e}")

# ============================================
# Calculate direction and speed
# ============================================
def get_direction(lat_diff, lng_diff):
    """Calculate direction from lat/lng differences."""
    if abs(lng_diff) < 0.0001 and abs(lat_diff) < 0.0001:
        return "🔴 Stationary"
    
    angle = math.atan2(lng_diff, lat_diff) * 180 / math.pi
    
    if angle >= -22.5 and angle < 22.5:
        return "⬆️  North"
    elif angle >= 22.5 and angle < 67.5:
        return "↗️  North-East"
    elif angle >= 67.5 and angle < 112.5:
        return "➡️  East"
    elif angle >= 112.5 and angle < 157.5:
        return "↘️  South-East"
    elif angle >= 157.5 or angle < -157.5:
        return "⬇️  South"
    elif angle >= -157.5 and angle < -112.5:
        return "↙️  South-West"
    elif angle >= -112.5 and angle < -67.5:
        return "⬅️  West"
    else:
        return "↖️  North-West"

def calculate_speed(lat1, lng1, lat2, lng2, time_seconds):
    """Calculate speed in km/h between two points."""
    # Haversine formula
    R = 6371  # Earth radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c  # in km
    
    time_hours = time_seconds / 3600
    speed = distance / time_hours if time_hours > 0 else 0
    
    return distance, speed

# ============================================
# Connect to WebSocket and send location
# ============================================
async def websocket_location_test(access_token, user, start_location, end_location, route_name):
    """Connect to WebSocket and send animated location updates."""
    
    ws_url = f"ws://127.0.0.1:8000/ws/driver/?token={access_token}"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            
            # Receive connection message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            conn_data = json.loads(msg)
            
            # Send initial location
            initial_location = {
                "type": "initialize_location",
                "lat": start_location["lat"],
                "lng": start_location["lng"]
            }
            await websocket.send(json.dumps(initial_location))
            
            await asyncio.wait_for(websocket.recv(), timeout=5)
            
            print(f"\n🚗 Route: {route_name}")
            print(f"   From: {start_location['name']} ({start_location['lat']:.4f}, {start_location['lng']:.4f})")
            print(f"   To: {end_location['name']} ({end_location['lat']:.4f}, {end_location['lng']:.4f})")
            print(f"\n📍 Live Tracking:\n")
            
            # Smooth path between two locations
            steps = 20
            lat_diff = end_location["lat"] - start_location["lat"]
            lng_diff = end_location["lng"] - start_location["lng"]
            time_per_step = 5  # Update every 5 seconds
            
            prev_lat = start_location["lat"]
            prev_lng = start_location["lng"]
            total_distance = 0
            
            for i in range(steps):
                await asyncio.sleep(time_per_step)
                
                progress = (i + 1) / steps
                current_lat = start_location["lat"] + (lat_diff * progress)
                current_lng = start_location["lng"] + (lng_diff * progress)
                
                live_location = {
                    "type": "live_tracking",
                    "lat": current_lat,
                    "lng": current_lng
                }
                
                # Calculate speed and direction
                distance, speed = calculate_speed(prev_lat, prev_lng, current_lat, current_lng, time_per_step)
                total_distance += distance
                direction = get_direction(current_lat - prev_lat, current_lng - prev_lng)
                
                # Simple animated ball without percentage
                bar_length = 50
                filled = int(bar_length * progress)
                bar = "●" * filled + "○" * (bar_length - filled)
                
                print(f"   {bar}")
                print(f"   📍 Lat: {current_lat:.6f} | Lng: {current_lng:.6f}")
                print(f"   🚀 Speed: {speed:.2f} km/h | {direction}")
                print()
                
                await websocket.send(json.dumps(live_location))
                
                prev_lat = current_lat
                prev_lng = current_lng
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            
            # Calculate average speed
            total_time = steps * time_per_step / 3600  # Convert to hours
            avg_speed = total_distance / total_time if total_time > 0 else 0
            
            print(f"   ✅ {route_name} - Journey completed!")
            print(f"   📊 Total Distance: {total_distance:.3f} km")
            print(f"   ⏱️  Average Speed: {avg_speed:.2f} km/h\n")
            
    except Exception as e:
        print(f"❌ Error: {e}")

# ============================================
# Check location after WebSocket (sync_to_async)
# ============================================
@sync_to_async
def check_location_after(user):
    """Check user location after WebSocket update."""
    try:
        route = SavedRoute.objects.filter(user=user, name="Current Location").first()
        if route:
            print(f"📍 Current Location in Database:")
            print(f"   Latitude: {route.latitude:.6f}")
            print(f"   Longitude: {route.longitude:.6f}")
            print(f"   Last Updated: {route.updated_at}")
            return True
        else:
            print(f"❌ No location saved")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ============================================
# Main function
# ============================================
async def main():
    ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzkzODMwOTQxLCJpYXQiOjE3Njc5MTA5NDEsImp0aSI6IjQ1OGM4ZjJhOWQ0NjQyMWVhNDNkNTE3OWM0NjE1NTVlIiwidXNlcl9pZCI6IjEifQ.EvSooUMdzB-f4E6S-0l-R1KT97DHHGZDscpu1ZdXlhM"
    
    print("=" * 70)
    print("🚀 WebSocket Live Location Tracking - Bangladesh Routes")
    print("=" * 70)
    
    # Get user
    print("\n1️⃣  Authenticating user...")
    user = await get_user_from_token(ACCESS_TOKEN)
    
    if not user:
        print("❌ Cannot proceed")
        return
    
    try:
        # Single route tracking
        current_route = BANGLADESH_ROUTES[0]  # Dhaka
        next_route = BANGLADESH_ROUTES[1]     # Mirpur
        
        print(f"\n2️⃣  Sending live location updates...")
        print(f"🔌 Connected to WebSocket")
        
        # Send location updates
        await websocket_location_test(
            ACCESS_TOKEN, 
            user, 
            current_route, 
            next_route,
            f"{current_route['name']} → {next_route['name']}"
        )
        
        # Check final location
        print(f"\n3️⃣  Verifying location in database...")
        await check_location_after(user)
        
        print(f"\n{'='*70}")
        print("✅ Test completed successfully!")
        print(f"{'='*70}")
        
    except KeyboardInterrupt:
        print(f"\n\n{'='*70}")
        print("⛔ Tracking stopped by user (Ctrl+C)")
        print(f"{'='*70}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Test terminated")