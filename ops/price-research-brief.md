# Research brief: BUY-NOW hardware prices for artificialacceleration.com

Today is 2026-10-15. Your knowledge of prices is out of date: 2026 has a memory shortage and GPU
prices are far above launch prices. Verify everything live.

THE RULE (from the site owner): a price only counts if a NEW unit can be bought at that price right
now from a real seller: the page shows it IN STOCK or orderable now (add to cart / buy now / in stock /
ships in N days). These are NOT prices and must not be reported as prices:
  - advertised "from" prices, price-comparison headline lows, MSRPs, launch prices, news articles, blogs
  - out-of-stock, sold-out, pre-order, "notify me", "coming soon" listings
  - used, refurbished, open-box, or third-party marketplace resellers (Amazon/eBay marketplace sellers)
Official stores (NVIDIA marketplace, Framework, GMKtec store, ASUS store) count when the page shows the
product can be ordered now. Major retailers count (US: Newegg sold by Newegg, B&H, Micro Center, CDW, Best
Buy; UK: Scan, Overclockers UK, CCL, Box; Germany: Mindfactory, Alternate, Caseking, Cyberport,
notebooksbilliger, Proshop; Japan: Ark, Tsukumo, Dospara, PC Koubou, Bic Camera, Yodobashi; China: JD.com
self-operated (京东自营), official flagship stores on JD/Tmall).

For each product x market assigned to you, find the CHEAPEST in-stock new offer you can confirm.
Fetch the page yourself (curl with header "User-Agent: artificialacceleration.com price check
(+https://artificialacceleration.com)", or WebFetch). Respect robots.txt. Do NOT fetch geizhals, idealo,
ComputerBase, PriceSpy, bestvaluegpu, apple.com store pages, vast.ai, runpod. Never sign in, never add to
cart, never submit forms.

IMPORTANT for verification: the site re-fetches every page you report with a plain HTTP GET (no
JavaScript) and checks that your two text snippets appear in it. So prefer pages whose price and stock
status are in the raw HTML (check with curl). Copy the snippets EXACTLY as they appear in the page text
(after stripping HTML tags; whitespace may be collapsed). If a shop only renders price/stock with
JavaScript, say so in "verifiable_without_js": false and still report it.

Output: a JSON object written to the file named in your task:
{"offers": [ {"product_id": "...", "region": "US|EU|UK|JP|CN", "currency": "USD|EUR|GBP|JPY|CNY",
   "amount": number (as on the page; EU/UK/JP/CN prices include VAT, US before sales tax),
   "seller": "...", "url": "...", "price_text": "exact snippet containing the price",
   "stock_text": "exact snippet showing in stock / orderable now", "product_title": "...",
   "condition": "new", "verifiable_without_js": true|false, "checked": "2026-10-15", "notes": "" } ],
 "unavailable": [ {"product_id": "...", "region": "...", "evidence": "which sellers you checked, all out
   of stock / pre-order only", "urls": ["..."]} ],
 "monitor_pages": [ {"product_id": "...", "region": "...", "url": "a stable product or category page
   worth re-checking every month"} ]}
Then reply with a short summary. Accuracy over coverage: an honest "unavailable" beats a guessed price.
