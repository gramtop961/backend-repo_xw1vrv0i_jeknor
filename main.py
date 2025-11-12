import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, Order

app = FastAPI(title="Dmart-like Shopping API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Shopping API is running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, 'name', None) or "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# -----------------------------
# Catalog Endpoints
# -----------------------------

@app.post("/api/products", response_model=dict)
def add_product(product: Product):
    try:
        product_id = create_document("product", product)
        return {"id": product_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products", response_model=List[dict])
def list_products():
    try:
        docs = get_documents("product")
        for d in docs:
            d["id"] = str(d.pop("_id", ""))
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------
# Order / Billing Endpoints
# -----------------------------

class CartItem(BaseModel):
    product_id: str
    quantity: int

class CheckoutRequest(BaseModel):
    customer_name: str
    customer_email: str
    customer_address: str
    items: List[CartItem]

@app.post("/api/checkout", response_model=dict)
def checkout(payload: CheckoutRequest):
    try:
        # Fetch product details and compute totals
        product_map = {}
        product_ids = [ObjectId(i.product_id) for i in payload.items]
        products = db["product"].find({"_id": {"$in": product_ids}})
        for p in products:
            product_map[str(p["_id"])]=p

        if len(product_map) != len(product_ids):
            raise HTTPException(status_code=400, detail="One or more products not found")

        line_items = []
        subtotal = 0.0
        for item in payload.items:
            prod = product_map.get(item.product_id)
            unit_price = float(prod.get("price", 0))
            line_total = unit_price * item.quantity
            subtotal += line_total
            line_items.append({
                "product_id": item.product_id,
                "title": prod.get("title"),
                "quantity": item.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            })

        tax_rate = 0.1  # 10% tax example
        tax = round(subtotal * tax_rate, 2)
        total = round(subtotal + tax, 2)

        invoice_number = f"INV-{ObjectId()}"[-8:]

        order = Order(
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            customer_address=payload.customer_address,
            items=line_items,
            subtotal=round(subtotal, 2),
            tax=tax,
            total=total,
            invoice_number=invoice_number,
        )

        order_id = create_document("order", order)
        return {
            "order_id": order_id,
            "invoice_number": invoice_number,
            "subtotal": round(subtotal, 2),
            "tax": tax,
            "total": total,
            "items": line_items,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
