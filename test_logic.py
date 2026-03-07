import requests
import json

BASE_URL = "http://127.0.0.1:5000"

session = requests.Session()

def test_login():
    res = session.post(f"{BASE_URL}/login", data={
        'student_number': '202611112',
        'name': 'Test User',
        'password': '123456'
    })
    print("Login Test Status:", res.status_code)

def test_availability():
    res = session.get(f"{BASE_URL}/api/availability", params={
        'date': '2026-03-08',
        'start_time': 10,
        'end_time': 12
    })
    print("Availability Test:", res.json())

def test_reservation():
    payload = {
        'date': '2026-03-08',
        'start_time': 10,
        'end_time': 12,
        'seat_number': 5
    }
    res = session.post(f"{BASE_URL}/api/reserve", json=payload)
    print("Reservation Test:", res.json())

def test_overlapping_reservation():
    payload = {
        'date': '2026-03-08',
        'start_time': 11,
        'end_time': 13,
        'seat_number': 5 # Same seat
    }
    res = session.post(f"{BASE_URL}/api/reserve", json=payload)
    print("Overlap Test:", res.json())

def test_daily_cap_limit():
    payload = {
        'date': '2026-03-08',
        'start_time': 14,
        'end_time': 16, # Valid duration, but 2nd booking today
        'seat_number': 10
    }
    res = session.post(f"{BASE_URL}/api/reserve", json=payload)
    print("Daily Cap Limit Test (1 per day):", res.json())

if __name__ == "__main__":
    test_login()
    test_availability()
    test_reservation()
    test_overlapping_reservation()
    test_daily_cap_limit()
    
    # Check availability again to see if space is occupied
    test_availability()
