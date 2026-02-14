import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client.get_database()

# Base URL
BASE_URL = "https://nutrition.umd.edu"

# Known dining halls (locationNum -> name)
DINING_HALLS = {
    "16": {"name": "Yahentamitsi Dining Hall", "location": "South Campus"},
    "51": {"name": "251 North", "location": "North Campus"},
    "04": {"name": "South Campus Diner", "location": "South Campus"},
}


def get_menu_page(location_num, date):
    """Fetch the menu page HTML for a dining hall and date."""
    location_name = DINING_HALLS[location_num]["name"]
    url = f"{BASE_URL}/longmenu.aspx?locationNum={location_num}&locationName={location_name}&dtdate={date}"

    response = requests.get(url)
    response.raise_for_status()
    return response.text


def get_nutrition_info(rec_num_and_port):
    """Fetch nutrition info from a label page."""
    url = f"{BASE_URL}/label.aspx?RecNumAndPort={rec_num_and_port}"

    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    nutrition = {}

    # Try to find nutrition values in the page text
    text = soup.get_text()

    # Basic parsing - look for common patterns
    if "Calories" in text:
        try:
            # Find calories value
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith("Calories") and not "from Fat" in line:
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            nutrition['calories'] = int(part)
                            break
        except:
            pass

    return nutrition


def parse_menu_page(html, dining_hall_id, date):
    """Parse menu items from the HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []

    current_station = "Unknown"

    # Find all links that go to label.aspx (these are menu items)
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')

        # Check if this is a menu item link
        if 'label.aspx' in href and 'RecNumAndPort' in href:
            item_name = link.get_text(strip=True)

            if not item_name:
                continue

            # Extract RecNumAndPort from href
            rec_num = href.split('RecNumAndPort=')[-1] if 'RecNumAndPort=' in href else None

            item = {
                'name': item_name,
                'dining_hall_id': dining_hall_id,
                'date': date,
                'station': current_station,
                'meal_period': 'all',  # Site doesn't clearly separate meals
                'rec_num': rec_num,
                'scraped_at': datetime.now()
            }

            items.append(item)

        # Check if this might be a station header (bold text, no label link)
        elif not href or href == '#':
            text = link.get_text(strip=True)
            if text and len(text) < 50:
                current_station = text

    # Also look for station headers in other elements
    for bold in soup.find_all(['b', 'strong']):
        text = bold.get_text(strip=True)
        # Station names are typically short
        if text and len(text) < 40 and not any(c.isdigit() for c in text):
            # This might be a station - we'll pick it up in order
            pass

    return items


def save_dining_halls():
    """Save dining halls to database."""
    for hall_id, info in DINING_HALLS.items():
        db.dining_halls.update_one(
            {'hall_id': hall_id},
            {'$set': {
                'hall_id': hall_id,
                'name': info['name'],
                'location': info['location']
            }},
            upsert=True
        )
    print(f"Saved {len(DINING_HALLS)} dining halls")


def save_menu_items(items):
    """Save menu items to database (upsert to avoid duplicates)."""
    for item in items:
        db.menu_items.update_one(
            {
                'name': item['name'],
                'dining_hall_id': item['dining_hall_id'],
                'date': item['date']
            },
            {'$set': item},
            upsert=True
        )
    print(f"Saved {len(items)} menu items")


def scrape_all(days_ahead=3):
    """Main scraping function."""
    print("Starting scrape...")

    # Save dining halls first
    save_dining_halls()

    # Scrape menus for each dining hall
    for hall_id in DINING_HALLS:
        print(f"\nScraping {DINING_HALLS[hall_id]['name']}...")

        for day_offset in range(days_ahead):
            date = datetime.now() + timedelta(days=day_offset)
            date_str = date.strftime("%-m/%-d/%Y")  # Format: M/D/YYYY

            print(f"  Date: {date_str}")

            try:
                html = get_menu_page(hall_id, date_str)
                items = parse_menu_page(html, hall_id, date_str)
                save_menu_items(items)
                print(f"    Found {len(items)} items")
            except Exception as e:
                print(f"    Error: {e}")

    print("\nScrape complete!")


if __name__ == "__main__":
    scrape_all()
