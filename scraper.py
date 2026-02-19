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
    "19": {"name": "Yahentamitsi Dining Hall", "location": "South Campus"},
    "51": {"name": "251 North", "location": "North Campus"},
    "16": {"name": "South Campus Diner", "location": "South Campus"},
}

def get_menu_page(location_num, date):
    url = f"{BASE_URL}/?locationNum={location_num}&dtdate={date}"
    response = requests.get(url)
    response.raise_for_status()

    return response.text

def parse_menu_page(html, dining_hall_id, date):
    soup = BeautifulSoup(html, 'html.parser')
    links = soup.findAll('a', href=True)
    items = []

    for link in links:
        href = link.get('href')
        name = link.get_text(strip=True)

        if 'label.aspx' in href:
            name = link.get_text(strip=True)
            rec_num = href.split('RecNumAndPort=')[-1]

            items.append({
                "name": name,
                "dining_hall_id": dining_hall_id,
                "date": date,
                "rec_num": rec_num
            })

    return items

def get_nutrition_info(rec_num):
    url = f"{BASE_URL}/label.aspx?RecNumAndPort={rec_num}"
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    nutrition = {}
    nutrients = soup.find_all('span', class_='nutfactstopnutrient')

    for nutrient in nutrients:
        label = nutrient.find('b')
        if label:
            name = label.get_text(strip=True)
            value = nutrient.get_text(strip=True).replace(name, '').strip()
            if name and value:
                nutrition[name] = value

    ingredients = soup.find('span', class_='labelingredientsvalue')
    if ingredients:
        nutrition['ingredients'] = ingredients.get_text(strip=True)

    allergens = soup.find('span', class_='labelallergensvalue')                   
    if allergens:                                                                 
        nutrition['allergens'] = allergens.get_text(strip=True)

    return nutrition

def scrape_dining_hall(location_num, date):
    items = parse_menu_page(get_menu_page(location_num, date), location_num, date)
    for item in items:
        nutrition = get_nutrition_info(item['rec_num'])
        item.update(nutrition)
    
    return items

def scrape_all_dining_halls(date):
    db.menu_items.delete_many({"date": date})
    all_items = []

    for location_num in DINING_HALLS:
        items = scrape_dining_hall(location_num, date)
        all_items.extend(items)
    
    if all_items:
        db.menu_items.insert_many(all_items)

    return all_items

def scrape_week():
    
    today = datetime.now()
    weekly = {}

    for i in range(0,7):
        day = (today + timedelta(days=i)).date().strftime('%-m/%-d/%Y')
        weekly[day] = scrape_all_dining_halls(day)

    return weekly