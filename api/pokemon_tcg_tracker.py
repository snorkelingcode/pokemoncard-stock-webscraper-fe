import requests
from bs4 import BeautifulSoup
import time
import smtplib
from email.mime.text import MIMEText
import logging
import json
from datetime import datetime
import argparse
import sys
import re
import random
from urllib.parse import urljoin


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='pokemon_tcg_tracker.log'
)

class PokemonTCGTracker:
    def __init__(self, config_file="config.json"):
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        # Use a list of user agents to rotate
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
        ]
        self.check_interval = self.config.get('check_interval', 1800)  # Default 30 minutes
        self.retail_price_thresholds = self.config.get('retail_price_thresholds', {})
        self.email_config = self.config.get('email_config', {})
        
        # Store results
        self.in_stock_items = []
        
        # Create a session that we'll reuse
        self.session = requests.Session()
        
        # Set up recent expansions for validation
        self.recent_expansions = [
            'scarlet', 'violet', 'paldea', 'paradox rift', 'twilight masquerade',
            'temporal forces', 'pocket monsters', 'obsidian flames', 'paldean fates',
            '151', 'crown zenith', 'silver tempest', 'lost origin',
            'astral radiance', 'brilliant stars', 'celebrations'
        ]
        
        # Store for direct GameStop product URLs
        self.gamestop_product_urls = [
            "https://www.gamestop.com/toys-games/trading-cards/products/pokemon-trading-card-game-scarlet-and-violet-151-elite-trainer-box/368947.html",
            "https://www.gamestop.com/toys-games/trading-cards/products/pokemon-trading-card-game-crown-zenith-special-collection-pikachu-vmax/351599.html",
            "https://www.gamestop.com/toys-games/trading-cards/products/pokemon-trading-card-game-scarlet-and-violet-paldean-fates-elite-trainer-box/377146.html",
            "https://www.gamestop.com/toys-games/trading-cards/products/pokemon-trading-card-game-scarlet-and-violet-twilight-masquerade-booster-box/393851.html",
            "https://www.gamestop.com/toys-games/trading-cards/products/pokemon-trading-card-game-scarlet-and-violet-twilight-masquerade-elite-trainer-box/393846.html"
        ]
    
    def get_headers(self):
        """Generate request headers to mimic a browser"""
        # Randomly select a user agent
        user_agent = random.choice(self.user_agents)
        
        return {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    
    def fetch_page(self, url):
        """Fetch a page with improved anti-bot circumvention"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Add random delay to mimic human behavior
                delay = random.uniform(1, 3)
                time.sleep(delay)
                
                # Use our session with fresh headers each time
                headers = self.get_headers()
                
                # Add cookies from previous requests
                response = self.session.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Check for anti-bot measures
                if "captcha" in response.text.lower() or "robot" in response.text.lower():
                    logging.warning(f"CAPTCHA detected on {url}, retrying...")
                    # Wait longer before retry
                    time.sleep(random.uniform(5, 10))
                    continue
                    
                # Check for very small responses (usually blocking)
                if len(response.text) < 1000 and "403" in response.text:
                    logging.warning(f"Possible block on {url}, response too small")
                    time.sleep(random.uniform(5, 10))
                    continue
                    
                return response.text
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching {url}: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(1, 3)  # Exponential backoff with jitter
                    logging.info(f"Retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                    return None
    
    def validate_product_link(self, product_url, expected_type, expected_name=None):
        """
        Validate that a product URL leads to the expected product type
        Returns True if the product page matches expectations
        """
        try:
            html = self.fetch_page(product_url)
            if not html:
                return False
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract the actual product title from the product page
            product_title = None
            # Try different selectors for product title on different sites
            title_selectors = ['h1.product-name', '.product-title', '.pdp-title', 'h1.title', '.product-detail-name']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    product_title = title_elem.text.strip()
                    break
            
            if not product_title:
                return False
            
            # If we have an expected name, check it
            if expected_name and expected_name.lower() not in product_title.lower():
                logging.info(f"Product name mismatch. Expected: '{expected_name}', Found: '{product_title}'")
                return False
            
            # Check if the product title contains the expected product type
            product_title_lower = product_title.lower()
            expected_type_lower = expected_type.lower()
            
            # For booster box, check for both "booster" and "box"
            if expected_type_lower == "booster box":
                return "booster" in product_title_lower and "box" in product_title_lower
            
            # For ETB
            if expected_type_lower == "elite trainer box" or expected_type_lower == "etb":
                return ("elite" in product_title_lower and "trainer" in product_title_lower) or "etb" in product_title_lower
            
            # For other products, check if the type is in the title
            return expected_type_lower in product_title_lower
            
        except Exception as e:
            logging.error(f"Error validating product link {product_url}: {str(e)}")
            return False
    
    def determine_product_type(self, product_name):
        """
        Determine the product type based on the name
        Returns the product type or "unknown" if it can't be determined
        """
        name_lower = product_name.lower()
        
        # Check for obvious product types
        if 'booster box' in name_lower:
            return 'booster box'
        elif 'elite trainer box' in name_lower or ' etb' in name_lower:
            return 'elite trainer box'
        elif ('booster pack' in name_lower) or (('pack' in name_lower or 'packs' in name_lower) and 'booster' not in name_lower):
            return 'booster pack'
        elif 'tin' in name_lower:
            return 'tin'
        elif 'special collection' in name_lower:
            return 'special collection'
        elif 'premium collection' in name_lower:
            return 'premium collection'
        elif 'blister pack' in name_lower or 'blister' in name_lower:
            return 'blister pack'
        elif 'bundle' in name_lower:
            return 'bundle'
        elif 'battle deck' in name_lower or 'theme deck' in name_lower:
            return 'deck'
        
        # Check for more generic terms
        if 'box' in name_lower and ('booster' in name_lower or 'boosters' in name_lower):
            return 'booster box'
        elif 'box' in name_lower and ('elite' in name_lower or 'trainer' in name_lower):
            return 'elite trainer box'
        elif 'collection' in name_lower and 'premium' in name_lower:
            return 'premium collection'
        elif 'collection' in name_lower:
            return 'special collection'
        
        # If it has cards or tcg but we couldn't determine the type
        if any(term in name_lower for term in ['trading card', 'tcg', 'cards']):
            # Default to booster pack as the most common item
            if 'pack' in name_lower:
                return 'booster pack'
            else:
                return 'special collection'  # Generic fallback
        
        return "unknown"  # Can't determine the type
    
    def validate_products(self, products):
        """
        Apply strict validation to ensure only TCG products are included
        Returns a filtered list of verified products
        """
        validated_products = []
        
        # TCG-specific keywords that should appear in product names
        tcg_keywords = [
            'booster', 'pack', 'elite trainer box', 'etb', 'tin', 'collection',
            'tcg ', 'trading card game', 'pokemon cards', 'card box', 'deck',
            'display box', 'paldea', 'scarlet', 'violet', 'paradox', 'tera'
        ]
        
        # Terms that indicate NON-TCG products
        exclude_terms = [
            'plush', 'figure', 'toy', 'funko', 'costume', 'shirt', 't-shirt',
            'video game', 'switch', 'playmat', 'binder', 'sleeves', 'case',
            'storage', 'phone', 'poster', 'hat', 'bag', 'backpack', 'keychain',
            'notebook', 'sticker', 'mug', 'controller', 'console'
        ]
        
        for product in products:
            # Skip products with validation errors or without URLs
            if 'validation_error' in product and product['validation_error']:
                continue
                
            if 'url' not in product or not product['url']:
                continue
                
            name = product['name'].lower()
            url = product['url'].lower()
            
            # Skip if name contains any excluded terms
            if any(term in name for term in exclude_terms):
                logging.info(f"Excluding product as it contains excluded term: {product['name']}")
                continue
                
            # Skip if URL contains suspicious patterns
            if any(term in url for term in ['apparel', 'accessories', 'toys', 'plush', 'games', 'collectibles/figures']):
                logging.info(f"Excluding product with non-TCG URL pattern: {url}")
                continue
                
            # Must contain at least one TCG keyword
            if not any(keyword in name for keyword in tcg_keywords):
                logging.info(f"Excluding product without TCG keywords: {product['name']}")
                continue
                
            # If product type doesn't match name, skip (unless it's our best guess "unknown")
            if 'type' in product and product['type'] != 'unknown' and product['type'] not in name:
                # Allow some exceptions (e.g., "booster box" might just say "box" in the name)
                if not (product['type'] == 'booster box' and 'box' in name and 'booster' in name):
                    logging.info(f"Excluding product with type mismatch: {product['name']} (type: {product['type']})")
                    continue
            
            # Further verification - must EITHER:
            # 1. Contain a specific recent expansion name to confirm it's current TCG product
            # 2. Have very specific TCG terms that are unlikely to be anything else
            has_expansion = any(exp in name for exp in self.recent_expansions)
            has_definite_tcg_terms = any(term in name for term in ['booster box', 'elite trainer box', 'pokemon tcg', 'trading card game'])
            
            if not (has_expansion or has_definite_tcg_terms):
                logging.info(f"Excluding product without recent expansion or definite TCG terms: {product['name']}")
                continue
            
            # Passed all checks - add to validated list
            validated_products.append(product)
            
        return validated_products
    
    def check_pokemoncenter(self):
        """Check Pokemon Center official site with improved filtering"""
        logging.info("Checking Pokemon Center...")
        url = "https://www.pokemoncenter.com/category/trading-card-game"  # More specific URL
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements with more specific selectors
        product_elements = soup.select('.product-grid-item') or soup.select('.product-item')
        
        for product in product_elements:
            try:
                # Try different possible selectors for different page layouts
                name_elem = (product.select_one('.product-tile-title') or 
                             product.select_one('.product-name') or 
                             product.select_one('.product-grid-item-name'))
                
                price_elem = (product.select_one('.product-tile-price') or 
                              product.select_one('.product-price') or 
                              product.select_one('.product-grid-item-price'))
                
                availability_elem = (product.select_one('.product-tile-availability') or 
                                     product.select_one('.product-availability'))
                
                url_elem = (product.select_one('a.product-tile-link') or 
                            product.select_one('a.product-link') or 
                            product.select_one('a[href*="product"]'))
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                
                # Filter by TCG keywords to ensure we only get card products
                tcg_keywords = ['booster', 'pack', 'box', 'etb', 'elite trainer', 'tin', 'collection', 
                               'deck', 'tcg', 'card', 'pokemon cards', 'trading card']
                
                if not any(keyword in name.lower() for keyword in tcg_keywords):
                    continue  # Skip non-TCG products
                    
                price_text = price_elem.text.strip()
                # Extract numbers from the price text (handles different formats)
                price_match = re.search(r'(\d+\.\d+)', price_text)
                if not price_match:
                    continue
                
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    continue  # Skip if price can't be parsed
                    
                product_url = url_elem['href']
                if not product_url.startswith('http'):
                    product_url = "https://www.pokemoncenter.com" + product_url
                
                # Double-check URL contains TCG-related terms
                if not any(term in product_url.lower() for term in ['trading-card', 'tcg', 'booster', 'cards']):
                    continue
                
                # Check if in stock
                in_stock_status = availability_elem and ("in stock" in availability_elem.text.lower() or 
                                                         "add to cart" in availability_elem.text.lower())
                
                if not in_stock_status:
                    continue
                
                # Determine product type
                product_type = self.determine_product_type(name)
                
                # Check if price is at retail level
                is_retail_price = False
                for type_name, threshold in self.retail_price_thresholds.items():
                    if type_name.lower() in product_type.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if not is_retail_price:
                    continue
                
                # Validate the product link before adding it
                validation_success = self.validate_product_link(product_url, product_type, name)
                
                if not validation_success:
                    logging.info(f"Validation failed for product: {name} - {product_url}")
                    continue
                
                # All checks passed, add the product
                in_stock.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'store': 'Best Buy',
                    'type': product_type,
                    'validation_error': False
                })
                logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing Best Buy product: {str(e)}")        
                # Determine product type
                product_type = self.determine_product_type(name)
                
                # Check if price is at retail level
                is_retail_price = False
                for type_name, threshold in self.retail_price_thresholds.items():
                    if type_name.lower() in product_type.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if not is_retail_price:
                    continue
                
                # Validate the product link before adding it
                validation_success = self.validate_product_link(product_url, product_type, name)
                
                if not validation_success:
                    logging.info(f"Validation failed for product: {name} - {product_url}")
                    continue
                
                # All checks passed, add the product
                in_stock.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'store': 'Pokemon Center',
                    'type': product_type,
                    'validation_error': False
                })
                logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing Pokemon Center product: {str(e)}")
        
        return in_stock
    
    def check_target(self):
        """Check Target for Pokemon cards with improved filtering"""
        logging.info("Checking Target...")
        url = "https://www.target.com/s?searchTerm=pokemon+trading+cards"  # Search query approach
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements - try different possible selectors
        product_elements = (soup.select('[data-test="product-list-ship-item"]') or 
                           soup.select('[data-test="product-card"]') or 
                           soup.select('.styles__StyledItem-sc-1on7yz9-0'))
        
        for product in product_elements:
            try:
                # Try different possible selectors
                name_elem = (product.select_one('[data-test="product-title"]') or 
                            product.select_one('.styles__StyledTitleLink-sc-1on7yz9-6'))
                
                price_elem = (product.select_one('[data-test="product-price"]') or 
                             product.select_one('.styles__StyledPricePromoWrapper-sc-1on7yz9-4'))
                
                url_elem = (product.select_one('a[data-test="product-title-link"]') or 
                           product.select_one('a[href^="/p/"]'))
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                
                # Filter by TCG keywords
                tcg_keywords = ['booster', 'pack', 'box', 'etb', 'elite trainer', 'tin', 'collection', 
                               'deck', 'tcg', 'trading card game', 'pokemon cards']
                
                if not any(keyword in name.lower() for keyword in tcg_keywords):
                    continue  # Skip non-TCG products
                    
                # Exclude known non-TCG products
                exclude_terms = ['plush', 'figure', 'toy', 'costume', 'shirt', 'game', 'video game', 
                                'switch', 'playmat', 'binder', 'sleeves', 'case', 'storage']
                
                if any(term in name.lower() for term in exclude_terms):
                    continue
                
                # Extract the price using regex to handle different formats
                price_text = price_elem.text.strip()
                price_match = re.search(r'(\d+\.\d+)', price_text)
                if not price_match:
                    continue
                    
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    continue
                    
                product_url = url_elem['href']
                if not product_url.startswith('http'):
                    product_url = "https://www.target.com" + product_url
                
                # Availability is harder to determine on Target - we'll assume it's in stock if we can see it
                in_stock_status = True
                
                # Determine product type
                product_type = self.determine_product_type(name)
                
                # Check if price is at retail level
                is_retail_price = False
                for type_name, threshold in self.retail_price_thresholds.items():
                    if type_name.lower() in product_type.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if not is_retail_price:
                    continue
                
                # Validate the product link before adding it
                validation_success = self.validate_product_link(product_url, product_type, name)
                
                if not validation_success:
                    logging.info(f"Validation failed for product: {name} - {product_url}")
                    continue
                
                # All checks passed, add the product
                in_stock.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'store': 'Target',
                    'type': product_type,
                    'validation_error': False
                })
                logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing Target product: {str(e)}")
        
        return in_stock
    
    def check_walmart(self):
        """Check Walmart for Pokemon cards with improved filtering"""
        logging.info("Checking Walmart...")
        url = "https://www.walmart.com/search?q=pokemon+trading+cards"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Try different possible selectors for products
        product_elements = (soup.select('[data-item-id]') or 
                           soup.select('.product-item') or 
                           soup.select('[data-testid="list-view"]'))
        
        for product in product_elements:
            try:
                # Try different possible selectors
                name_elem = (product.select_one('.ellipsis-title') or 
                            product.select_one('[data-automation="product-title"]') or
                            product.select_one('span.f6-m') or
                            product.select_one('span.lh-title'))
                
                price_elem = (product.select_one('.price-main') or 
                             product.select_one('[data-automation="product-price"]') or
                             product.select_one('div.b.black.f4-l.ph1'))
                
                url_elem = product.select_one('a[href^="/ip/"]')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                
                # Filter by TCG keywords
                tcg_keywords = ['booster', 'pack', 'box', 'etb', 'elite trainer', 'tin', 'collection', 
                               'deck', 'tcg', 'trading card game', 'pokemon cards']
                
                if not any(keyword in name.lower() for keyword in tcg_keywords):
                    continue  # Skip non-TCG products
                    
                # Exclude known non-TCG products
                exclude_terms = ['plush', 'figure', 'toy', 'costume', 'shirt', 'game', 'video game', 
                                'switch', 'playmat', 'binder', 'sleeves', 'case', 'storage']
                
                if any(term in name.lower() for term in exclude_terms):
                    continue
                
                # Extract the price using regex to handle different formats
                price_text = price_elem.text.strip()
                price_match = re.search(r'(\d+\.\d+)', price_text)
                if not price_match:
                    continue
                    
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    continue
                    
                product_url = url_elem['href']
                if not product_url.startswith('http'):
                    product_url = "https://www.walmart.com" + product_url
                
                # Since we're looking at search results, we'll assume items are in stock
                in_stock_status = True
                
                # Determine product type
                product_type = self.determine_product_type(name)
                
                # Check if price is at retail level
                is_retail_price = False
                for type_name, threshold in self.retail_price_thresholds.items():
                    if type_name.lower() in product_type.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if not is_retail_price:
                    continue
                
                # Validate the product link before adding it
                validation_success = self.validate_product_link(product_url, product_type, name)
                
                if not validation_success:
                    logging.info(f"Validation failed for product: {name} - {product_url}")
                    continue
                
                # All checks passed, add the product
                in_stock.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'store': 'Walmart',
                    'type': product_type,
                    'validation_error': False
                })
                logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing Walmart product: {str(e)}")
        
        return in_stock
    
def check_bestbuy(self):
    """Check Best Buy for Pokemon cards with improved filtering"""
    logging.info("Checking Best Buy...")
    url = "https://www.bestbuy.com/site/searchpage.jsp?st=pokemon+trading+card+game"
    html = self.fetch_page(url)
    
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    in_stock = []
    
    # Try different possible selectors for products
    product_elements = (soup.select('.sku-item') or 
                       soup.select('.list-item') or
                       soup.select('.product-item'))
    
    for product in product_elements:
        try:
            # Try different possible selectors
            name_elem = (product.select_one('.sku-title a') or 
                        product.select_one('.sku-header a') or
                        product.select_one('.product-title'))
            
            price_elem = (product.select_one('.priceView-customer-price span') or 
                         product.select_one('.pricing-price span') or
                         product.select_one('.price-block'))
            
            # Best Buy shows "Add to Cart" button only for in-stock items
            availability_elem = (product.select_one('.fulfillment-add-to-cart-button button') or
                                product.select_one('.add-to-cart-button'))
            
            url_elem = name_elem  # The name element is usually a link
            
            if not all([name_elem, price_elem, url_elem]):
                continue
            
            name = name_elem.text.strip()
            
            # Filter by TCG keywords
            tcg_keywords = ['booster', 'pack', 'box', 'etb', 'elite trainer', 'tin', 'collection', 
                           'deck', 'tcg', 'trading card', 'pokemon cards']
            
            if not any(keyword in name.lower() for keyword in tcg_keywords):
                continue  # Skip non-TCG products
                
            # Exclude known non-TCG products
            exclude_terms = ['plush', 'figure', 'toy', 'costume', 'shirt', 'game', 'video game', 
                           'switch', 'playmat', 'binder', 'sleeves', 'case', 'storage']
            
            if any(term in name.lower() for term in exclude_terms):
                continue
                
            # Extract the price using regex to handle different formats
            price_text = price_elem.text.strip()
            price_match = re.search(r'(\d+\.\d+)', price_text)
            if not price_match:
                continue
                
            try:
                price = float(price_match.group(1))
            except ValueError:
                continue
                
            product_url = url_elem['href']
            if not product_url.startswith('http'):
                product_url = "https://www.bestbuy.com" + product_url
            
            # Check if in stock (button exists and doesn't say "Sold Out")
            in_stock_status = availability_elem and "sold out" not in availability_elem.text.lower()
            
            if not in_stock_status:
                continue
            
            # Determine product type
            product_type = self.determine_product_type(name)
            
            # Check if price is at retail level
            is_retail_price = False
            for type_name, threshold in self.retail_price_thresholds.items():
                if type_name.lower() in product_type.lower() and price <= threshold:
                    is_retail_price = True
                    break
            
            if is_retail_price:
                in_stock.append({
                    'name': name,
                    'price': price,
                    'url': product_url,
                    'store': 'Best Buy',
                    'type': product_type
                })
                logging.info(f"Found in-stock item at retail price: {name} - ${price}")
        
        except Exception as e:
            logging.error(f"Error processing Best Buy product: {str(e)}")

            
    
    return in_stock