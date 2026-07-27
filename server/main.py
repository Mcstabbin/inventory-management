from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Supplier lead time in days by product category. Restocking uses this plus the
# destination warehouse's transit time to quote an expected delivery date.
LEAD_TIME_DAYS_BY_CATEGORY = {
    'Circuit Boards': 21,
    'Controllers': 28,
    'Power Supplies': 14,
    'Sensors': 10,
    'Actuators': 18
}
DEFAULT_LEAD_TIME_DAYS = 14
WAREHOUSE_TRANSIT_DAYS = {
    'San Francisco': 2,
    'London': 5,
    'Tokyo': 7
}
DEFAULT_TRANSIT_DAYS = 4

# Submitted restocking orders live in process memory, same as the rest of this
# demo's write paths - restarting the server clears them.
restock_orders = []

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockRecommendation(BaseModel):
    sku: str
    name: str
    category: str
    warehouse: str
    unit_cost: float
    quantity_on_hand: int
    reorder_point: int
    target_stock: int
    deficit: int
    full_cost: float
    funded_quantity: int
    funded_cost: float
    funding: str  # funded | partial | deferred
    priority: str  # high | medium | low
    urgency_score: float
    lead_time_days: int
    forecast_trend: Optional[str] = None
    forecasted_demand: Optional[int] = None

class RestockPlan(BaseModel):
    budget: float
    max_budget: float
    total_cost: float
    remaining_budget: float
    funded_items: int
    funded_units: int
    deferred_items: int
    recommendations: List[RestockRecommendation]

class RestockOrderLine(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_cost: float
    line_total: float

class RestockOrder(BaseModel):
    id: str
    order_number: str
    status: str
    created_date: str
    expected_delivery: str
    lead_time_days: int
    budget: Optional[float] = None
    total_value: float
    items: List[RestockOrderLine]
    notes: Optional[str] = None

class RestockOrderLineRequest(BaseModel):
    sku: str
    quantity: int

class CreateRestockOrderRequest(BaseModel):
    items: List[RestockOrderLineRequest]
    budget: Optional[float] = None
    notes: Optional[str] = None

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

def lead_time_for(category: str, warehouse: str) -> int:
    """Total days from order to arrival: supplier build time plus inbound transit."""
    supplier_days = LEAD_TIME_DAYS_BY_CATEGORY.get(category, DEFAULT_LEAD_TIME_DAYS)
    transit_days = WAREHOUSE_TRANSIT_DAYS.get(warehouse, DEFAULT_TRANSIT_DAYS)
    return supplier_days + transit_days

def build_restock_candidates(warehouse: Optional[str] = None,
                             category: Optional[str] = None) -> list:
    """Score every inventory item that needs replenishing, most urgent first.

    Target stock is the reorder point plus a cover layer. When a demand forecast
    exists for the SKU the cover layer is the forecasted demand itself; otherwise
    we fall back to half the reorder point as generic safety stock. Only 1 of the
    9 forecast SKUs currently matches inventory, so most items take the fallback.
    """
    forecast_by_sku = {f['item_sku']: f for f in demand_forecasts}
    candidates = []

    for item in apply_filters(inventory_items, warehouse, category):
        reorder_point = item['reorder_point']
        on_hand = item['quantity_on_hand']
        forecast = forecast_by_sku.get(item['sku'])

        if forecast:
            cover = forecast['forecasted_demand']
        else:
            cover = int(round(reorder_point * 0.5))

        target_stock = reorder_point + cover
        deficit = max(0, target_stock - on_hand)
        if deficit == 0:
            continue

        # Urgency = how much of the target is unmet, with a hard boost for items
        # already under the reorder point (operationally the ones that stock out),
        # and a rising forecast breaking ties toward items that drain fastest.
        coverage = on_hand / target_stock if target_stock else 0
        base_score = max(0.0, min(60.0, (1 - coverage) * 60))
        below_reorder_boost = 25 if on_hand < reorder_point else 0
        trend_bonus = {'increasing': 15, 'stable': 6, 'decreasing': 0}.get(
            forecast['trend'] if forecast else None, 3)
        urgency_score = round(min(100.0, base_score + below_reorder_boost + trend_bonus), 1)

        candidates.append({
            'sku': item['sku'],
            'name': item['name'],
            'category': item['category'],
            'warehouse': item['warehouse'],
            'unit_cost': item['unit_cost'],
            'quantity_on_hand': on_hand,
            'reorder_point': reorder_point,
            'target_stock': target_stock,
            'deficit': deficit,
            'full_cost': round(deficit * item['unit_cost'], 2),
            'funded_quantity': 0,
            'funded_cost': 0.0,
            'funding': 'deferred',
            'priority': 'high' if urgency_score >= 60 else 'medium' if urgency_score >= 35 else 'low',
            'urgency_score': urgency_score,
            'lead_time_days': lead_time_for(item['category'], item['warehouse']),
            'forecast_trend': forecast['trend'] if forecast else None,
            'forecasted_demand': forecast['forecasted_demand'] if forecast else None
        })

    # Most urgent first; cheaper first on a tie so a tight budget covers more lines.
    candidates.sort(key=lambda c: (-c['urgency_score'], c['full_cost']))
    return candidates

@app.get("/api/restocking/recommendations", response_model=RestockPlan)
def get_restock_recommendations(
    budget: Optional[float] = Query(None, ge=0),
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Recommend what to restock within a budget, most urgent items first.

    Allocation is a single greedy pass over the urgency ordering. The first item
    that cannot be fully funded is topped up with whatever budget remains (a
    partial line), and everything after it is reported as deferred so the UI can
    show what the budget is leaving on the table.
    """
    candidates = build_restock_candidates(warehouse, category)
    max_budget = round(sum(c['full_cost'] for c in candidates), 2)

    # No budget supplied means "show me the full picture" rather than "spend nothing".
    remaining = max_budget if budget is None else budget

    for candidate in candidates:
        if remaining <= 0:
            break
        if candidate['full_cost'] <= remaining:
            candidate['funded_quantity'] = candidate['deficit']
            candidate['funded_cost'] = candidate['full_cost']
            candidate['funding'] = 'funded'
            remaining = round(remaining - candidate['full_cost'], 2)
        else:
            affordable_units = int(remaining // candidate['unit_cost'])
            if affordable_units > 0:
                candidate['funded_quantity'] = affordable_units
                candidate['funded_cost'] = round(affordable_units * candidate['unit_cost'], 2)
                candidate['funding'] = 'partial'
                remaining = round(remaining - candidate['funded_cost'], 2)

    total_cost = round(sum(c['funded_cost'] for c in candidates), 2)
    effective_budget = max_budget if budget is None else budget

    return {
        'budget': round(effective_budget, 2),
        'max_budget': max_budget,
        'total_cost': total_cost,
        'remaining_budget': round(effective_budget - total_cost, 2),
        'funded_items': len([c for c in candidates if c['funding'] != 'deferred']),
        'funded_units': sum(c['funded_quantity'] for c in candidates),
        'deferred_items': len([c for c in candidates if c['funding'] == 'deferred']),
        'recommendations': candidates
    }

@app.get("/api/restocking/orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get restocking orders submitted during this server session, newest first."""
    return list(reversed(restock_orders))

@app.post("/api/restocking/orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restocking order. Lead time is the slowest line in the order."""
    if not request.items:
        raise HTTPException(status_code=400, detail="A restocking order needs at least one item")

    inventory_by_sku = {item['sku']: item for item in inventory_items}
    lines = []
    lead_time_days = 0

    for line in request.items:
        item = inventory_by_sku.get(line.sku)
        if not item:
            raise HTTPException(status_code=404, detail=f"Unknown SKU {line.sku}")
        if line.quantity < 1:
            raise HTTPException(status_code=400, detail=f"Quantity for {line.sku} must be at least 1")

        lines.append({
            'sku': item['sku'],
            'name': item['name'],
            'quantity': line.quantity,
            'unit_cost': item['unit_cost'],
            'line_total': round(line.quantity * item['unit_cost'], 2)
        })
        # The whole order lands when its slowest line lands.
        lead_time_days = max(lead_time_days, lead_time_for(item['category'], item['warehouse']))

    created = datetime.now()
    order = {
        'id': f"RSO-{len(restock_orders) + 1:04d}",
        'order_number': f"RSO-{len(restock_orders) + 1:04d}",
        'status': 'Submitted',
        'created_date': created.strftime('%Y-%m-%d'),
        'expected_delivery': (created + timedelta(days=lead_time_days)).strftime('%Y-%m-%d'),
        'lead_time_days': lead_time_days,
        'budget': round(request.budget, 2) if request.budget is not None else None,
        'total_value': round(sum(line['line_total'] for line in lines), 2),
        'items': lines,
        'notes': request.notes
    }
    restock_orders.append(order)
    return order

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
