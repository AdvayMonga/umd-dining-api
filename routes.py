from flask import jsonify, request
from app import app, db
from datetime import datetime


@app.route('/')
def home():
    return jsonify({
        'message': 'UMD Dining API is running!',
        'version': '1.0',
        'endpoints': {
            'dining_halls': '/api/dining-halls',
            'menu': '/api/menu',
            'search': '/api/search'
        }
    })

@app.get('/api/dining-halls')
def get_dining_halls():
    try:
        halls = list(db.dining_halls.find({}, {'_id': 0}))
        return jsonify({
            'success': True,
            'count': len(halls),
            'data': halls
        })
    except Exception as e:
        return jsonify({'success': False,'error': str(e)}), 500

@app.get('/api/menu')
def get_menu():
    try:
        query = {}

        dining_hall_id = request.args.get('dining_hall_id')
        date = request.args.get('date')
        meal_period = request.args.get('meal_period')

        if dining_hall_id:
            query['dining_hall_id'] = dining_hall_id

        if date:
            query['date'] = date

        if meal_period:
            query['meal_period'] = meal_period.lower()

        items = list(db.menu_items.find(query, {'_id': 0}).sort('station', 1))

        return jsonify({
            'success': True,
            'count': len(items),
            'filters': query,
            'data': items
        })
    except Exception as e:
        return jsonify({'success': False,'error': str(e)}), 500

@app.get('/api/search')
def search_menu():
    """Search menu items by name"""
    try:
        search_query = request.args.get('q', '')

        if not search_query:
            return jsonify({'success': False,'error': 'Search query required'}), 400

        items = list(db.menu_items.find(
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'_id': 0}
        ).limit(50))

        return jsonify({
            'success': True,
            'query': search_query,
            'count': len(items),
            'data': items
        })
    except Exception as e:
        return jsonify({'success': False,'error': str(e)}), 500
