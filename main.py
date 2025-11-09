import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict
from email.utils import parsedate_to_datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


def fetch_rss_feed(url: str, limit: int = 6) -> List[Dict]:
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        # Support both RSS 2.0 (channel/item) and Atom (entry)
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item")[:limit]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                try:
                    dt = parsedate_to_datetime(pub) if pub else None
                except Exception:
                    dt = None
                items.append({
                    "title": title,
                    "link": link,
                    "published": pub,
                    "published_ts": dt.isoformat() if dt else None,
                    "source": url,
                })
        else:
            # Atom
            ns = {
                'atom': 'http://www.w3.org/2005/Atom'
            }
            for entry in root.findall('atom:entry', ns)[:limit]:
                title_el = entry.find('atom:title', ns)
                link_el = entry.find('atom:link', ns)
                updated_el = entry.find('atom:updated', ns)
                link = link_el.get('href') if link_el is not None else ''
                pub = updated_el.text if updated_el is not None else ''
                try:
                    dt = parsedate_to_datetime(pub) if pub else None
                except Exception:
                    dt = None
                items.append({
                    "title": title_el.text.strip() if title_el is not None else "",
                    "link": link,
                    "published": pub,
                    "published_ts": dt.isoformat() if dt else None,
                    "source": url,
                })
        return items
    except Exception as e:
        # Return empty list on failure to keep overall endpoint resilient
        return []

@app.get("/api/news")
def get_live_news(limit: int = 9):
    """Aggregate a handful of recent finance/education headlines from public RSS.
    This keeps everything server-side so the frontend just calls one endpoint.
    """
    feeds = [
        # General finance/markets suitable for parents (RSS)
        "https://www.nasdaq.com/feed/rssoutbound?category=Investing",
        "https://www.marketwatch.com/feeds/topstories",
        # Education/edtech general (RSS)
        "https://www.edweek.org/feeds/index.rss",
    ]
    collected: List[Dict] = []
    for u in feeds:
        collected.extend(fetch_rss_feed(u, limit=limit))

    # Deduplicate by link
    seen = set()
    unique: List[Dict] = []
    for it in collected:
        if not it.get("link"):
            continue
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        unique.append(it)

    # Sort by published_ts (desc), fall back to original order
    def sort_key(x):
        return x.get("published_ts") or ""

    unique.sort(key=sort_key, reverse=True)
    trimmed = unique[:limit]
    return {"items": trimmed, "count": len(trimmed)}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
