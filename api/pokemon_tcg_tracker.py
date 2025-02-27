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
        
        self.user_agent = self.config.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        self.check_interval = self.config.get('check_interval', 1800)  # Default 30 minutes
        self.retail_price_thresholds = self.config.get('retail_price_thresholds', {})
        self.email_config = self.config.get('email_config', {})
        
        # Store results
        self.in_stock_items = []
    
    def get_headers(self):
        """Generate request headers to mimic a browser"""
        return {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def fetch_page(self, url):
        """Fetch a page with error handling and retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.get_headers(), timeout=10)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching {url}: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logging.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                    return None
    
    def check_pokemoncenter(self):
        """Check Pokemon Center official site"""
        logging.info("Checking Pokemon Center...")
        url = "https://www.pokemoncenter.com/category/trading-cards"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements (adjust selectors based on actual site structure)
        product_elements = soup.select('.product-item')
        
        for product in product_elements:
            try:
                name_elem = product.select_one('.product-name')
                price_elem = product.select_one('.product-price')
                availability_elem = product.select_one('.product-availability')
                url_elem = product.select_one('a.product-link')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                price = float(price_text)
                product_url = "https://www.pokemoncenter.com" + url_elem['href']
                
                # Check if in stock
                in_stock_status = availability_elem and "in stock" in availability_elem.text.lower()
                
                # Check if price is at retail level
                is_retail_price = False
                for product_type, threshold in self.retail_price_thresholds.items():
                    if product_type.lower() in name.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if in_stock_status and is_retail_price:
                    in_stock.append({
                        'name': name,
                        'price': price,
                        'url': product_url,
                        'store': 'Pokemon Center'
                    })
                    logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing product: {str(e)}")
        
        return in_stock
    
    def check_target(self):
        """Check Target for Pokemon cards"""
        logging.info("Checking Target...")
        url = "https://www.target.com/c/pokemon-trading-cards-games/-/N-5tdv"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements (adjust selectors based on actual site structure)
        product_elements = soup.select('[data-test="product-card"]')
        
        for product in product_elements:
            try:
                name_elem = product.select_one('[data-test="product-title"]')
                price_elem = product.select_one('[data-test="product-price"]')
                availability_elem = product.select_one('[data-test="product-availability"]')
                url_elem = product.select_one('a[href^="/p/"]')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                price = float(price_text)
                product_url = "https://www.target.com" + url_elem['href']
                
                # Check if in stock (not "sold out" or "out of stock")
                in_stock_status = not (availability_elem and ("sold out" in availability_elem.text.lower() or 
                                                            "out of stock" in availability_elem.text.lower()))
                
                # Check if price is at retail level
                is_retail_price = False
                for product_type, threshold in self.retail_price_thresholds.items():
                    if product_type.lower() in name.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if in_stock_status and is_retail_price:
                    in_stock.append({
                        'name': name,
                        'price': price,
                        'url': product_url,
                        'store': 'Target'
                    })
                    logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing product: {str(e)}")
        
        return in_stock
    
    def check_walmart(self):
        """Check Walmart for Pokemon cards"""
        logging.info("Checking Walmart...")
        url = "https://www.walmart.com/browse/toys/pokemon-trading-cards/4171_4191_1044400_5208903"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements (adjust selectors based on actual site structure)
        product_elements = soup.select('[data-item-id]')
        
        for product in product_elements:
            try:
                name_elem = product.select_one('.ellipsis-title')
                price_elem = product.select_one('.price-main')
                availability_elem = product.select_one('.fulfillment-text')
                url_elem = product.select_one('a[href^="/ip/"]')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                price = float(price_text)
                product_url = "https://www.walmart.com" + url_elem['href']
                
                # Check if in stock
                in_stock_status = not (availability_elem and "out of stock" in availability_elem.text.lower())
                
                # Check if price is at retail level
                is_retail_price = False
                for product_type, threshold in self.retail_price_thresholds.items():
                    if product_type.lower() in name.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if in_stock_status and is_retail_price:
                    in_stock.append({
                        'name': name,
                        'price': price,
                        'url': product_url,
                        'store': 'Walmart'
                    })
                    logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing product: {str(e)}")
        
        return in_stock
    
    def check_bestbuy(self):
        """Check Best Buy for Pokemon cards"""
        logging.info("Checking Best Buy...")
        url = "https://www.bestbuy.com/site/searchpage.jsp?st=pokemon+cards"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements (adjust selectors based on actual site structure)
        product_elements = soup.select('.list-item')
        
        for product in product_elements:
            try:
                name_elem = product.select_one('.sku-title')
                price_elem = product.select_one('.priceView-customer-price span')
                availability_elem = product.select_one('.fulfillment-add-to-cart-button')
                url_elem = product.select_one('a.image-link')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                price = float(price_text)
                product_url = "https://www.bestbuy.com" + url_elem['href']
                
                # Check if in stock (button says "Add to Cart" not "Sold Out")
                in_stock_status = availability_elem and "add to cart" in availability_elem.text.lower()
                
                # Check if price is at retail level
                is_retail_price = False
                for product_type, threshold in self.retail_price_thresholds.items():
                    if product_type.lower() in name.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if in_stock_status and is_retail_price:
                    in_stock.append({
                        'name': name,
                        'price': price,
                        'url': product_url,
                        'store': 'Best Buy'
                    })
                    logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing product: {str(e)}")
        
        return in_stock
    
    def check_gamestop(self):
        """Check GameStop for Pokemon cards"""
        logging.info("Checking GameStop...")
        url = "https://www.gamestop.com/collectibles/trading-cards/pokemon-tcg"
        html = self.fetch_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        in_stock = []
        
        # Find product elements (adjust selectors based on actual site structure)
        product_elements = soup.select('.product-tile')
        
        for product in product_elements:
            try:
                name_elem = product.select_one('.link-name')
                price_elem = product.select_one('.actual-price')
                availability_elem = product.select_one('.availability')
                url_elem = product.select_one('a.link-name')
                
                if not all([name_elem, price_elem, url_elem]):
                    continue
                
                name = name_elem.text.strip()
                price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                price = float(price_text)
                product_url = "https://www.gamestop.com" + url_elem['href']
                
                # Check if in stock
                in_stock_status = availability_elem and "in stock" in availability_elem.text.lower()
                
                # Check if price is at retail level
                is_retail_price = False
                for product_type, threshold in self.retail_price_thresholds.items():
                    if product_type.lower() in name.lower() and price <= threshold:
                        is_retail_price = True
                        break
                
                if in_stock_status and is_retail_price:
                    in_stock.append({
                        'name': name,
                        'price': price,
                        'url': product_url,
                        'store': 'GameStop'
                    })
                    logging.info(f"Found in-stock item at retail price: {name} - ${price}")
            
            except Exception as e:
                logging.error(f"Error processing product: {str(e)}")
        
        return in_stock
    
    def send_email_notification(self, items):
        """Send email notification for in-stock items"""
        if not items or not self.email_config:
            return
        
        try:
            sender = self.email_config.get('sender')
            recipient = self.email_config.get('recipient')
            password = self.email_config.get('password')
            smtp_server = self.email_config.get('smtp_server', 'smtp.gmail.com')
            smtp_port = self.email_config.get('smtp_port', 587)
            
            if not all([sender, recipient, password]):
                logging.error("Email configuration incomplete")
                return
            
            # Create email content
            subject = f"Pokemon TCG Alert: {len(items)} Items Found at Retail Price!"
            
            body = "The following Pokemon TCG items were found in stock at retail prices:\n\n"
            for item in items:
                body += f"• {item['name']} - ${item['price']} at {item['store']}\n"
                body += f"  Link: {item['url']}\n\n"
            
            body += f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = sender
            msg['To'] = recipient
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)
            
            logging.info(f"Email notification sent for {len(items)} items")
        
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
    
    def check_all_sites(self):
        """Check all sites for in-stock Pokemon TCG items"""
        all_in_stock = []
        
        # Check each site
        all_in_stock.extend(self.check_pokemoncenter())
        all_in_stock.extend(self.check_target())
        all_in_stock.extend(self.check_walmart())
        all_in_stock.extend(self.check_bestbuy())
        all_in_stock.extend(self.check_gamestop())
        
        # Store results
        self.in_stock_items = all_in_stock
        
        # Save results to file
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        with open(f'results_{timestamp}.json', 'w') as f:
            json.dump(all_in_stock, f, indent=2)
        
        # Send notification if items found
        if all_in_stock:
            self.send_email_notification(all_in_stock)
        
        return all_in_stock
    
    def run(self):
        """Run the tracker continuously"""
        logging.info("Starting Pokemon TCG Tracker")
        
        while True:
            try:
                logging.info("Checking sites for Pokemon TCG items at retail prices...")
                results = self.check_all_sites()
                
                if results:
                    logging.info(f"Found {len(results)} items in stock at retail prices")
                else:
                    logging.info("No items found in stock at retail prices")
                
                # Wait for next check
                logging.info(f"Waiting {self.check_interval} seconds until next check...")
                time.sleep(self.check_interval)
            
            except KeyboardInterrupt:
                logging.info("Tracker stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {str(e)}")
                # Wait a bit before retrying
                time.sleep(60)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Pokemon TCG Stock Tracker')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--json', action='store_true', help='Output results as JSON to stdout')
    args = parser.parse_args()
    
    # Initialize tracker with config file
    config_file = args.config if args.config else "config.json"
    tracker = PokemonTCGTracker(config_file)
    
    if args.once:
        # Run the scraper once and exit
        results = tracker.check_all_sites()
        
        if args.json:
            # Print results as JSON to stdout
            print(json.dumps(results))
        else:
            # Print results in a human-readable format
            print(f"Found {len(results)} products in stock at retail prices:")
            for product in results:
                print(f"- {product['name']} (${product['price']}) at {product['store']}")
                print(f"  URL: {product['url']}")
                print()
        
        # Exit the script
        sys.exit(0)
    else:
        # Run continuously as before
        tracker.run()