# Shopping List Skill

## Overview
Stateful shopping list management with session support. Users can create lists, add items with quantities, check off items, and close sessions.

## Key Files
- `app/services/shopping.py` - Shopping list business logic
- `app/routers/shopping.py` - REST API endpoints
- `app/bot.py` - Telegram command handlers

## State Management
- Each user has one active shopping list at a time
- Lists persist until explicitly closed
- Checked items can be bulk-cleared

## Database Schema
```sql
-- Shopping lists (sessions)
shopping_lists (
    id UUID,
    user_id INTEGER,
    name VARCHAR,
    is_active BOOLEAN,
    created_at TIMESTAMP,
    closed_at TIMESTAMP
)

-- Shopping items
shopping_items (
    id UUID,
    list_id UUID,
    item_name VARCHAR,
    quantity INTEGER,
    unit VARCHAR,
    is_checked BOOLEAN
)
```

## Telegram Commands
- `/add <item>` - Add item (parses quantity/unit: `/add 2 kg apples`)
- `/list` - Show current shopping list
- `/check <item>` - Mark item as done (by name match)
- `/clear` - Remove all checked items
- `/done` - Close current shopping session

## API Endpoints
- `GET /api/shopping/list` - Get current list
- `POST /api/shopping/items` - Add item
- `PATCH /api/shopping/items/{id}/check` - Check item
- `DELETE /api/shopping/items/{id}` - Remove item
- `POST /api/shopping/clear-checked` - Clear checked
- `POST /api/shopping/close` - Close session

## Parsing Logic
Input: `/add 2 kg apples`
- quantity: 2
- unit: kg
- item_name: apples

Supported units: kg, g, l, ml, pcs, units, liters, bottles
