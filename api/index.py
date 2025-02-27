from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import subprocess
import json
import os
from datetime import datetime
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # Log to stdout for Vercel
)

app = FastAPI(title="Pokémon TCG Stock Tracker API")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production to specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security - API Key setup
API_KEY = os.getenv("API_KEY", "your-default-api-key")  # Set a strong key in production
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Data models
class PriceThreshold(BaseModel):
    product_type: str
    price: float

class ScraperConfig(BaseModel):
    retailers: List[str]
    thresholds: Dict[str, float]
    check_interval: int = 1800  # Default 30 minutes

class Product(BaseModel):
    name: str
    price: float
    url: str
    store: str
    type: str
    image: Optional[str] = None

# Global state
last_results: List[Product] = []
last_update_time: Optional[datetime] = None
is_scraping: bool = False

# Path to the scraper script - update for Vercel
SCRAPER_SCRIPT = os.path.join(os.path.dirname(__file__), "pokemon_tcg_tracker.py")

# Helper function to verify API key
async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    raise HTTPException(
        status_code=403, detail="Invalid API key"
    )

# Endpoint to get in-stock products
@app.get("/api/products", response_model=List[Product])
async def get_products():
    return last_results

# Endpoint to get status information
@app.get("/api/status")
async def get_status():
    return {
        "last_update": last_update_time.isoformat() if last_update_time else None,
        "products_count": len(last_results),
        "is_scraping": is_scraping,
        "retailers": list(set(product.store for product in last_results)) if last_results else []
    }

# Simplified run_scraper function for Vercel deployment
async def run_scraper(config: ScraperConfig):
    global last_results, last_update_time, is_scraping
    
    try:
        is_scraping = True
        logging.info("Starting scraper with config: %s", config.dict())
        
        # For Vercel deployment, we'll use sample data since we can't run long processes
        # In a real implementation, you'd use a separate service or API for scraping
        sample_products = [
            {
                "name": "Pokémon TCG: Scarlet & Violet - Twilight Masquerade Booster Box",
                "price": 143.99,
                "url": "https://www.pokemoncenter.com/product/699-17070/",
                "store": "Pokemon Center",
                "type": "booster box"
            },
            {
                "name": "Pokémon TCG: Scarlet & Violet - Twilight Masquerade Elite Trainer Box",
                "price": 49.99,
                "url": "https://www.target.com/p/pokemon-tcg-scarlet-violet-elite-trainer-box/-/A-88392018",
                "store": "Target",
                "type": "elite trainer box"
            },
            {
                "name": "Pokémon TCG: Paldean Fates Premium Collection - Miraidon ex",
                "price": 39.99,
                "url": "https://www.bestbuy.com/site/pokemon-tcg-paldean-fates-premium-collection/6566306.p",
                "store": "Best Buy",
                "type": "premium collection"
            },
            {
                "name": "Pokémon TCG: Scarlet & Violet - Twilight Masquerade 3-Pack Blister",
                "price": 12.99,
                "url": "https://www.walmart.com/ip/pokemon-tcg-blister-pack/645383971",
                "store": "Walmart",
                "type": "blister pack"
            },
            {
                "name": "Pokémon TCG: Crown Zenith Special Collection - Pikachu VMAX",
                "price": 24.99,
                "url": "https://www.gamestop.com/pokemon-tcg-crown-zenith-special-collection/1992913.html",
                "store": "GameStop",
                "type": "special collection"
            }
        ]
        
        # Filter by selected retailers
        filtered_results = [r for r in sample_products if r["store"] in config.retailers]
        
        # Convert to Product objects
        products = []
        for item in filtered_results:
            product_type = item["type"]
            products.append(Product(
                name=item["name"],
                price=item["price"],
                url=item["url"],
                store=item["store"],
                type=product_type,
                image="/api/placeholder/400/320"
            ))
        
        # Update global state
        last_results = products
        last_update_time = datetime.now()
        
        logging.info("Scraper completed. Found %d products", len(products))
        
    except Exception as e:
        logging.error("Error running scraper: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error running scraper: {str(e)}")
    finally:
        is_scraping = False

# Original run_scraper function for local development
async def run_scraper_local(config: ScraperConfig):
    global last_results, last_update_time, is_scraping
    
    try:
        is_scraping = True
        logging.info("Starting scraper with config: %s", config.dict())
        
        # Write config to temporary file
        temp_config_path = os.path.join(os.path.dirname(__file__), "temp_config.json")
        with open(temp_config_path, "w") as f:
            json.dump({
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "check_interval": config.check_interval,
                "retail_price_thresholds": config.thresholds,
                "email_config": {}  # No email needed since we're using the API
            }, f, indent=2)
        
        # Run the scraper as a subprocess (one-time run, not continuous)
        process = subprocess.Popen(
            ["python", SCRAPER_SCRIPT, "--config", temp_config_path, "--once", "--json"],
            stdout=subprocess.PIPE
        )
        
        # Wait for process to complete and get output
        stdout, _ = process.communicate()
        
        # Parse results
        try:
            results = json.loads(stdout.decode('utf-8').strip())
            # Filter by selected retailers
            filtered_results = [r for r in results if r["store"] in config.retailers]
            
            # Convert to Product objects
            products = []
            for item in filtered_results:
                # Try to determine product type from name
                product_type = "other"
                for type_name in config.thresholds.keys():
                    if type_name.lower() in item["name"].lower():
                        product_type = type_name
                        break
                
                products.append(Product(
                    name=item["name"],
                    price=item["price"],
                    url=item["url"],
                    store=item["store"],
                    type=product_type,
                    image="/api/placeholder/400/320"
                ))
            
            # Update global state
            last_results = products
            last_update_time = datetime.now()
            
            logging.info("Scraper completed. Found %d products", len(products))
            
        except json.JSONDecodeError:
            logging.error("Failed to parse scraper output")
            raise HTTPException(status_code=500, detail="Failed to parse scraper output")
        
    except Exception as e:
        logging.error("Error running scraper: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error running scraper: {str(e)}")
    finally:
        is_scraping = False
        # Clean up
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)

# Endpoint to trigger scraper
@app.post("/api/scrape")
async def scrape(
    config: ScraperConfig, 
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(get_api_key)
):
    if is_scraping:
        raise HTTPException(status_code=409, detail="Scraper is already running")
    
    # Determine whether to use the local or Vercel-compatible function
    is_vercel = os.environ.get("VERCEL", "0") == "1"
    
    if is_vercel:
        # Use the simplified version for Vercel
        background_tasks.add_task(run_scraper, config)
    else:
        # Use the full version for local development
        background_tasks.add_task(run_scraper_local, config)
    
    return {"message": "Scraper started"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Modified scraper script for one-time execution
@app.post("/api/update-scraper")
async def update_scraper(api_key: APIKey = Depends(get_api_key)):
    """
    Update the scraper script to support one-time execution mode.
    This adds command line arguments to the original script.
    """
    try:
        # This function would modify the scraper script to support one-time execution
        # In a real implementation, you'd either version control your script or have this
        # modification built in from the start
        
        script_addition = """
# Add this to the bottom of your pokemon_tcg_tracker.py file:

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Pokemon TCG Stock Tracker')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--json', action='store_true', help='Output results as JSON to stdout')
    args = parser.parse_args()
    
    config_file = args.config if args.config else "config.json"
    tracker = PokemonTCGTracker(config_file)
    
    if args.once:
        # Run once and print results
        results = tracker.check_all_sites()
        if args.json:
            print(json.dumps(results))
        sys.exit(0)
    else:
        # Run continuously
        tracker.run()
        """
        
        return {"message": "Instructions for updating scraper script", "code": script_addition}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating scraper: {str(e)}")

# Main entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)